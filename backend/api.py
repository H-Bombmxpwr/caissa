"""JSON API over the library.

Every handler returns (status, payload). Payloads are dicts (sent as JSON) or a
(bytes, content_type) tuple for raw downloads.
"""

import datetime
import json
import os
import re
import threading
import time
import uuid
import urllib.parse

from . import lichess
from .autoimport import AutoImport
from .engine import AnnotationJob, Engine, EngineError, LiveAnalysis
from .store import Library
from .study import Study
from . import importers
from . import literature
from . import openingtree
from . import openings as opening_names
from . import repertoire as repertoire_pgn
from .books import Books
from .scouting import Scouting

EXTRA_FILTERS = ('annotator','site','round','termination','annotated','date_from','date_to','source','category',
                 'white_min_elo','white_max_elo','black_min_elo','black_max_elo','kind',
                 'team','title','fide_id','source_title','variation','event_type',
                 'event_date_from','event_date_to')

# What POST /api/collections/link may filter on: the game fields a saved search is
# built from, and nothing that would let a request reach outside the library.
COLLECT_FILTERS = ('query', 'collection', 'player', 'player_prefix', 'white_prefix',
                   'black_prefix', 'event_prefix', 'white', 'black', 'eco', 'eco_to', 'result',
                   'outcome', 'opening', 'event', 'year', 'date_from', 'date_to', 'min_elo',
                   'max_elo', 'min_length', 'max_length', 'position', 'tag', 'kind')

# What a collection can hold. The game database lists COLLECTION_KINDS[0] only.
COLLECTION_KINDS = ('games', 'studies', 'openings')


def _epoch_ms(value, end_of_day=False):
    """lichess wants milliseconds; a person picking a date wants a date. Accepts both.

    `end_of_day` makes an inclusive upper bound: "until 2024-06-30" should keep the
    games played on the 30th rather than stopping at midnight that morning.
    """
    if value in (None, ''):
        return None
    text = str(value).strip()
    if text.isdigit() and len(text) > 8:
        return int(text)
    try:
        stamp = datetime.datetime.strptime(text.replace('.', '-')[:10], '%Y-%m-%d')
    except ValueError:
        return None
    if end_of_day:
        stamp += datetime.timedelta(days=1, milliseconds=-1)
    return int(stamp.replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status
        self.message = message


class Api:
    def __init__(self, data_dir):
        self.library = Library(data_dir)
        self.study = Study(self.library)
        self.scouting = Scouting(self.library)
        self.books = Books(self.library)
        self.crawler = lichess.MastersCrawler(self.library)
        self.engine = Engine()
        self.opponent = Engine(threads=1, hash_mb=32)
        self.live = LiveAnalysis()
        self.annotation = AnnotationJob(self.engine, self.library)
        # Watches the linked lichess account for new games. Off unless switched on, and
        # started here so it survives the view that turned it on being navigated away from.
        self.autoimport = AutoImport(self.library, self._lichess_token, self.study)
        self.import_lock = threading.Lock()
        self.delete_previews = {}
        # A starter collection for an empty library only. Re-creating one the user has
        # deleted would make "delete collection" look broken after every restart.
        if not self.library.collections():
            self.library.ensure_collection("My games")
        self.import_status = {'running': False, 'label': '', 'done': 0, 'total': 0,
                              'added': 0, 'duplicates': 0, 'skipped': 0, 'error': None, 'batch_id': None}
        self.autoimport.apply()

    # ---------- dispatch ----------

    def handle(self, method, path, query, body):
        parts = [p for p in path.strip("/").split("/") if p]     # ['api', ...]
        if not parts or parts[0] != "api":
            raise ApiError("not an api route", 404)
        rest = parts[1:]
        if not rest:
            raise ApiError("no endpoint given", 404)

        head = rest[0]
        handler = getattr(self, "_route_" + head, None)
        if handler is None:
            raise ApiError("unknown endpoint: " + head, 404)
        try:
            is_import = method == 'POST' and ((head == 'import' and rest[1:] != ['undo'])
                                             or (head == 'games' and len(rest) == 1)
                                             or (head == 'lichess' and rest[1:] == ['studies']))
            if is_import:
                label = (body or {}).get('collection') or 'Import'
                batch = self.library.begin_import(label)
                # Imports run inside the request, so the only way a view that has been
                # navigated away from can still report one is to publish progress here.
                self.import_status = {'running': True, 'label': label, 'done': 0, 'total': 0,
                                      'added': 0, 'duplicates': 0, 'skipped': 0, 'error': None, 'batch_id': batch}
                self._progress_offset = self._progress_last = 0
                whole_account = (bool((body or {}).get('all')) or rest[1:] == ['reference']
                                 or str((body or {}).get('max', '')) in ('0', 'all'))
                self._progress_streaming = (head == 'import' and (rest[1:] != ['lichess'] or whole_account)) or head == 'lichess'
                self.library.on_progress = self._import_progress
                try:
                    status, payload = handler(method, rest[1:], query, body)
                    payload['batch_id'] = batch
                    for key in ('added', 'duplicates', 'skipped'):
                        self.import_status[key] = payload.get(key, 0)
                    return status, payload
                except (ApiError, ValueError, KeyError, OSError) as err:
                    self.import_status['error'] = getattr(err, 'message', str(err))
                    raise
                finally:
                    self.library.on_progress = None
                    self.import_status['running'] = False
                    self.library.end_import(batch)
            return handler(method, rest[1:], query, body)
        except (ValueError, KeyError) as err:
            raise ApiError(str(err)) from err

    def _route_scouting(self, method, rest, query, body):
        if method == 'GET' and rest == ['human']:
            return 200, self.scouting.human_moves(query)
        if method == 'GET' and not rest:
            return 200, self.scouting.report(query)
        if rest == ['drills']:
            if method == 'GET':
                return 200, {'drills': self.scouting.drills(query.get('player', ''))}
            if method == 'POST':
                try:
                    return 200, self.scouting.create_drill(body or {}, self.engine)
                except EngineError as err:
                    raise ApiError(str(err), 503) from err
        if method == 'POST' and len(rest) == 2 and rest[0] == 'review':
            return 200, self.scouting.review(rest[1], body or {})
        raise ApiError('unsupported scouting request', 405)

    def _route_openings(self, method, rest, query, body):
        """Opening names actually present in the library, with the ECO span each covers.

        There is no bundled ECO table and inventing one would be worse than useless, so
        the suggestions and the ranges behind them come from the games already imported.
        """
        if method == 'POST' and rest == ['classify']:
            return 200, self.library.name_openings((body or {}).get('collection'))
        if method == 'POST' and rest == ['name']:
            body = body or {}
            moves = [san for san in (body.get('moves') or []) if isinstance(san, str)]
            return 200, {'names': opening_names.progression(moves, body.get('fen') or None)}
        if method != 'GET':
            raise ApiError('unsupported openings request', 405)
        term = (query.get('q') or '').strip()
        sql = ["SELECT opening AS name,",
               # A big base subdivides ECO (B90a, E04a). The span an opening covers is
               # still the three-letter code, so the suffix is trimmed rather than
               # treated as a different code — or as no code at all.
               "MIN(CASE WHEN eco GLOB '[A-E][0-9][0-9]*' THEN substr(eco,1,3) END) AS eco_from,",
               "MAX(CASE WHEN eco GLOB '[A-E][0-9][0-9]*' THEN substr(eco,1,3) END) AS eco_to,",
               "COUNT(*) AS games FROM games WHERE opening IS NOT NULL AND opening <> ''"]
        params = []
        if term:
            sql.append('AND opening LIKE ?')
            params.append('%' + term + '%')
        sql.append('GROUP BY opening ORDER BY games DESC, name LIMIT 40')
        rows = [dict(r) for r in self.library.connect().execute(' '.join(sql), params)]
        return 200, {'openings': rows}

    def _import_progress(self, done, total):
        if done < getattr(self, '_progress_last', 0):
            self._progress_offset += self._progress_last
        self._progress_last = done
        self.import_status['done'] = getattr(self, '_progress_offset', 0) + done
        self.import_status['total'] = 0 if getattr(self, '_progress_streaming', False) else total

    def _route_study(self, method, rest, query, body):
        action = rest[0] if rest else 'position'
        body = body or {}

        if action == 'position' and method == 'GET':
            return 200, self.study.position(query['fen'])
        if action == 'index':
            if method == 'GET':
                return 200, self.study.state.copy()
            if method == 'POST':
                return 200, self.study.index(body['collection'])
        if action == 'pins' and method == 'POST':
            return 200, self.study.pin(body)
        if action == 'pins' and method == 'DELETE' and len(rest) == 2:
            with self.library.connect() as db:
                db.execute('DELETE FROM pins WHERE id=?', (int(rest[1]),))
            return 200, {'deleted': True}
        if action == 'folders':
            if method == 'PUT' and len(rest) == 2:
                return 200, self.study.categorize_folder(rest[1], body['category'])
            if method == 'GET':
                return 200, self.study.folders()
            if method == 'POST':
                return 200, self.study.create_folder(body)
            if method == 'DELETE' and len(rest) == 2:
                return 200, self.study.delete_folder(rest[1])
        if action == 'assign' and method == 'POST':
            return 200, self.study.assign(body)
        if action == 'tags' and method == 'GET':
            return 200, {'tags': [r[0] for r in self.library.connect().execute(
                'SELECT tag FROM game_tags WHERE game_id=?', (int(query['game_id']),))]}
        if action == 'tags' and method == 'PUT':
            with self.library._write_lock, self.library.connect() as db:
                db.execute('DELETE FROM game_tags WHERE game_id=?', (int(body['game_id']),))
                db.executemany('INSERT OR IGNORE INTO game_tags VALUES(?,?)',
                    [(int(body['game_id']), str(t).strip()) for t in body.get('tags', []) if str(t).strip()])
            return 200, {'saved': True}
        raise ApiError('unsupported study request', 405)

    # ---------- routes ----------

    def _route_health(self, method, rest, query, body):
        return 200, {
            "ok": True,
            "data_dir": self.library.dir,
            "games": self.library.connect().execute("SELECT COUNT(*) FROM games").fetchone()[0],
            "time": int(time.time()),
        }

    def _route_stats(self, method, rest, query, body):
        return 200, self.library.stats(full=query.get('full') in ('1', 'true'))

    def _route_books(self, method, rest, query, body):
        if method=='GET' and not rest:
            return 200, {'books':self.books.list()}
        if method=='POST' and not rest:
            return 200,self.books.add(body or {})
        if method=='PUT' and len(rest)==1:
            return 200,self.books.update(rest[0],body or {})
        raise ApiError('Unsupported books request',405)

    def _route_tree(self, method, rest, query, body):
        """One player's openings: what was played, and how it went for them.

        The player may be the reader or anyone else in the library — a collection of
        Fischer's games is exactly what this is for. The same filters drive all three
        views, so the weakest-line list and the position report are always talking
        about the same set of games.
        """
        from .chess import Chess
        if method != "GET":
            raise ApiError("Use GET", 405)
        action = rest[0] if rest else "position"

        if action == "players":
            return 200, {"players": openingtree.players(
                self.library, query.get("collection"), int(query.get("limit", 40)))}

        filters = openingtree.Filters(
            player=query.get("player"), color=query.get("color"),
            collection=query.get("collection"), speed=query.get("speed"),
            since=query.get("since"), until=query.get("until"),
            min_opponent_elo=query.get("min_opponent_elo") or None,
            max_opponent_elo=query.get("max_opponent_elo") or None,
            rated=query.get("rated") if query.get("rated") not in (None, "") else None,
            kind=query.get("kind") or None,
        )

        if action == "weakest":
            return 200, {
                "player": filters.player or None,
                "weakest": openingtree.weakest(
                    self.library, filters,
                    min_games=max(1, int(query.get("min_games", openingtree.DEFAULT_MIN_GAMES))),
                    limit=max(1, min(int(query.get("limit", 15)), 50)),
                    max_ply=max(2, min(int(query.get("max_ply", openingtree.MAX_SCAN_PLY)), 80)),
                ),
            }

        if action == "position":
            fen = Chess(query.get("fen") or Chess().fen()).fen()
            report = openingtree.position(self.library, fen, filters)
            report["indexed_games"] = self.library.connect().execute(
                "SELECT COUNT(DISTINCT game_id) FROM positions").fetchone()[0]
            return 200, report

        raise ApiError("unsupported tree request", 404)

    def _route_book(self, method, rest, query, body):
        from .chess import Chess
        if method!='GET':
            raise ApiError('Use GET',405)
        fen=query.get('fen') or Chess().fen()
        source=query.get('source','local')
        if source=='bundled':
            from .openingbook import lookup
            return 200,lookup(fen)
        if source not in ('local','masters','lichess'):
            raise ApiError('Choose local, masters or lichess')
        if source!='local':
            options={key:query[key] for key in ('since','until','ratings','speeds') if query.get(key)}
            _,data=self._route_explorer('GET',[],dict(options,db=source,fen=fen,moves='50',top='15'),None)
            return 200,{'fen':fen,'source':source,'cached':data.get('_cached',False),
                'stale':data.get('_stale',False),'opening':data.get('opening'),
                'total':sum(data.get(k,0) for k in ('white','draws','black')),
                'moves':[dict(san=m['san'],games=sum(m.get(k,0) for k in ('white','draws','black')),
                    white=m.get('white',0),draws=m.get('draws',0),black=m.get('black',0),
                    average_elo=m.get('averageRating')) for m in data.get('moves',[])],
                'games':[],'reference_games':data.get('topGames',[])}
        clause='p.hash=?'
        params=[Chess(fen).key()]
        if query.get('collection'):
            clause+=' AND g.collection_id=?'
            params.append(int(query['collection']))
        db=self.library.connect()
        rows=[dict(r) for r in db.execute('''SELECT next_san AS san, COUNT(*) AS games,
            SUM(result='1-0') AS white, SUM(result='0-1') AS black,
            SUM(result='1/2-1/2') AS draws, SUM(result='*') AS unfinished,
            ROUND(AVG(elo)) AS average_elo FROM (
              SELECT DISTINCT p.game_id,p.next_san,g.result,
                (g.white_elo+g.black_elo)/2.0 AS elo
              FROM positions p JOIN games g ON g.id=p.game_id WHERE '''+clause+'''
              AND p.next_san IS NOT NULL) GROUP BY next_san ORDER BY games DESC,san''',params)]
        games=[dict(r) for r in db.execute('''SELECT DISTINCT g.id,g.white,g.black,g.date,g.event,g.result
            FROM positions p JOIN games g ON g.id=p.game_id WHERE '''+clause+' ORDER BY g.date DESC LIMIT 20',params)]
        return 200,{'fen':fen,'moves':rows,'games':games}

    def _route_network(self, method, rest, query, body):
        import urllib.request
        try:
            req=urllib.request.Request('https://www.pgnmentor.com/files.html',method='HEAD',headers={'User-Agent':'Caissa/1.0'})
            with urllib.request.urlopen(req,timeout=4) as response:
                reachable=response.status<400
        except Exception:
            reachable=False
        return 200,{'reachable':reachable,'service':'PGN Mentor','checked_at':int(time.time())}

    def _route_collections(self, method, rest, query, body):
        if method == "GET" and not rest:
            return 200, {"collections": self.library.collections()}
        if method == "POST" and not rest:
            name = (body or {}).get("name", "").strip()
            if not name:
                raise ApiError("a collection needs a name")
            return 200, {"collection": self.library.ensure_collection(name, (body or {}).get("kind", "games"))}
        if method == "POST" and rest == ["link"]:
            body = body or {}
            name = str(body.get("name", "")).strip()
            if not name:
                raise ApiError("a collection needs a name")
            kind = body.get("kind") or "games"
            if kind not in COLLECTION_KINDS:
                raise ApiError("unknown collection kind: " + str(kind))
            filters = {key: value for key, value in (body.get("filters") or {}).items()
                       if key in COLLECT_FILTERS and value not in (None, "")}
            if not filters:
                raise ApiError("Narrow the search before collecting it: an empty filter is the whole library.")
            try:
                return 200, self.library.collect_into(name, filters, kind)
            except ValueError as err:      # a malformed date or ELO never reaches SQL
                raise ApiError(str(err))
        if method == "PUT" and len(rest) == 1:
            info = self.library.collection(rest[0])
            if not info:
                raise ApiError("no such collection", 404)
            try:
                renamed = self.library.rename_collection(info["id"], (body or {}).get("name", ""))
            except ValueError as err:
                raise ApiError(str(err))
            folder = self.library.connect().execute(
                'SELECT folder_id FROM collection_folders WHERE collection_id=?', (info['id'],)).fetchone()
            if folder:
                self.study.write_manifest(folder['folder_id'])
            return 200, {"collection": renamed}
        if rest and rest[-1] == "pgn" and method == "GET":
            info = self.library.collection(rest[0])
            if not info:
                raise ApiError("no such collection", 404)
            found = self.library.search(collection=info["name"], limit=100000)
            chunks = [self.library.game_pgn(g["id"]) for g in found["games"]]
            text = "\n\n".join(c for c in chunks if c) + "\n"
            return 200, (text.encode("utf-8"), "application/x-chess-pgn")
        if method == "DELETE" and rest:
            info = self.library.collection(rest[0])
            folder = self.library.connect().execute(
                'SELECT folder_id FROM collection_folders WHERE collection_id=?', (info['id'],)).fetchone() if info else None
            removed = self.library.delete_collection(rest[0], remove_files=query.get("files") == "1")
            if removed and folder:
                self.study.write_manifest(folder['folder_id'])
            if not removed:
                raise ApiError("no such collection", 404)
            return 200, {"deleted": True}
        raise ApiError("unsupported collections request", 405)

    def _route_games(self, method, rest, query, body):
        if rest == ['delete-preview'] and method == 'POST':
            filters = dict((body or {}).get('filters') or {})
            filters.pop('limit', None)
            filters.pop('offset', None)
            if 'q' in filters:
                filters['query'] = filters.pop('q')
            allowed = {'query','collection','player','player_prefix','white_prefix','black_prefix','event_prefix','white','black','eco','eco_to','result','opening','min_elo','max_elo','outcome','year','sort','event','min_length','max_length','tag','added_from','added_to','position'}
            allowed.update(EXTRA_FILTERS)
            if set(filters) - allowed:
                raise ApiError('Unknown filter')
            found = self.library.search(**filters, limit=-1)
            token = uuid.uuid4().hex
            now = time.time()
            self.delete_previews = {k:v for k,v in self.delete_previews.items() if now-v[0]<600}
            # Bind confirmation to row identity as well as id (SQLite may reuse ids).
            ids = [(g['id'],g['signature'],g['path'],g['byte_offset'],g['byte_length']) for g in found['games']]
            self.delete_previews[token] = (now, ids)
            return 200, {'token': token, 'total': found['total'], 'sample': found['games'][:10]}
        if rest == ['delete-confirm'] and method == 'POST':
            entry = self.delete_previews.pop((body or {}).get('token'), None)
            if not entry or time.time()-entry[0]>600:
                raise ApiError('Deletion preview expired; preview the filters again')
            with self.library._write_lock, self.library.connect() as db:
                count = 0
                for identity in entry[1]:
                    count += db.execute('DELETE FROM games WHERE id=? AND signature=? AND path=? AND byte_offset=? AND byte_length=?',identity).rowcount
            return 200, {'deleted': count}
        if method == "GET" and not rest:
            return 200, self.library.search(
                query=query.get("q"),
                collection=query.get("collection"),
                player=query.get("player"),
                white=query.get("white"),
                black=query.get("black"),
                eco=query.get("eco"), max_elo=query.get("max_elo"), outcome=query.get("outcome"),
                result=query.get("result"),
                opening=query.get("opening"),
                min_elo=query.get("min_elo"),
                year=query.get("year"),
                sort=query.get("sort", "date"),
                limit=min(int(query.get("limit", 100)), 500),
                offset=int(query.get("offset", 0)),
                event=query.get('event'), min_length=query.get('min_length'),
                max_length=query.get('max_length'), tag=query.get('tag'),
                added_from=query.get('added_from'), added_to=query.get('added_to'),
                position=query.get('position'), eco_to=query.get('eco_to'),
                player_prefix=query.get('player_prefix'), event_prefix=query.get('event_prefix'),
                white_prefix=query.get('white_prefix'), black_prefix=query.get('black_prefix'),
                **{key:query.get(key) for key in EXTRA_FILTERS},
            )
        # /api/games/<id>/collections — the shelves one game sits on.
        if len(rest) >= 2 and rest[1] == "collections":
            game_id = int(rest[0])
            if method == "GET":
                return 200, {"collections": self.library.collections_for([game_id]).get(game_id, [])}
            if method == "POST":
                name = str((body or {}).get("collection", "")).strip()
                if not name:
                    raise ApiError("Name the collection to add this game to.")
                kind = (body or {}).get("kind") or "games"
                if kind not in COLLECTION_KINDS:
                    raise ApiError("unknown collection kind: " + str(kind))
                if not self.library.collection(name):
                    self.library.ensure_collection(name, kind)
                linked = self.library.link_game(game_id, name)
                return 200, {"linked": linked, "collection": name,
                             "collections": self.library.collections_for([game_id]).get(game_id, [])}
            if method == "DELETE" and len(rest) == 3:
                removed = self.library.unlink_game(game_id, urllib.parse.unquote(rest[2]))
                if not removed:
                    raise ApiError("That game is not linked into this collection. A game's "
                                   "own collection is changed by moving it, not by unlinking.")
                return 200, {"unlinked": True,
                             "collections": self.library.collections_for([game_id]).get(game_id, [])}
            raise ApiError("unsupported collections request", 405)

        if method == "GET" and rest:
            game = self.library.game(int(rest[0]))
            if not game:
                raise ApiError("no such game", 404)
            return 200, {"game": game}
        if method == "POST" and not rest:
            pgn = (body or {}).get("pgn", "")
            if not pgn.strip():
                raise ApiError("no PGN given")
            kind = (body or {}).get("kind") or "games"
            if kind not in COLLECTION_KINDS:
                raise ApiError("unknown collection kind: " + kind)
            result = self.library.add_games(
                pgn,
                collection=(body or {}).get("collection") or "My games",
                source=(body or {}).get("source") or "import",
                kind=kind,
            )
            return 200, result
        if method == "PUT" and rest:
            pgn = (body or {}).get("pgn", "")
            if not pgn.strip():
                raise ApiError("no PGN given")
            if not self.library.replace_game(int(rest[0]), pgn):
                raise ApiError("no such game", 404)
            return 200, {"saved": True, "game": self.library.game(int(rest[0]))}
        if method == "DELETE" and rest:
            if not self.library.delete_game(int(rest[0])):
                raise ApiError("no such game", 404)
            return 200, {"deleted": True}
        raise ApiError("unsupported games request", 405)

    def _route_import(self, method, rest, query, body):
        if method == 'GET' and rest == ['status']:
            return 200, dict(self.import_status)
        if method == 'GET' and rest == ['history']:
            return 200, {'batches': self.library.import_history()}
        if method == 'POST' and rest == ['undo']:
            return 200, self.library.undo_import((body or {})['batch_id'])
        if method != "POST" or not rest:
            raise ApiError("unsupported import request", 405)
        kind = rest[0]
        body = body or {}

        if kind == 'reference':
            # Attaching is a scan, not a download. The file is already here; the only
            # thing produced is index rows pointing back into it.
            if not self.import_lock.acquire(blocking=False):
                raise ApiError('An import is already running', 409)
            try:
                attached = importers.attach_reference(
                    self.library, str(body.get('path', '')).strip(),
                    body.get('collection') or 'Reference base',
                    progress=self._import_progress)
                try:
                    attached['folder'] = self.study.shelve(
                        attached['collection_id'], body.get('folder') or 'Reference')
                except (ValueError, KeyError, OSError) as err:
                    attached['folder_error'] = str(err)   # the games are in; the shelf is not worth failing for
                return 200, attached
            except OSError as err:
                raise ApiError('Could not read that PGN: ' + str(err), 503) from err
            finally:
                self.import_lock.release()

        if kind in ('source', 'chesscom'):
            if not self.import_lock.acquire(blocking=False):
                raise ApiError('An import is already running', 409)
            try:
                if kind == 'source':
                    source = str(body.get('path', '')).strip()
                    if not source:
                        raise ApiError('Give a local path or download URL')
                    return 200, importers.import_source(self.library, source, body.get('collection') or 'My games')
                user = str(body.get('user', '')).strip()
                # 0 (or "all") means the whole account; anything else is a game count.
                wanted = body.get('max', 100)
                wanted = 0 if wanted in (0, '0', 'all', None, '') else max(1, int(wanted))
                return 200, importers.chesscom(self.library, user, body.get('collection') or 'chess.com imports',
                                               wanted, perf=body.get('perf'), since=body.get('since'),
                                               until=body.get('until'))
            except OSError as err:
                raise ApiError('Could not import source: '+str(err), 503) from err
            finally:
                self.import_lock.release()

        if kind == "lichess":
            user = str(body.get("user", "")).strip()
            if not user:
                raise ApiError("give a lichess username")
            if not self.import_lock.acquire(blocking=False):
                raise ApiError("an import is already running — one at a time keeps lichess happy", 409)
            try:
                token = body.get("token") or self.library.setting("lichess_token") or None
                if body.get("token"):
                    self.library.setting("lichess_token", body["token"])
                collection = body.get("collection") or "lichess imports"
                selection = {"color": body.get("color"), "rated": body.get("rated"),
                             "perf": body.get("perf"), "since": _epoch_ms(body.get("since")),
                             "until": _epoch_ms(body.get("until"), end_of_day=True)}
                if body.get("all") or str(body.get("max", "")) in ("0", "all"):
                    # No ceiling and no idea how many are coming, so it is streamed
                    # and written in batches rather than held in memory.
                    return 200, lichess.import_all_user_games(
                        self.library, user, collection, token=token,
                        **selection)
                pgn = lichess.user_games(
                    user,
                    max_games=max(1, int(body.get("max", 100))),
                    token=token,
                    **selection,
                )
                result = self.library.add_games(pgn, collection=collection, source="lichess")
                result["user"] = user
                return 200, result
            except lichess.RateLimited as err:
                raise ApiError(
                    "lichess is rate limiting us — try again in %ss" % err.retry_after, 429
                ) from err
            except FileNotFoundError as err:
                raise ApiError("no such lichess user: " + user, 404) from err
            except PermissionError as err:
                raise ApiError(str(err), 401) from err
            except ConnectionError as err:
                raise ApiError("could not reach lichess: %s" % err, 503) from err
            finally:
                self.import_lock.release()

        if kind == "dump":
            path = str(body.get("path", "")).strip()
            if not path or not os.path.exists(path):
                raise ApiError("give the path of a .pgn or .pgn.zst file on this machine")
            if not self.import_lock.acquire(blocking=False):
                raise ApiError("an import is already running", 409)
            try:
                result = lichess.import_dump(
                    self.library, path,
                    collection=body.get("collection") or "Masters",
                    limit=body.get("limit"),
                )
                return 200, result
            except RuntimeError as err:
                raise ApiError(str(err), 400) from err
            finally:
                self.import_lock.release()

        raise ApiError("unknown import source: " + kind, 404)

    def _route_tablebase(self, method, rest, query, body):
        from .chess import Chess
        if method != 'GET':
            raise ApiError('Use GET', 405)
        fen = Chess(query['fen']).fen()
        if sum(c.isalpha() for c in fen.split()[0]) > 7:
            raise ApiError('Tablebase supports at most seven pieces, including kings')
        cached = self.library.setting('tablebase:'+fen)
        if cached:
            return 200, json.loads(cached)
        try:
            data = json.loads(lichess._request('https://tablebase.lichess.org/standard?'+urllib.parse.urlencode({'fen':fen}), 'application/json'))
        except Exception as err:
            raise ApiError('Tablebase unavailable. Connect to the internet and try again.', 503) from err
        self.library.setting('tablebase:'+fen, json.dumps(data))
        return 200, data

    def _route_literature(self, method, rest, query, body):
        """Free study material for the line on the board."""
        if method != "GET":
            raise ApiError("unsupported literature request", 405)
        raw = query.get("moves") or "[]"
        try:
            sans = json.loads(raw) if raw.strip().startswith("[") else raw.split()
        except ValueError:
            sans = raw.split()
        if not isinstance(sans, list):
            raise ApiError("moves must be a list of SAN moves")
        return 200, literature.references(
            [str(m) for m in sans][:24],
            opening=query.get("opening"),
            eco=query.get("eco"),
            online=query.get("offline") != "1",
        )

    def _route_facts(self, method, rest, query, body):
        """What Wikipedia has to say about the players, the event, and maybe the game."""
        if method != "GET":
            raise ApiError("unsupported facts request", 405)
        headers = {key: query.get(key.lower(), "") for key in ("White", "Black", "Event", "Site", "Date")}
        if not (headers["White"] or headers["Black"] or headers["Event"]):
            raise ApiError("give at least a player or an event to look up")
        # Older results trusted Wikipedia's search ranking and could recommend
        # a different year's championship. Do not reuse those cached suggestions.
        key = "facts:v2:" + json.dumps(headers, sort_keys=True)
        cached = self.library.setting(key)
        if cached:
            found = json.loads(cached)
            found["cached"] = True
            return 200, found
        found = literature.game_facts(headers, online=query.get("offline") != "1")
        # Only a real answer is worth keeping; an offline miss must not become permanent.
        if found.get("groups") or found.get("note"):
            self.library.setting(key, json.dumps(found))
        return 200, found

    def _route_explorer(self, method, rest, query, body):
        if method != "GET":
            raise ApiError("unsupported explorer request", 405)
        db = query.get("db", "masters")
        if db not in ("masters", "lichess"):
            raise ApiError("db must be masters or lichess")
        play = query.get("play", "")
        fen = query.get("fen")
        extra={key:query[key] for key in ('since','until','ratings','speeds') if query.get(key)}
        if db=='masters':
            extra={key:value for key,value in extra.items() if key in ('since','until')}
        cache_key = json.dumps([db,fen,play,query.get('moves','12'),query.get('top','8'),extra],sort_keys=True)
        cached = self.library.cache_explorer(cache_key, db)
        if cached:
            return 200, dict(json.loads(cached),_cached=True)
        try:
            data = lichess.explorer(
                db,
                play=[m for m in play.split(",") if m] if play else None,
                fen=fen,
                moves=int(query.get("moves", 12)),
                top_games=int(query.get("top", 8)),
                extra=extra,
                # lichess requires a signed-in account on the explorer endpoints now.
                token=self._lichess_token(),
            )
        except Exception as err:
            stale=self.library.cache_explorer(cache_key,db,max_age=10**12)
            if stale:
                return 200,dict(json.loads(stale),_cached=True,_stale=True)
            if isinstance(err,lichess.RateLimited):
                raise ApiError("explorer is rate limiting us — try again shortly",429) from err
            raise ApiError("could not reach the explorer: %s" % err,503) from err
        self.library.cache_explorer(cache_key, db, json.dumps(data))
        return 200, data

    def _route_masters(self, method, rest, query, body):
        action = rest[0] if rest else ""
        if action == 'references' and method == 'GET':
            return 200, {'references': self.library.references(),
                         'attachable': self.library.attachable(),
                         'folder': self.library.REFERENCE_DIR}
        if action == 'detach' and method == 'POST':
            body = body or {}
            return 200, importers.detach_reference(self.library, body['collection'],
                                                   force=bool(body.get('force')))
        if action == 'dependents' and method == 'GET':
            return 200, {'dependents': importers.reference_dependents(
                self.library, int(query['collection']))}
        if action == 'players' and method == 'GET':
            names={name:{'name':name,'source':'Master player'} for name in
                'Carlsen Kasparov Karpov Fischer Spassky Tal Botvinnik Smyslov Petrosian Alekhine Capablanca Lasker Steinitz Anand Kramnik Topalov Polgar Ding Gukesh Nakamura Caruana Aronian Giri So Nepomniachtchi Firouzja Erigaisi Abdusattorov Praggnanandhaa Keymer Short Adams Ivanchuk Shirov Morozevich Svidler Grischuk Gelfand Rubinstein Nimzowitsch Reti Tarrasch Bronstein Korchnoi Reshevsky Najdorf Larsen Euwe'.split()}
            cached=self.library.setting('mentor_catalog')
            for player in json.loads(cached or '[]'):
                names[player['name']]={'name':player['name'],'source':'PGN Mentor collection'}
            needle=query.get('q','').strip()
            if needle:
                for probe in {needle, needle[:1].upper()+needle[1:]}:
                    rows=self.library.connect().execute('''SELECT DISTINCT name FROM
                        (SELECT white AS name FROM games WHERE white>=? AND white<?
                         UNION SELECT black AS name FROM games WHERE black>=? AND black<?)
                        LIMIT 60''',(probe,probe+'\uffff',probe,probe+'\uffff'))
                    for row in rows:
                        name=row['name'].split(',')[0].strip()
                        if name and name!='?':names.setdefault(name,{'name':name,'source':'Your library'})
            return 200,{'players':sorted([p for p in names.values() if needle.casefold() in p['name'].casefold()],key=lambda p:p['name'])[:100]}
        if action == 'catalog' and method == 'GET':
            from html.parser import HTMLParser
            class Catalog(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.players = {}
                def handle_starttag(self, tag, attrs):
                    href = dict(attrs).get('href', '')
                    if tag == 'a' and re.fullmatch(r'players/[A-Za-z0-9_-]+\.(pgn|zip)', href):
                        name = href.split('/')[-1][:-4]
                        self.players[name] = {'name': name, 'url':'https://www.pgnmentor.com/'+href}
            cached = self.library.setting('mentor_catalog')
            if cached:
                players = json.loads(cached)
            else:
                try:
                    parser = Catalog()
                    parser.feed(lichess._request('https://www.pgnmentor.com/files.html','text/html'))
                    players = list(parser.players.values())
                    if players:
                        self.library.setting('mentor_catalog',json.dumps(players))
                except Exception as err:
                    raise ApiError('Could not load PGN Mentor. Check your connection.',503) from err
            needle = query.get('q','').strip().casefold()
            return 200, {'players':[p for p in players if needle in p['name'].casefold()][:100]}
        if action == "status" and method == "GET":
            return 200, self.crawler.status()
        if action == "crawl" and method == "POST":
            body = body or {}
            started = self.crawler.start(
                max_depth=int(body.get("depth", 8)),
                max_positions=int(body.get("positions", 300)),
                min_games=int(body.get("min_games", 200)),
                top_games=int(body.get("top_games", 8)),
                collection=body.get("collection") or "Masters",
                opening_moves=body.get("moves") or [],
            )
            if not started:
                raise ApiError("a crawl is already running", 409)
            return 200, {"started": True, "status": self.crawler.status()}
        if action == "stop" and method == "POST":
            self.crawler.stop()
            return 200, {"stopping": True}
        raise ApiError("unsupported masters request", 405)

    def _route_repertoires(self, method, rest, query, body):
        if method == "POST" and rest == ["import"]:
            return self._import_repertoire(body or {})
        if method == "GET" and not rest:
            return 200, {"repertoires": self.library.repertoires()}
        if method == "GET" and rest:
            rep = self.library.repertoire(int(rest[0]))
            if not rep:
                raise ApiError("no such repertoire", 404)
            return 200, {"repertoire": rep}
        if method in ("POST", "PUT"):
            body = body or {}
            name = str(body.get("name", "")).strip()
            if not name:
                raise ApiError("a repertoire needs a name")
            rep_id = int(rest[0]) if rest else body.get("id")
            new_id = self.library.save_repertoire(
                name, body.get("color", "w"), json.dumps(body.get("data") or {}), rep_id
            )
            return 200, {"id": new_id}
        if method == "DELETE" and rest:
            if not self.library.delete_repertoire(int(rest[0])):
                raise ApiError("no such repertoire", 404)
            return 200, {"deleted": True}
        raise ApiError("unsupported repertoire request", 405)

    def _import_repertoire(self, body):
        """Read an opening PGN into repertoire lines, keeping the PGN itself searchable.

        The games go into a collection of kind 'openings' rather than the game
        database: an opening tree is reference material, not games that were played.
        """
        pgn = str(body.get("pgn", ""))
        if not pgn.strip():
            raise ApiError("Choose a PGN file, or paste one in.")
        name = str(body.get("name", "")).strip()
        if not name:
            raise ApiError("Name the repertoire these lines belong to.")
        color = "b" if str(body.get("color", "w")).lower().startswith("b") else "w"
        try:
            max_plies = max(4, min(int(body.get("max_plies") or repertoire_pgn.MAX_PLIES), 200))
        except (TypeError, ValueError):
            max_plies = repertoire_pgn.MAX_PLIES
        parsed = repertoire_pgn.from_pgn(pgn, color, max_plies)
        if not parsed["lines"]:
            raise ApiError("No playable lines were found in that PGN.")

        rep_id = body.get("id")
        added = len(parsed["lines"])
        lines = parsed["lines"]
        if rep_id:
            existing = self.library.repertoire(int(rep_id))
            if not existing:
                raise ApiError("no such repertoire", 404)
            stored = json.loads(existing["data"] or "{}")
            lines, added = repertoire_pgn.merge(stored.get("lines") or [], parsed["lines"])
            name, color = existing["name"], existing["color"]
        new_id = self.library.save_repertoire(name, color, json.dumps({"lines": lines}), rep_id)

        stored_games = None
        if body.get("keep_pgn", True):
            collection = str(body.get("collection", "")).strip() or "Opening trees"
            stored_games = self.library.add_games(pgn, collection=collection,
                                                  source="repertoire", kind="openings")
        return 200, {"id": new_id, "name": name, "color": color, "lines": len(lines),
                     "added": added, "chapters": parsed["chapters"],
                     "skipped_chapters": parsed["skipped"], "truncated": parsed["truncated"],
                     "collection": (stored_games or {}).get("collection"),
                     "games_added": (stored_games or {}).get("added", 0)}

    # ---------- the lichess account, and the studies it can reach ----------

    def _lichess_token(self):
        return self.library.setting("lichess_token") or None

    def _lichess_call(self, work):
        """One place to turn lichess's failure modes into answers a reader can act on."""
        try:
            return work()
        except PermissionError as err:
            raise ApiError(str(err), 401) from err
        except lichess.RateLimited as err:
            raise ApiError("lichess is rate limiting us — try again in %ss" % err.retry_after, 429) from err
        except FileNotFoundError as err:
            raise ApiError("lichess has no such user or study", 404) from err
        except (ConnectionError, OSError) as err:
            raise ApiError("could not reach lichess: %s" % err, 503) from err

    def _route_lichess(self, method, rest, query, body):
        body = body or {}
        action = rest[0] if rest else "account"

        if action == "account" and method == "GET":
            token = self._lichess_token()
            if not token:
                return 200, {"connected": False, "token_url": lichess.TOKEN_URL,
                             "scopes_needed": list(lichess.SCOPES)}
            try:
                details = self._lichess_call(lambda: lichess.account(token))
            except ApiError as err:
                # A token that has been revoked should say so rather than look connected.
                return 200, {"connected": False, "error": err.message, "stored": True,
                             "token_url": lichess.TOKEN_URL, "scopes_needed": list(lichess.SCOPES)}
            details.update(connected=True, token_url=lichess.TOKEN_URL,
                           scopes_needed=list(lichess.SCOPES))
            return 200, details

        if action == "account" and method == "PUT":
            token = str(body.get("token", "")).strip()
            if not token:
                raise ApiError("Paste the personal access token from lichess.")
            details = self._lichess_call(lambda: lichess.account(token))
            self.library.setting("lichess_token", token)
            self.autoimport.state["user"] = details.get("username")
            self.autoimport.apply()
            details.update(connected=True, saved=True)
            return 200, details

        if action == "account" and method == "DELETE":
            self.library.setting("lichess_token", "")
            self.autoimport.stop()
            return 200, {"connected": False, "forgotten": True}

        if action == "studies" and method == "GET":
            token = self._lichess_token()
            user = (query.get("user") or "").strip()
            if not user:
                if not token:
                    raise ApiError("Connect your lichess account, or name a user.", 401)
                user = self._lichess_call(lambda: lichess.account(token))["username"]
            found = self._lichess_call(lambda: lichess.studies(user, token))
            return 200, {"user": user, "studies": found, "authenticated": bool(token)}

        if action == "studies" and method == "POST":
            return self._import_lichess_studies(body)

        if action == "autoimport":
            if method == "GET":
                return 200, self.autoimport.status()
            if method == "PUT":
                if body.get("enabled") and not self._lichess_token():
                    raise ApiError("Connect your lichess account before switching this on.", 401)
                self.autoimport.save(body)
                return 200, self.autoimport.status()
            if method == "POST":
                # An explicit "check now", which also works while the watcher is off.
                result = self.autoimport.run_once()
                if result.get("error"):
                    raise ApiError(result["error"], 503)
                return 200, dict(result, status=self.autoimport.status())

        raise ApiError("unsupported lichess request", 405)

    def _import_lichess_studies(self, body):
        """Bring chosen studies in as PGN, and optionally as drillable repertoire lines.

        Studies are reference material, so they are filed under a collection of kind
        'studies' and stay out of the game database while remaining searchable there.
        """
        # Either [{id, name}] or bare ids. The name matters: a collection called after
        # the study is the one the reader will go looking for afterwards.
        chosen = body.get("studies") or [{"id": i} for i in (body.get("ids") or [])]
        chosen = [{"id": str(s.get("id", "")).strip(), "name": str(s.get("name", "")).strip()}
                  for s in chosen if str(s.get("id", "")).strip()]
        if not chosen:
            raise ApiError("Choose at least one study to import.")
        ids = [s["id"] for s in chosen]
        token = self._lichess_token()
        # A blank collection name means "one collection per study, named after it".
        shared = str(body.get("collection", "")).strip()
        kind = body.get("kind") or "studies"
        if kind not in COLLECTION_KINDS:
            raise ApiError("unknown collection kind: " + str(kind))
        as_repertoire = bool(body.get("as_repertoire"))
        color = "b" if str(body.get("color", "w")).lower().startswith("b") else "w"

        added = duplicates = skipped = 0
        rep_id = body.get("repertoire_id")
        rep_lines_added = 0
        failures = []
        imported = []
        linked = 0
        collections = []
        for study in chosen:
            study_id, label = study["id"], study["name"]
            try:
                pgn = self._lichess_call(lambda sid=study_id: lichess.study_pgn(sid, token))
            except ApiError as err:
                failures.append({"id": study_id, "name": label, "error": err.message})
                continue
            if not pgn.strip():
                failures.append({"id": study_id, "name": label,
                                 "error": "that study exported no chapters"})
                continue
            target = shared or label or ("Lichess study " + study_id)
            result = self.library.add_games(pgn, collection=target,
                                            source="lichess-study", kind=kind)
            added += result["added"]
            duplicates += result["duplicates"]
            skipped += result["skipped"]
            linked += result.get("linked", 0)
            if result["collection"] not in collections:
                collections.append(result["collection"])
            imported.append(study_id)
            if as_repertoire:
                parsed = repertoire_pgn.from_pgn(pgn, color)
                if parsed["lines"]:
                    name = str(body.get("name", "")).strip() or "Lichess repertoire"
                    if rep_id:
                        existing = self.library.repertoire(int(rep_id))
                        stored = json.loads(existing["data"] or "{}") if existing else {}
                        merged, fresh = repertoire_pgn.merge(stored.get("lines") or [], parsed["lines"])
                        name, color = (existing["name"], existing["color"]) if existing else (name, color)
                    else:
                        merged, fresh = parsed["lines"], len(parsed["lines"])
                    rep_id = self.library.save_repertoire(name, color, json.dumps({"lines": merged}), rep_id)
                    rep_lines_added += fresh
        return 200, {"added": added, "duplicates": duplicates, "skipped": skipped,
                     "linked": linked, "collection": collections[0] if collections else None,
                     "collections": collections, "kind": kind, "studies": len(imported),
                     "repertoire_id": rep_id, "repertoire_lines": rep_lines_added,
                     "failures": failures}

    def _route_engine(self, method, rest, query, body):
        action = rest[0] if rest else "info"
        body = body or {}
        if action == 'live':
            if method == 'GET':
                return 200, self.live.status()
            if method == 'DELETE':
                with self.live.lock:
                    self.live.stop()
                return 200, {'stopped': True}
            if method == 'POST':
                from .chess import Chess
                fen = Chess(body['fen']).fen()
                try:
                    return 200, self.live.start(fen, max(1, min(5, int(body.get('multipv', 3)))))
                except EngineError as err:
                    raise ApiError(str(err), 503) from err

        if action == 'play' and method == 'POST':
            from .chess import Chess
            level = int(body.get('level', 5))
            if not 1 <= level <= 11:
                raise ApiError('Choose a computer level from 1 to 11')
            fen = Chess(body.get('fen', '')).fen()
            try:
                return 200, self.opponent.analyze(fen, skill=(level-1)*2,
                                                 movetime=100+level*75)
            except EngineError as err:
                raise ApiError(str(err), 503) from err

        if action == "info" and method == "GET":
            return 200, self.engine.info()

        if action == "analyze" and method == "POST":
            fen = body.get("fen")
            if not fen:
                raise ApiError("give a position (fen)")
            try:
                return 200, self.engine.analyze(
                    fen,
                    movetime=body.get("movetime"),
                    depth=body.get("depth"),
                    multipv=body.get("multipv", 1),
                )
            except EngineError as err:
                raise ApiError(str(err), 503) from err

        if action == "annotate" and method == "POST":
            positions = body.get("positions") or []
            if not positions:
                raise ApiError("give the positions to analyze")
            started = self.annotation.start(
                body.get("game_id"),
                positions,
                movetime=int(body.get("movetime", 300)),
                depth=body.get("depth"),
            )
            if not started:
                raise ApiError("an annotation run is already going", 409)
            return 200, {"started": True, "total": len(positions)}

        if action == "annotate" and method == "GET":
            return 200, self.annotation.status()

        if action == "stop" and method == "POST":
            self.annotation.stop()
            return 200, {"stopping": True}

        raise ApiError("unsupported engine request", 405)

    # Credentials live in the settings table but must not leave through the settings
    # route: the account route reports who the token belongs to instead.
    SECRET_SETTINGS = ("lichess_token",)

    def _route_sounds(self, method, rest, query, body):
        """Which sample sets are installed, and which events each one has a sound for.

        The list is read from disk rather than hard-coded because it is not fixed:
        the lichess sets ship with the app, while chess.com's are downloaded by
        whoever wants them and are never redistributed.
        """
        if method != "GET":
            raise ApiError("unsupported sounds request", 405)
        folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "assets", "sound")
        labels = {"standard": "Lichess standard", "piano": "Lichess piano",
                  "sfx": "Lichess sfx", "futuristic": "Lichess futuristic",
                  "nes": "Lichess NES", "lisp": "Lichess lisp",
                  "robot": "Lichess robot", "woodland": "Lichess woodland",
                  "chesscom": "Chess.com (downloaded on this machine)"}
        found = []
        if os.path.isdir(folder):
            for name in sorted(os.listdir(folder)):
                manifest = os.path.join(folder, name, "manifest.json")
                if not os.path.isfile(manifest):
                    continue
                try:
                    with open(manifest, encoding="utf-8") as handle:
                        events = json.load(handle)
                except (OSError, ValueError):
                    continue
                found.append({"name": name, "label": labels.get(name, name.title()),
                              "events": sorted(events)})
        return 200, {"sets": found}

    def _route_settings(self, method, rest, query, body):
        if rest and rest[0] in self.SECRET_SETTINGS:
            raise ApiError("read and change that through /api/lichess/account", 403)
        if method == "GET" and rest:
            return 200, {"key": rest[0], "value": self.library.setting(rest[0])}
        if method == "PUT" and rest:
            value = str((body or {}).get("value", ""))
            self.library.setting(rest[0], value)
            return 200, {"key": rest[0], "value": value}
        raise ApiError("unsupported settings request", 405)

"""JSON API over the library.

Every handler returns (status, payload). Payloads are dicts (sent as JSON) or a
(bytes, content_type) tuple for raw downloads.
"""

import json
import os
import re
import threading
import time
import uuid
import urllib.parse

from . import lichess
from .engine import AnnotationJob, Engine, EngineError, LiveAnalysis
from .store import Library
from .study import Study
from . import importers
from . import literature


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status
        self.message = message


class Api:
    def __init__(self, data_dir):
        self.library = Library(data_dir)
        self.study = Study(self.library)
        self.crawler = lichess.MastersCrawler(self.library)
        self.engine = Engine()
        self.live = LiveAnalysis()
        self.annotation = AnnotationJob(self.engine, self.library)
        self.import_lock = threading.Lock()
        self.delete_previews = {}
        # A starter collection for an empty library only. Re-creating one the user has
        # deleted would make "delete collection" look broken after every restart.
        if not self.library.collections():
            self.library.ensure_collection("My games")
        self.import_status = {'running': False, 'label': '', 'done': 0, 'total': 0,
                              'added': 0, 'duplicates': 0, 'skipped': 0, 'error': None, 'batch_id': None}

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
            is_import = method == 'POST' and ((head == 'import' and rest[1:] != ['undo']) or (head == 'games' and len(rest) == 1))
            if is_import:
                label = (body or {}).get('collection') or 'Import'
                batch = self.library.begin_import(label)
                # Imports run inside the request, so the only way a view that has been
                # navigated away from can still report one is to publish progress here.
                self.import_status = {'running': True, 'label': label, 'done': 0, 'total': 0,
                                      'added': 0, 'duplicates': 0, 'skipped': 0, 'error': None, 'batch_id': batch}
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

    def _route_openings(self, method, rest, query, body):
        """Opening names actually present in the library, with the ECO span each covers.

        There is no bundled ECO table and inventing one would be worse than useless, so
        the suggestions and the ranges behind them come from the games already imported.
        """
        if method != 'GET':
            raise ApiError('unsupported openings request', 405)
        term = (query.get('q') or '').strip()
        sql = ["SELECT opening AS name,",
               "MIN(CASE WHEN eco GLOB '[A-E][0-9][0-9]' THEN eco END) AS eco_from,",
               "MAX(CASE WHEN eco GLOB '[A-E][0-9][0-9]' THEN eco END) AS eco_to,",
               "COUNT(*) AS games FROM games WHERE opening IS NOT NULL AND opening <> ''"]
        params = []
        if term:
            sql.append('AND opening LIKE ?')
            params.append('%' + term + '%')
        sql.append('GROUP BY opening ORDER BY games DESC, name LIMIT 40')
        rows = [dict(r) for r in self.library.connect().execute(' '.join(sql), params)]
        return 200, {'openings': rows}

    def _import_progress(self, done, total):
        self.import_status['done'] = done
        self.import_status['total'] = total

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
        return 200, self.library.stats()

    def _route_collections(self, method, rest, query, body):
        if method == "GET" and not rest:
            return 200, {"collections": self.library.collections()}
        if method == "POST" and not rest:
            name = (body or {}).get("name", "").strip()
            if not name:
                raise ApiError("a collection needs a name")
            return 200, {"collection": self.library.ensure_collection(name, (body or {}).get("kind", "games"))}
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
            allowed = {'query','collection','player','white','black','eco','eco_to','result','opening','min_elo','max_elo','outcome','year','sort','event','min_length','max_length','tag','added_from','added_to','position'}
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
            )
        if method == "GET" and rest:
            game = self.library.game(int(rest[0]))
            if not game:
                raise ApiError("no such game", 404)
            return 200, {"game": game}
        if method == "POST" and not rest:
            pgn = (body or {}).get("pgn", "")
            if not pgn.strip():
                raise ApiError("no PGN given")
            result = self.library.add_games(
                pgn,
                collection=(body or {}).get("collection") or "My games",
                source=(body or {}).get("source") or "import",
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
                return 200, importers.chesscom(self.library, user, body.get('collection') or 'chess.com imports',
                                              max(1, min(int(body.get('max', 100)), 2000)))
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
                pgn = lichess.user_games(
                    user,
                    max_games=min(int(body.get("max", 100)), 2000),
                    color=body.get("color"),
                    rated=body.get("rated"),
                    perf=body.get("perf"),
                    since=body.get("since"),
                    token=token,
                )
                result = self.library.add_games(
                    pgn, collection=body.get("collection") or "lichess imports", source="lichess"
                )
                result["user"] = user
                return 200, result
            except lichess.RateLimited as err:
                raise ApiError(
                    "lichess is rate limiting us — try again in %ss" % err.retry_after, 429
                ) from err
            except FileNotFoundError as err:
                raise ApiError("no such lichess user: " + user, 404) from err
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
        key = "facts:" + json.dumps(headers, sort_keys=True)
        cached = self.library.setting(key)
        if cached:
            found = json.loads(cached)
            found["cached"] = True
            return 200, found
        found = literature.game_facts(headers, online=query.get("offline") != "1")
        # Only a real answer is worth keeping; an offline miss must not become permanent.
        if found.get("groups"):
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
        cache_key = db + "|" + (fen or play)
        cached = self.library.cache_explorer(cache_key, db)
        if cached:
            return 200, json.loads(cached)
        try:
            data = lichess.explorer(
                db,
                play=[m for m in play.split(",") if m] if play else None,
                fen=fen,
                moves=int(query.get("moves", 12)),
                top_games=int(query.get("top", 8)),
            )
        except lichess.RateLimited as err:
            raise ApiError("explorer is rate limiting us — try again shortly", 429) from err
        except ConnectionError as err:
            raise ApiError("could not reach the explorer: %s" % err, 503) from err
        self.library.cache_explorer(cache_key, db, json.dumps(data))
        return 200, data

    def _route_masters(self, method, rest, query, body):
        action = rest[0] if rest else ""
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

    def _route_settings(self, method, rest, query, body):
        if method == "GET" and rest:
            return 200, {"key": rest[0], "value": self.library.setting(rest[0])}
        if method == "PUT" and rest:
            value = str((body or {}).get("value", ""))
            self.library.setting(rest[0], value)
            return 200, {"key": rest[0], "value": value}
        raise ApiError("unsupported settings request", 405)

"""The game library: PGN files on disk plus a SQLite index over them.

Layout (DATA_DIR defaults to ./library, or /data on Railway with a volume)::

    library/
      library.db                  index + repertoires + settings
      collections/
        my-games/games.pgn        plain PGN, appended to; still valid PGN
        masters/games.pgn

Games stay in ordinary PGN files you can copy elsewhere or open in any other
program; the database only remembers where each one starts and ends.
"""

import os
import sqlite3
import threading
import time
import hashlib
import re
import uuid
from datetime import datetime, timedelta

from . import openings
from . import pgnutil

SCHEMA = """
CREATE TABLE IF NOT EXISTS collections (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  kind TEXT NOT NULL DEFAULT 'games',
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS games (
  id INTEGER PRIMARY KEY,
  collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
  path TEXT NOT NULL,
  byte_offset INTEGER NOT NULL,
  byte_length INTEGER NOT NULL,
  white TEXT, black TEXT,
  white_elo INTEGER, black_elo INTEGER,
  result TEXT, date TEXT, event TEXT, site TEXT, round TEXT,
  eco TEXT, opening TEXT, variant TEXT, time_control TEXT,
  fen TEXT, ply_count INTEGER,
  first_moves TEXT,
  source TEXT,
  source_id TEXT,
  event_date TEXT, event_type TEXT,
  white_team TEXT, black_team TEXT,
  white_title TEXT, black_title TEXT,
  white_fide_id TEXT, black_fide_id TEXT,
  source_title TEXT, variation TEXT,
  speed TEXT, rated INTEGER,
  added_at INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS games_source_id ON games(source_id) WHERE source_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS games_collection ON games(collection_id);
-- Browsing a collection means filtering by it and ordering by date. With only the
-- single-column index SQLite gathers every match and sorts it to hand back thirty
-- rows: thirty-seven seconds on a ten-million-game collection. Carrying the sort key
-- in the index turns that into a range scan that stops after thirty.
CREATE INDEX IF NOT EXISTS games_collection_date ON games(collection_id, date, id);
CREATE INDEX IF NOT EXISTS games_white ON games(white);
CREATE INDEX IF NOT EXISTS games_black ON games(black);
CREATE INDEX IF NOT EXISTS games_eco ON games(eco);
CREATE INDEX IF NOT EXISTS games_date ON games(date);
CREATE INDEX IF NOT EXISTS games_event ON games(event);
CREATE INDEX IF NOT EXISTS games_opening ON games(opening);

-- A game belongs to the collection it was first imported into, and may be linked
-- into others. Importing a game that is already in the library used to drop it
-- silently as a duplicate, which lost the fact that it belongs in both places;
-- now that fact is recorded here instead. One row of PGN, many shelves.
CREATE TABLE IF NOT EXISTS game_collections (
  game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
  collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
  added_at INTEGER NOT NULL,
  PRIMARY KEY (game_id, collection_id)
);
CREATE INDEX IF NOT EXISTS game_collections_collection ON game_collections(collection_id);
-- Which collections are attached bases rather than imported games. Deriving this by
-- scanning games for source='reference' costs a full table scan — eight seconds on ten
-- million rows, every time the Master games view opens. It is two rows of fact; it gets
-- a table. Counting each base's games then goes through games(collection_id).
-- One row per opening name in the library, with the ECO span it covers and how many
-- games carry it. Deriving this with GROUP BY on demand reads every row — thirty-seven
-- seconds on ten million games, per keystroke of the opening box. It changes only when
-- games are imported, so it is computed then and read instantly after.
CREATE TABLE IF NOT EXISTS opening_summary (
  name TEXT PRIMARY KEY,
  eco_from TEXT,
  eco_to TEXT,
  games INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS reference_bases (
  collection_id INTEGER PRIMARY KEY REFERENCES collections(id) ON DELETE CASCADE,
  path TEXT NOT NULL,
  attached_at INTEGER NOT NULL,
  -- 0 while the scan is running. A scan of ten million games can be interrupted — the
  -- machine runs short of memory, the app is closed — and a base that holds some
  -- unknown fraction of its file must say so rather than look finished.
  complete INTEGER NOT NULL DEFAULT 0,
  -- How far into the PGN the last committed batch reached, so an interrupted scan
  -- carries on from there instead of starting the eight gigabytes again.
  scanned_bytes INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS repertoires (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  color TEXT NOT NULL,
  data TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS explorer_cache (
  fen TEXT PRIMARY KEY,
  db TEXT NOT NULL,
  body TEXT NOT NULL,
  fetched_at INTEGER NOT NULL
);
"""


def slugify(name):
    keep = "".join(c if c.isalnum() or c in "-_ " else " " for c in str(name))
    slug = "-".join(keep.lower().split()).strip("-_")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "collection"


class Library:
    def __init__(self, data_dir):
        self.dir = os.path.abspath(data_dir)
        self.collections_dir = os.path.join(self.dir, "collections")
        os.makedirs(self.collections_dir, exist_ok=True)
        self.db_path = os.path.join(self.dir, "library.db")
        self._local = threading.local()
        self._write_lock = threading.Lock()
        self._active_imports = set()
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS import_batches (
                  id TEXT PRIMARY KEY, created_at INTEGER, label TEXT, undone INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS import_members (
                  batch TEXT REFERENCES import_batches(id),
                  game_id INTEGER REFERENCES games(id) ON DELETE CASCADE,
                  PRIMARY KEY(batch, game_id));
            ''')
            # A library that attached a base before the scan tracked completeness has
            # the table without the column, and CREATE TABLE IF NOT EXISTS will not add
            # it. Existing bases are taken as finished: they were, under the old rule.
            # Sorting by rating used to sort on an expression, and an expression is
            # something no index can answer: ten million rows gathered and sorted to
            # return thirty, thirty-seven seconds a go. A generated column is the same
            # expression given a name, so it can be indexed — and being generated it
            # cannot drift from the two columns it reads, and no insert has to set it.
            # table_info hides generated columns; table_xinfo is the one that lists them,
            # and asking the wrong one adds the column a second time on every launch.
            if 'top_elo' not in {r[1] for r in conn.execute('PRAGMA table_xinfo(games)')}:
                conn.execute('ALTER TABLE games ADD COLUMN top_elo INTEGER '
                             'GENERATED ALWAYS AS (MAX(COALESCE(white_elo,0),'
                             'COALESCE(black_elo,0))) VIRTUAL')
            conn.execute('CREATE INDEX IF NOT EXISTS games_top_elo ON games(top_elo)')
            registry = {r[1] for r in conn.execute('PRAGMA table_info(reference_bases)')}
            if 'complete' not in registry:
                conn.execute('ALTER TABLE reference_bases ADD COLUMN complete INTEGER NOT NULL DEFAULT 1')
            if 'scanned_bytes' not in registry:
                conn.execute('ALTER TABLE reference_bases ADD COLUMN scanned_bytes INTEGER NOT NULL DEFAULT 0')
            columns = {r[1] for r in conn.execute('PRAGMA table_info(games)')}
            # ChessBase metadata, added to existing libraries in place. Every one is
            # optional: a PGN that carries none of them stores empty strings.
            for name, kind in [('annotator','TEXT'),('termination','TEXT'),('has_annotations','INTEGER'),
                               ('event_date','TEXT'),('event_type','TEXT'),
                               ('white_team','TEXT'),('black_team','TEXT'),
                               ('white_title','TEXT'),('black_title','TEXT'),
                               ('white_fide_id','TEXT'),('black_fide_id','TEXT'),
                               ('source_title','TEXT'),('variation','TEXT'),
                               ('speed','TEXT'),('rated','INTEGER')]:
                if name not in columns:
                    conn.execute('ALTER TABLE games ADD COLUMN '+name+' '+kind)
            if 'signature' not in columns:
                conn.execute('ALTER TABLE games ADD COLUMN signature TEXT')
            conn.execute('CREATE INDEX IF NOT EXISTS games_signature ON games(signature)')
            conn.execute('CREATE INDEX IF NOT EXISTS games_event_date ON games(event_date)')
            conn.execute('CREATE INDEX IF NOT EXISTS games_speed ON games(speed)')
            # These two backfills exist for libraries written before the columns did.
            # Neither column is indexed, so merely ASKING whether there is anything to
            # do is a full table scan — fifty seconds on a ten-million-game library,
            # paid on every single launch to be told "nothing". A one-time job is
            # recorded as done when it is done, and never asked about again.
            self._backfill_once(conn, 'chessbase_columns', '''SELECT id FROM games
                WHERE has_annotations IS NULL OR event_date IS NULL OR speed IS NULL''',
                lambda cx, ident, text: self._update_extra_metadata(cx, ident, text))
            self._backfill_once(conn, 'game_signatures',
                'SELECT id FROM games WHERE signature IS NULL',
                lambda cx, ident, text: cx.execute('UPDATE games SET signature=? WHERE id=?',
                                                   (self.signature(text), ident)))

    def _backfill_once(self, conn, name, finder, apply):
        """Run a one-time repair over old rows, and remember that it ran.

        The marker is written whether or not anything needed repairing, because the
        expensive part is the search, not the repair. Rows written from now on carry
        these columns already, so there is nothing for a second run to find.
        """
        done = conn.execute('SELECT value FROM settings WHERE key=?',
                            ('backfill:' + name,)).fetchone()
        if done:
            return
        for row in conn.execute(finder).fetchall():
            text = self.game_pgn(row['id'])
            if text:
                apply(conn, row['id'], text)
        conn.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', ('backfill:' + name, '1'))

    @staticmethod
    def _update_extra_metadata(conn, ident, text):
        meta = pgnutil.describe(text)
        conn.execute('''UPDATE games SET annotator=?,termination=?,has_annotations=?,
            event_date=?,event_type=?,white_team=?,black_team=?,white_title=?,black_title=?,
            white_fide_id=?,black_fide_id=?,source_title=?,variation=?,speed=?,rated=? WHERE id=?''',
            (meta['annotator'],meta['termination'],meta['has_annotations'],
             meta['event_date'],meta['event_type'],meta['white_team'],meta['black_team'],
             meta['white_title'],meta['black_title'],meta['white_fide_id'],
             meta['black_fide_id'],meta['source_title'],meta['variation'],
             meta['speed'],meta['rated'],ident))

    @staticmethod
    def signature(text):
        tags = pgnutil.headers(text)
        identity = '|'.join(tags.get(k, '') for k in ('White','Black','Date','Event','Round','Result','FEN'))
        return hashlib.sha256((identity+'|'+' '.join(pgnutil.moves(text))).encode('utf-8')).hexdigest()

    # ---------- plumbing ----------

    def connect(self):
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    def close(self):
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # ---------- collections ----------

    def collections(self):
        rows = self.connect().execute(
            """SELECT c.id, c.name, c.kind, c.created_at,
                      (SELECT COUNT(*) FROM games g WHERE g.collection_id = c.id)
                      + (SELECT COUNT(*) FROM game_collections l WHERE l.collection_id = c.id) AS games,
                      (SELECT COUNT(*) FROM game_collections l WHERE l.collection_id = c.id) AS linked
               FROM collections c ORDER BY c.name"""
        ).fetchall()
        result = [dict(r) for r in rows]
        db = self.connect()
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='positions'").fetchone():
            # Driven from positions, which holds the games that ARE indexed, rather than
            # from games, which holds every game there is. Asking "is this one indexed?"
            # of ten million games is ten million probes; asking the index what it holds
            # is one pass over the few thousand rows that exist.
            counts = dict(db.execute('''SELECT collection_id, COUNT(*) FROM (
                SELECT g.collection_id AS collection_id, g.id AS game_id
                FROM (SELECT DISTINCT game_id FROM positions) p JOIN games g ON g.id = p.game_id
                UNION
                SELECT l.collection_id, l.game_id FROM game_collections l
                WHERE l.game_id IN (SELECT game_id FROM positions)
            ) GROUP BY collection_id'''))
            for item in result:
                item['indexed_games'] = counts.get(item['id'], 0)
        return result

    def collection(self, ident):
        conn = self.connect()
        if isinstance(ident, int) or str(ident).isdigit():
            row = conn.execute("SELECT * FROM collections WHERE id = ?", (int(ident),)).fetchone()
        else:
            row = conn.execute("SELECT * FROM collections WHERE name = ?", (ident,)).fetchone()
        return dict(row) if row else None

    def ensure_collection(self, name, kind="games"):
        existing = self.collection(name)
        if existing:
            return existing
        with self._write_lock:
            conn = self.connect()
            conn.execute(
                "INSERT OR IGNORE INTO collections (name, kind, created_at) VALUES (?, ?, ?)",
                (name, kind, int(time.time())),
            )
            conn.commit()
        os.makedirs(os.path.join(self.collections_dir, slugify(name)), exist_ok=True)
        return self.collection(name)

    def rename_collection(self, ident, name):
        """Give a collection a new name, taking its PGN folder with it.

        Games record where their text lives as a path under the library, so the folder
        move and the paths have to travel together or the games stop being readable. If
        the destination folder is already taken the files stay where they are: the games
        still read correctly from the old folder, and only new imports land under the new
        name.
        """
        info = self.collection(ident)
        if not info:
            return None
        name = (name or "").strip()
        if not name:
            raise ValueError("a collection needs a name")
        clash = self.collection(name)
        if clash and clash["id"] != info["id"]:
            raise ValueError("another collection is already called " + name)
        old_slug, new_slug = slugify(info["name"]), slugify(name)
        with self._write_lock:
            conn = self.connect()
            conn.execute("UPDATE collections SET name = ? WHERE id = ?", (name, info["id"]))
            old_dir = os.path.join(self.collections_dir, old_slug)
            new_dir = os.path.join(self.collections_dir, new_slug)
            if new_slug != old_slug and os.path.isdir(old_dir) and not os.path.exists(new_dir):
                os.rename(old_dir, new_dir)
                # Stored paths were written with whichever separator built them, so both
                # spellings are rewritten rather than guessed at.
                for sep in ("/", os.sep):
                    old_rel, new_rel = "collections" + sep + old_slug + sep, "collections" + sep + new_slug + sep
                    conn.execute("UPDATE games SET path = ? || substr(path, ?) WHERE substr(path, 1, ?) = ?",
                                 (new_rel, len(old_rel) + 1, len(old_rel), old_rel))
            conn.commit()
        os.makedirs(os.path.join(self.collections_dir, new_slug), exist_ok=True)
        return self.collection(info["id"])

    def collect_into(self, name, filters, kind="games"):
        """Put every game matching a search onto one shelf, without copying it.

        The master collections are built this way. PGN Mentor ships one archive per
        player, so a collection for one opening of that player's is the archive filtered:
        the games keep living in the collection they were imported into and are linked
        onto the new shelf, rather than being stored a second time.
        """
        info = self.ensure_collection(name, kind)
        found = self.search(limit=200000, **filters)
        linked = 0
        with self._write_lock:
            conn = self.connect()
            for game in found["games"]:
                if game["collection_id"] == info["id"]:
                    continue
                linked += conn.execute("INSERT OR IGNORE INTO game_collections VALUES (?,?,?)",
                                       (game["id"], info["id"], int(time.time()))).rowcount
            conn.commit()
        return {"collection": info["name"], "id": info["id"],
                "matched": len(found["games"]), "linked": linked}

    def collections_for(self, game_ids):
        """Every collection each of these games sits in, owner first then links."""
        ids = [int(i) for i in game_ids]
        if not ids:
            return {}
        marks = ",".join("?" * len(ids))
        rows = self.connect().execute(
            "SELECT g.id AS game_id, c.id, c.name, c.kind, 1 AS owner "
            "FROM games g JOIN collections c ON c.id = g.collection_id "
            "WHERE g.id IN (" + marks + ") "
            "UNION ALL "
            "SELECT l.game_id, c.id, c.name, c.kind, 0 AS owner "
            "FROM game_collections l JOIN collections c ON c.id = l.collection_id "
            "WHERE l.game_id IN (" + marks + ")",
            ids + ids).fetchall()
        out = {}
        for row in rows:
            out.setdefault(row["game_id"], []).append(
                {"id": row["id"], "name": row["name"], "kind": row["kind"],
                 "owner": bool(row["owner"])})
        for entries in out.values():
            entries.sort(key=lambda c: (not c["owner"], c["name"].lower()))
        return out

    def link_game(self, game_id, collection):
        """Shelve an existing game in another collection. Returns False if it is already there."""
        info = self.collection(collection)
        if not info:
            raise ValueError("Choose an existing collection")
        row = self.connect().execute("SELECT collection_id FROM games WHERE id=?",
                                     (int(game_id),)).fetchone()
        if not row:
            raise ValueError("No such game")
        if row["collection_id"] == info["id"]:
            return False
        with self._write_lock, self.connect() as db:
            cur = db.execute("INSERT OR IGNORE INTO game_collections VALUES (?,?,?)",
                             (int(game_id), info["id"], int(time.time())))
        return bool(cur.rowcount)

    def unlink_game(self, game_id, collection):
        """Take a game off a shelf it was linked onto. The owning collection is not a link."""
        info = self.collection(collection)
        if not info:
            raise ValueError("Choose an existing collection")
        with self._write_lock, self.connect() as db:
            cur = db.execute("DELETE FROM game_collections WHERE game_id=? AND collection_id=?",
                             (int(game_id), info["id"]))
        return bool(cur.rowcount)

    def name_openings(self, collection=None):
        """Fill in opening names for games imported before, or without, an Opening tag."""
        db = self.connect()
        sql = "SELECT id, eco, opening, first_moves, fen FROM games WHERE opening IS NULL OR opening = ''"
        params = []
        if collection:
            info = self.collection(collection)
            if not info:
                return {"named": 0, "checked": 0}
            sql += " AND collection_id = ?"
            params.append(info["id"])
        rows = db.execute(sql, params).fetchall()
        updates = []
        for row in rows:
            found = openings.name_for({"opening": row["opening"], "eco": row["eco"], "fen": row["fen"]},
                                      (row["first_moves"] or "").split())
            if found:
                updates.append((found["eco"], found["opening"], row["id"]))
        if updates:
            with self._write_lock, db:
                db.executemany("UPDATE games SET eco = ?, opening = ? WHERE id = ?", updates)
        return {"named": len(updates), "checked": len(rows)}

    def delete_collection(self, ident, remove_files=False):
        info = self.collection(ident)
        if not info:
            return False
        with self._write_lock:
            conn = self.connect()
            # A game this collection owns but another collection also holds must not
            # disappear with it. Hand it to the other collection instead, and drop the
            # link that has just become its ownership.
            rescued = conn.execute(
                """SELECT l.game_id, MIN(l.collection_id) AS new_owner
                   FROM game_collections l JOIN games g ON g.id = l.game_id
                   WHERE g.collection_id = ? AND l.collection_id <> ?
                   GROUP BY l.game_id""", (info["id"], info["id"])).fetchall()
            for row in rescued:
                conn.execute("UPDATE games SET collection_id = ? WHERE id = ?",
                             (row["new_owner"], row["game_id"]))
                conn.execute("DELETE FROM game_collections WHERE game_id = ? AND collection_id = ?",
                             (row["game_id"], row["new_owner"]))
            conn.execute("DELETE FROM games WHERE collection_id = ?", (info["id"],))
            conn.execute("DELETE FROM collections WHERE id = ?", (info["id"],))
            conn.commit()
        if remove_files:
            folder = os.path.join(self.collections_dir, slugify(info["name"]))
            if os.path.isdir(folder):
                for entry in os.listdir(folder):
                    os.remove(os.path.join(folder, entry))
                os.rmdir(folder)
        return True

    def _pgn_path(self, collection_name):
        folder = os.path.join(self.collections_dir, slugify(collection_name))
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, "games.pgn")

    # ---------- importing ----------

    def add_games(self, pgn_text, collection="My games", source="import", skip_duplicates=True,
                  kind="games"):
        """Append every game in `pgn_text` to a collection. Returns a summary dict.

        `kind` only applies when the collection is being created: a collection that
        already exists keeps whatever kind it was given, so importing into it never
        moves somebody's games out of the database behind their back.
        """
        info = self.ensure_collection(collection, kind or "games")
        texts = pgnutil.split_games(pgn_text)
        if not texts:
            return {"added": 0, "duplicates": 0, "skipped": 0, "collection": info["name"]}

        path = self._pgn_path(info["name"])
        rel = os.path.relpath(path, self.dir)
        added = duplicates = skipped = linked = 0
        rows = []

        with self._write_lock:
            conn = self.connect()
            known = set()
            if skip_duplicates:
                known = {
                    r[0]
                    for r in conn.execute(
                        "SELECT source_id FROM games WHERE source_id IS NOT NULL"
                    ).fetchall()
                }

            report = getattr(self, "on_progress", None)
            with open(path, "a", encoding="utf-8", newline="\n") as handle:
                for position, text in enumerate(texts):
                    # Coarse enough that a 100k-game archive does not pay for a callback a game.
                    if report and position % 25 == 0:
                        report(position, len(texts))
                    meta = pgnutil.describe(text)
                    if meta['variant'].lower() not in ('standard', 'chess', 'from position'):
                        skipped += 1
                        continue
                    if not meta["ply_count"] and not meta["fen"]:
                        skipped += 1
                        continue
                    signature = self.signature(text)
                    if skip_duplicates and ((meta["source_id"] and meta["source_id"] in known) or
                        signature in known or conn.execute('SELECT 1 FROM games WHERE signature=? LIMIT 1', (signature,)).fetchone()):
                        # The same game arriving for a second collection is not noise:
                        # it belongs on both shelves, so link it rather than drop it.
                        existing = conn.execute(
                            'SELECT id, collection_id FROM games WHERE signature=? '
                            'OR (source_id IS NOT NULL AND source_id=?) LIMIT 1',
                            (signature, meta["source_id"])).fetchone()
                        if existing and existing["collection_id"] != info["id"]:
                            if conn.execute(
                                'INSERT OR IGNORE INTO game_collections VALUES (?,?,?)',
                                (existing["id"], info["id"], int(time.time()))).rowcount:
                                linked += 1
                            else:
                                duplicates += 1
                        else:
                            duplicates += 1
                        continue
                    # A file carrying only an ECO code would otherwise show up with no
                    # opening name at all; its own Opening tag is never overwritten.
                    named = openings.name_for(meta, meta["first_moves"].split())
                    if named:
                        meta["eco"], meta["opening"] = named["eco"], named["opening"]
                    if meta["source_id"]:
                        known.add(meta["source_id"])
                    known.add(signature)
                    meta['signature'] = signature

                    blob = text.strip() + "\n\n"
                    offset = handle.tell()
                    handle.write(blob)
                    rows.append((info["id"], rel, offset, len(blob.encode("utf-8")), meta, source))
                    added += 1

            for collection_id, relpath, offset, length, meta, src in rows:
                cursor = conn.execute(
                    """INSERT OR IGNORE INTO games
                       (collection_id, path, byte_offset, byte_length, white, black,
                        white_elo, black_elo, result, date, event, site, round, eco,
                        opening, variant, time_control, fen, ply_count, first_moves,
                        source, source_id, added_at, signature)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        collection_id, relpath, offset, length,
                        meta["white"], meta["black"], meta["white_elo"], meta["black_elo"],
                        meta["result"], meta["date"], meta["event"], meta["site"], meta["round"],
                        meta["eco"], meta["opening"], meta["variant"], meta["time_control"],
                        meta["fen"], meta["ply_count"], meta["first_moves"],
                        src, meta["source_id"], int(time.time()), meta['signature'],
                    ),
                )
                batch = getattr(self._local, 'batch', None)
                if cursor.rowcount:
                    conn.execute('''UPDATE games SET annotator=?,termination=?,has_annotations=?,
                        event_date=?,event_type=?,white_team=?,black_team=?,white_title=?,black_title=?,
                        white_fide_id=?,black_fide_id=?,source_title=?,variation=?,speed=?,rated=? WHERE id=?''',
                        (meta['annotator'],meta['termination'],meta['has_annotations'],
                         meta['event_date'],meta['event_type'],meta['white_team'],meta['black_team'],
                         meta['white_title'],meta['black_title'],meta['white_fide_id'],
                         meta['black_fide_id'],meta['source_title'],meta['variation'],
                         meta['speed'],meta['rated'],cursor.lastrowid))
                if batch and cursor.rowcount:
                    conn.execute('INSERT INTO import_members VALUES (?,?)', (batch, cursor.lastrowid))
            self.merge_openings(conn, [(meta['opening'], meta['eco'])
                                       for _, _, _, _, meta, _ in rows])
            conn.commit()

        if report:
            report(len(texts), len(texts))
        return {
            "added": added,
            "duplicates": duplicates,
            "skipped": skipped,
            "linked": linked,
            "collection": info["name"],
            "collection_id": info["id"],
        }

    # ---------- reading ----------

    def game_pgn(self, game_id):
        row = self.connect().execute(
            "SELECT path, byte_offset, byte_length FROM games WHERE id = ?", (game_id,)
        ).fetchone()
        if not row:
            return None
        full = os.path.join(self.dir, row["path"])
        if not os.path.exists(full):
            return None
        with open(full, "rb") as handle:
            handle.seek(row["byte_offset"])
            return handle.read(row["byte_length"]).decode("utf-8", "replace").strip()

    def game(self, game_id):
        row = self.connect().execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
        if not row:
            return None
        out = dict(row)
        out["pgn"] = self.game_pgn(game_id)
        out["collections"] = self.collections_for([game_id]).get(int(game_id), [])
        return out

    SORTS = {
        "date": "date DESC, id DESC",
        "date_asc": "date ASC, id ASC",
        "white": "white COLLATE NOCASE ASC",
        "black": "black COLLATE NOCASE ASC",
        "elo": "top_elo DESC",
        "added": "added_at DESC, id DESC",
        "length": "ply_count DESC",
        "event": "event COLLATE NOCASE ASC, date DESC",
        "annotator": "annotator COLLATE NOCASE ASC, id DESC",
        "eco": "eco ASC, date DESC",
        # ChessBase sorts by the tournament, not by the individual game's date.
        "event_date": "COALESCE(NULLIF(event_date,''), date) DESC, event COLLATE NOCASE ASC, round ASC",
        "round": "event COLLATE NOCASE ASC, LENGTH(round) ASC, round ASC",
        "result": "result ASC, date DESC",
        "opening": "opening COLLATE NOCASE ASC, eco ASC",
    }

    def search(self, query=None, collection=None, player=None, white=None, black=None,
               eco=None, result=None, opening=None, min_elo=None, year=None,
               sort="date", limit=100, offset=0, event=None, min_length=None, max_length=None, tag=None,
               added_from=None, added_to=None, position=None, eco_to=None, max_elo=None, outcome=None,
               player_prefix=None, white_prefix=None, black_prefix=None, event_prefix=None,
               annotator=None, site=None, round=None, termination=None, annotated=None,
               date_from=None, date_to=None, source=None, category=None,
               white_min_elo=None, white_max_elo=None, black_min_elo=None, black_max_elo=None,
               kind=None, team=None, title=None, fide_id=None, source_title=None,
               variation=None, event_type=None, event_date_from=None, event_date_to=None):
        where, params = [], []

        # Collections carry a kind: ordinary games, saved study positions, or imported
        # opening trees. The game database asks for 'games' so studies and repertoire
        # trees stay out of it; every other caller can still reach them by naming a kind
        # or by passing none at all, which searches the whole library.
        if kind:
            where.append("(collection_id IN (SELECT id FROM collections WHERE kind = ?)"
                         " OR id IN (SELECT l.game_id FROM game_collections l"
                         " JOIN collections c ON c.id = l.collection_id WHERE c.kind = ?))")
            params.extend([str(kind), str(kind)])

        if collection:
            info = self.collection(collection)
            if not info:
                return {"total": 0, "games": []}
            # A collection holds the games it owns plus any linked onto it. Asking for
            # both with an OR costs the index: SQLite cannot walk one index for a query
            # that reaches into two, so it gathers every match and sorts — thirty-seven
            # seconds to show thirty rows of a ten-million-game collection. Most
            # collections have no links at all, and for those the question is simply
            # not asked.
            linked = self.connect().execute(
                'SELECT 1 FROM game_collections WHERE collection_id=? LIMIT 1',
                (info['id'],)).fetchone()
            if linked:
                where.append("(collection_id = ? OR id IN "
                             "(SELECT game_id FROM game_collections WHERE collection_id = ?))")
                params.extend([info["id"], info["id"]])
            else:
                where.append("collection_id = ?")
                params.append(info["id"])
        if query:
            # Eleven LIKE '%term%' columns cannot use an index, so every row is read:
            # thirty-nine seconds on a ten-million-game library. That is affordable on
            # an ordinary one, where it also matches a forename in the middle of
            # "Carlsen, Magnus", so the honest answer depends on which library this is.
            for term in query.split():
                if self.is_large():
                    where.append(self._fast_text_clause(term, params))
                else:
                    like = "%" + term + "%"
                    where.append("(white LIKE ? OR black LIKE ? OR event LIKE ? OR opening LIKE ? "
                                 "OR eco LIKE ? OR annotator LIKE ? OR site LIKE ? OR white_team LIKE ? "
                                 "OR black_team LIKE ? OR source_title LIKE ? OR variation LIKE ?)")
                    params.extend([like] * 11)
        # "Kasparov, Garry" and ChessBase's "Kasparov,Garry" name the same person, so
        # both spellings are searched however the reader typed it.
        def spellings(name):
            name = name.strip()
            variants = {name, name.replace(", ", ","), re.sub(r",\s*", ", ", name)}
            return ["%" + v + "%" for v in variants if v]

        # "%Carlsen%" cannot use an index, so on a ten-million-game base it reads every
        # row — about thirty-five seconds a search. A surname is a prefix, and a prefix
        # is a range an index answers instantly, so the modules that ask for a surname
        # ask for a prefix. `player` keeps its substring meaning for the database's own
        # free-text box, where matching a forename mid-string is the point.
        #
        # The ranges go in as a subquery of ids rather than as an OR of comparisons: a
        # query carrying two ranges leaves SQLite to pick one index, and it reliably
        # picks ECO — which on a whole-alphabet range is every row. Resolving the names
        # first through their own covering indexes, then probing by rowid, is the plan
        # that stays fast when a search also narrows by opening and by year.
        def prefixes(name):
            name = name.strip()
            forms = {name, name[:1].upper() + name[1:], name.replace(", ", ",")}
            return [(f, f + "\uffff") for f in forms if f]

        for columns, value in ((("white", "black"), player_prefix),
                               (("white",), white_prefix), (("black",), black_prefix),
                               (("event",), event_prefix)):
            if not value:
                continue
            reads = []
            for column in columns:
                for low, high in prefixes(value):
                    reads.append("SELECT id FROM games WHERE %s >= ? AND %s < ?" % (column, column))
                    params.extend([low, high])
            where.append("id IN (" + " UNION ".join(reads) + ")")
        if player:
            clause = " OR ".join(["white LIKE ? OR black LIKE ?"] * len(spellings(player)))
            where.append("(" + clause + ")")
            for like in spellings(player):
                params.extend([like, like])
        for column, value in (("white", white), ("black", black)):
            if value:
                where.append("(" + " OR ".join([column + " LIKE ?"] * len(spellings(value))) + ")")
                params.extend(spellings(value))
        if eco:
            where.append("eco LIKE ?")
            params.append(eco.upper() + "%")
        if opening:
            # The names are already gathered in opening_summary — a few hundred rows
            # rather than ten million — so the substring match happens there and the
            # games are found by an indexed equality. Same answer, without the scan.
            # The summary only ever gains names, so it cannot lose a match; a library
            # that has never imported through add_games falls back to the old way.
            if self.connect().execute('SELECT 1 FROM opening_summary LIMIT 1').fetchone():
                where.append('opening IN (SELECT name FROM opening_summary WHERE name LIKE ?)')
            else:
                where.append('opening LIKE ?')
            params.append("%" + opening + "%")
        if result:
            where.append("result = ?")
            params.append(result)
        if min_elo:
            # "either player at least this" is what top_elo already stores, and unlike
            # the two-column OR it is a column an index can range over.
            where.append("top_elo >= ?")
            params.append(int(min_elo))
        if max_elo:
            # A ceiling means nobody above it; an unrated player is not treated as 9999.
            where.append("(COALESCE(white_elo,0) <= ? AND COALESCE(black_elo,0) <= ?)")
            params.extend([int(max_elo), int(max_elo)])
        if outcome == 'draw':
            where.append("result = '1/2-1/2'")
        elif outcome in ('win', 'loss'):
            # Win and loss only mean something from somebody's side of the board.
            won, lost = ('1-0', '0-1') if outcome == 'win' else ('0-1', '1-0')
            if white:
                where.append("result = ?")
                params.append(won)
            elif black:
                where.append("result = ?")
                params.append(lost)
            elif player:
                like = "%" + player.strip() + "%"
                where.append("((white LIKE ? AND result = ?) OR (black LIKE ? AND result = ?))")
                params.extend([like, won, like, lost])
        if year:
            where.append("date LIKE ?")
            params.append(str(year) + "%")
        if event:
            where.append('event LIKE ?')
            params.append('%'+event+'%')
        for column,value in [('annotator',annotator),('site',site),('round',round),('termination',termination),
                             ('source',source),('source_title',source_title),('variation',variation),
                             ('event_type',event_type)]:
            if value:
                where.append(column+' LIKE ?')
                params.append('%'+value+'%')
        # ChessBase tags one side at a time; a reader looking for a club or a title
        # means "either player", which is the only reading that is ever useful.
        for low, high, value in [('white_team','black_team',team),
                                 ('white_title','black_title',title),
                                 ('white_fide_id','black_fide_id',fide_id)]:
            if value:
                where.append('(%s LIKE ? OR %s LIKE ?)' % (low, high))
                params.extend(['%'+str(value)+'%'] * 2)
        for value, operator in [(event_date_from,'>='), (event_date_to,'<=')]:
            if value:
                date = datetime.strptime(value,'%Y-%m-%d').strftime('%Y.%m.%d')
                where.append("COALESCE(NULLIF(event_date,''), date) "+operator+' ?')
                params.append(date)
        if annotated in ('0','1',0,1):
            where.append('has_annotations=?')
            params.append(int(annotated))
        for column,low,high in [('white_elo',white_min_elo,white_max_elo),('black_elo',black_min_elo,black_max_elo)]:
            for value,op in [(low,'>='),(high,'<=')]:
                if value is not None and value!='':
                    where.append(column+' '+op+' ?')
                    params.append(int(value))
        for value,op in [(date_from,'>='),(date_to,'<=')]:
            if value:
                date=datetime.strptime(value,'%Y-%m-%d').strftime('%Y.%m.%d')
                where.append('date '+op+' ?')
                params.append(date)
        if category:
            where.append('collection_id IN (SELECT cf.collection_id FROM collection_folders cf JOIN folders f ON f.id=cf.folder_id WHERE f.category=?)')
            params.append(category)
        if min_length:
            where.append('ply_count >= ?')
            params.append(int(min_length))
        if max_length:
            where.append('ply_count <= ?')
            params.append(int(max_length))
        if tag:
            where.append('id IN (SELECT game_id FROM game_tags WHERE tag=?)')
            params.append(tag)
        for value, operator, extra in ((added_from, '>=', 0), (added_to, '<', 1)):
            if value:
                stamp = (datetime.strptime(value, '%Y-%m-%d') + timedelta(days=extra)).timestamp()
                where.append('added_at '+operator+' ?')
                params.append(int(stamp))
        if eco_to:
            # Big bases subdivide ECO: Lumbras writes B90a, B92d, E04a. An inclusive
            # "eco <= 'B99'" sorts every one of those above the bound and drops the
            # whole final bucket — and "B90 through B90" then matches nothing at all.
            # Reaching past the last suffix keeps a three-letter range meaning what it
            # says, whichever spelling the base uses.
            where.append('eco < ?')
            params.append(eco_to.upper() + '￿')
            if eco:
                index = where.index('eco LIKE ?')
                where[index] = 'eco >= ?'
                # Each clause before ECO may have multiple parameters.
                param_index = sum(clause.count('?') for clause in where[:index])
                params[param_index] = eco.upper()
        if position:
            from .chess import Chess
            where.append('id IN (SELECT game_id FROM positions WHERE hash=?)')
            params.append(Chess(position).key())

        clause = (" WHERE " + " AND ".join(where)) if where else ""
        order = self.SORTS.get(sort, self.SORTS["date"])
        conn = self.connect()
        total = conn.execute("SELECT COUNT(*) FROM games" + clause, params).fetchone()[0]
        rows = conn.execute(
            "SELECT id, collection_id, white, black, white_elo, black_elo, result, date, "
            "event, site, round, annotator, termination, has_annotations, eco, opening, ply_count, "
            "source, first_moves, added_at, signature, path, byte_offset, byte_length, "
            "event_date, event_type, white_team, black_team, white_title, black_title, "
            "white_fide_id, black_fide_id, source_title, variation "
            "FROM games" + clause + " ORDER BY " + order + " LIMIT ? OFFSET ?",
            params + [int(limit), int(offset)],
        ).fetchall()
        games = [dict(r) for r in rows]
        memberships = self.collections_for([g["id"] for g in games])
        for game in games:
            game["collections"] = memberships.get(game["id"], [])
        return {"total": total, "games": games}

    REFERENCE_DIR = 'reference'

    def references(self):
        """The reference bases attached to this library, and their PGNs' health.

        A base is attached, not imported: its rows carry a path into a file that lives
        outside any collection folder. So the honest answer includes whether that file
        is still where the rows say it is — a base whose PGN has moved is a collection
        of games that cannot be opened, and the reader should be told which.
        """
        db = self.connect()
        rows = db.execute(
            """SELECT r.collection_id AS id, c.name, r.path, r.complete, r.scanned_bytes
               FROM reference_bases r JOIN collections c ON c.id = r.collection_id
               ORDER BY r.attached_at""").fetchall()
        out = []
        for row in rows:
            full = os.path.join(self.dir, row['path'])
            games = db.execute('SELECT COUNT(*) FROM games WHERE collection_id=?',
                               (row['id'],)).fetchone()[0]
            size = os.path.getsize(full) if os.path.isfile(full) else 0
            out.append(dict(id=row['id'], name=row['name'], games=games,
                            path=row['path'], missing=not os.path.isfile(full),
                            complete=bool(row['complete']), bytes=size,
                            scanned_bytes=row['scanned_bytes'],
                            scanned_pct=round(100 * row['scanned_bytes'] / size, 1) if size else 0))
        out.sort(key=lambda base: -base['games'])
        return out

    def attachable(self, minimum_bytes=50 * 1024 * 1024):
        """Big PGNs in the library's reference folder that nothing has attached yet.

        This is what lets the app notice a gigabase and offer to use it, instead of
        making somebody find a file picker for something already sitting in place.
        """
        folder = os.path.join(self.dir, self.REFERENCE_DIR)
        if not os.path.isdir(folder):
            return []
        taken = {r[0] for r in self.connect().execute('SELECT path FROM reference_bases')}
        found = []
        for name in sorted(os.listdir(folder)):
            if not name.lower().endswith('.pgn'):
                continue
            full = os.path.join(folder, name)
            relative = os.path.relpath(full, self.dir)
            if relative in taken or os.path.getsize(full) < minimum_bytes:
                continue
            found.append(dict(name=name, path=relative, bytes=os.path.getsize(full)))
        return found

    LARGE_LIBRARY = 200000

    def is_large(self):
        """Is this library big enough that a full scan is felt rather than measured?

        Asked as "is there a two-hundred-thousandth row", which an index answers, not
        as a count, which reads the lot.
        """
        cached = getattr(self._local, 'is_large', None)
        if cached is None:
            cached = bool(self.connect().execute(
                'SELECT 1 FROM games LIMIT 1 OFFSET ?', (self.LARGE_LIBRARY,)).fetchone())
            self._local.is_large = cached
        return cached

    def _fast_text_clause(self, term, params):
        """One search term, answered from indexes instead of by reading every row.

        Names, events and ECO codes match from the start — the same bargain the Master
        games search makes, and for the same reason. Opening names still match anywhere
        inside, because "Najdorf" sits in the middle of what that opening is called:
        the few hundred distinct names are filtered first and the games looked up by
        the name itself, which is indexed.

        What it gives up against the slow path is mid-string matching on people, events
        and sites — a forename, or a word from the middle of a tournament's name. Those
        have their own fields in the filter dialog, which still search anywhere.
        """
        reads = []
        for column in ('white', 'black', 'event', 'eco'):
            reads.append('SELECT id FROM games WHERE %s >= ? AND %s < ?' % (column, column))
            params.extend([term, term + '\uffff'])
            capital = term[:1].upper() + term[1:]
            if capital != term:
                reads.append('SELECT id FROM games WHERE %s >= ? AND %s < ?' % (column, column))
                params.extend([capital, capital + '\uffff'])
        reads.append('SELECT id FROM games WHERE opening IN '
                     '(SELECT name FROM opening_summary WHERE name LIKE ?)')
        params.append('%' + term + '%')
        return 'id IN (' + ' UNION '.join(reads) + ')'

    OPENING_SUMMARY_SQL = """
        INSERT INTO opening_summary (name, eco_from, eco_to, games)
        SELECT opening,
               MIN(CASE WHEN eco GLOB '[A-E][0-9][0-9]*' THEN substr(eco,1,3) END),
               MAX(CASE WHEN eco GLOB '[A-E][0-9][0-9]*' THEN substr(eco,1,3) END),
               COUNT(*)
        FROM games WHERE opening IS NOT NULL AND opening <> ''
        GROUP BY opening"""

    def merge_openings(self, conn, added):
        """Fold newly imported games into the opening summary.

        A rebuild is a full scan; an import knows exactly which openings it brought and
        how many of each, so it adds those counts rather than recounting the library.
        The ECO span widens to cover whatever arrived.
        """
        tally = {}
        for opening, eco in added:
            if not opening:
                continue
            code = eco[:3] if eco and len(eco) >= 3 and eco[0] in 'ABCDE' else None
            count, low, high = tally.get(opening, (0, code, code))
            tally[opening] = (count + 1,
                              min(x for x in (low, code) if x) if (low or code) else None,
                              max(x for x in (high, code) if x) if (high or code) else None)
        for name, (count, low, high) in tally.items():
            conn.execute("""INSERT INTO opening_summary (name, eco_from, eco_to, games)
                VALUES (?,?,?,?) ON CONFLICT(name) DO UPDATE SET
                    games = games + excluded.games,
                    eco_from = CASE WHEN eco_from IS NULL THEN excluded.eco_from
                                    WHEN excluded.eco_from IS NULL THEN eco_from
                                    ELSE MIN(eco_from, excluded.eco_from) END,
                    eco_to = CASE WHEN eco_to IS NULL THEN excluded.eco_to
                                  WHEN excluded.eco_to IS NULL THEN eco_to
                                  ELSE MAX(eco_to, excluded.eco_to) END""",
                         (name, low, high, count))
        if tally:
            # The summary is being kept up to date, which is what the flag records —
            # so the picker stops asking for a rebuild it does not need.
            conn.execute("INSERT OR REPLACE INTO settings VALUES ('opening_summary_games','1')")

    def rebuild_opening_summary(self):
        """Recount the openings in the library. One full pass, run when games change."""
        with self._write_lock:
            conn = self.connect()
            conn.execute('DELETE FROM opening_summary')
            conn.execute(self.OPENING_SUMMARY_SQL)
            conn.execute("INSERT OR REPLACE INTO settings VALUES ('opening_summary_games','1')")
            conn.commit()
        return conn.execute('SELECT COUNT(*) FROM opening_summary').fetchone()[0]

    def openings(self, term='', limit=40):
        """Opening names for the picker, and whether the summary behind them is current.

        Never rebuilds inline: the caller is a keystroke, and a rebuild is a full scan.
        A stale answer with `stale: True` beside it is worth more than a frozen box.
        """
        conn = self.connect()
        sql = ('SELECT name, eco_from, eco_to, games FROM opening_summary'
               + (' WHERE name LIKE ?' if term else '')
               + ' ORDER BY games DESC, name LIMIT ?')
        params = (['%' + term + '%'] if term else []) + [max(1, min(int(limit), 200))]
        rows = [dict(r) for r in conn.execute(sql, params)]
        built = conn.execute("SELECT value FROM settings WHERE key='opening_summary_games'").fetchone()
        return rows, built is None

    def begin_import(self, label):
        batch = uuid.uuid4().hex
        with self._write_lock, self.connect() as db:
            db.execute('INSERT INTO import_batches(id,created_at,label) VALUES (?,?,?)',
                       (batch, int(time.time()), label))
            self._active_imports.add(batch)
        self._local.batch = batch
        return batch

    def end_import(self, batch):
        with self._write_lock:
            self._active_imports.discard(batch)
        self._local.batch = None

    def import_history(self):
        return [dict(r) for r in self.connect().execute('''SELECT b.*,
            (SELECT COUNT(*) FROM import_members m WHERE m.batch=b.id) AS games
            FROM import_batches b ORDER BY created_at DESC, rowid DESC LIMIT 30''')]

    def undo_import(self, batch):
        with self._write_lock, self.connect() as db:
            if batch in self._active_imports:
                raise ValueError('Wait for this import to finish before undoing it')
            count = db.execute('DELETE FROM games WHERE id IN (SELECT game_id FROM import_members WHERE batch=?)', (batch,)).rowcount
            db.execute('UPDATE import_batches SET undone=1 WHERE id=?', (batch,))
        return {'deleted': count}

    def delete_game(self, game_id):
        """Drops the index entry. The PGN text stays in the file until compacted."""
        with self._write_lock:
            conn = self.connect()
            cur = conn.execute("DELETE FROM games WHERE id = ?", (game_id,))
            conn.commit()
        return cur.rowcount > 0

    def replace_game(self, game_id, pgn_text):
        """Save an edited/annotated game: appended fresh, index re-pointed at it."""
        row = self.connect().execute(
            "SELECT collection_id, path FROM games WHERE id = ?", (game_id,)
        ).fetchone()
        if not row:
            return False
        info = self.connect().execute(
            "SELECT name FROM collections WHERE id = ?", (row["collection_id"],)
        ).fetchone()
        path = self._pgn_path(info["name"])
        rel = os.path.relpath(path, self.dir)
        meta = pgnutil.describe(pgn_text)
        blob = pgn_text.strip() + "\n\n"
        with self._write_lock:
            with open(path, "a", encoding="utf-8", newline="\n") as handle:
                offset = handle.tell()
                handle.write(blob)
            conn = self.connect()
            conn.execute(
                """UPDATE games SET path=?, byte_offset=?, byte_length=?, white=?, black=?,
                       white_elo=?, black_elo=?, result=?, date=?, event=?, eco=?, opening=?,
                       ply_count=?, first_moves=? WHERE id=?""",
                (
                    rel, offset, len(blob.encode("utf-8")), meta["white"], meta["black"],
                    meta["white_elo"], meta["black_elo"], meta["result"], meta["date"],
                    meta["event"], meta["eco"], meta["opening"], meta["ply_count"],
                    meta["first_moves"], game_id,
                ),
            )
            self._update_extra_metadata(conn, game_id, pgn_text)
            # source_id identifies where the game came from and is unique across the
            # library; annotating a game must not let it claim another game's identity.
            conn.execute('UPDATE games SET signature=?, fen=?, variant=? WHERE id=?',
                         (self.signature(pgn_text), meta['fen'], meta['variant'], game_id))
            if meta['source_id']:
                taken = conn.execute('SELECT id FROM games WHERE source_id=? AND id<>?',
                                     (meta['source_id'], game_id)).fetchone()
                if not taken:
                    conn.execute('UPDATE games SET source_id=? WHERE id=?', (meta['source_id'], game_id))
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='positions'").fetchone():
                conn.execute('DELETE FROM positions WHERE game_id=?', (game_id,))
            conn.commit()
        return True

    # ---------- odds and ends ----------

    def stats(self, full=False):
        """The library's headline numbers.

        `full` adds three whole-table aggregates — commonest players, commonest
        openings, counts by source. Ranking players means grouping white and black
        together, which is two rows per game: seventeen million for a library with a
        reference base attached, and a minute of work for a panel that does not exist.
        The database page asks for the cheap answer; anything that actually wants the
        rankings asks for them.
        """
        conn = self.connect()
        out = {
            "games": conn.execute("SELECT COUNT(*) FROM games").fetchone()[0],
            "data_dir": self.dir,
        }
        if not full:
            return out
        out["collections"] = self.collections()
        out["by_source"] = {
            r["source"] or "unknown": r["n"]
            for r in conn.execute("SELECT source, COUNT(*) AS n FROM games GROUP BY source").fetchall()
        }
        out["top_players"] = [dict(r) for r in conn.execute(
            """SELECT name, COUNT(*) AS n FROM (
                   SELECT white AS name FROM games UNION ALL SELECT black FROM games
               ) GROUP BY name ORDER BY n DESC LIMIT 10""")]
        out["top_openings"] = [dict(r) for r in conn.execute(
            "SELECT opening, COUNT(*) AS n FROM games WHERE opening <> '' "
            "GROUP BY opening ORDER BY n DESC LIMIT 15")]
        return out

    def setting(self, key, value=None):
        conn = self.connect()
        if value is None:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else None
        with self._write_lock:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            conn.commit()
        return value

    def repertoires(self):
        rows = self.connect().execute(
            "SELECT id, name, color, updated_at FROM repertoires ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def repertoire(self, rep_id):
        row = self.connect().execute("SELECT * FROM repertoires WHERE id = ?", (rep_id,)).fetchone()
        return dict(row) if row else None

    def save_repertoire(self, name, color, data, rep_id=None):
        with self._write_lock:
            conn = self.connect()
            now = int(time.time())
            if rep_id:
                conn.execute(
                    "UPDATE repertoires SET name=?, color=?, data=?, updated_at=? WHERE id=?",
                    (name, color, data, now, rep_id),
                )
            else:
                cur = conn.execute(
                    "INSERT INTO repertoires (name, color, data, updated_at) VALUES (?,?,?,?)",
                    (name, color, data, now),
                )
                rep_id = cur.lastrowid
            conn.commit()
        return rep_id

    def delete_repertoire(self, rep_id):
        with self._write_lock:
            conn = self.connect()
            cur = conn.execute("DELETE FROM repertoires WHERE id = ?", (rep_id,))
            conn.commit()
        return cur.rowcount > 0

    def cache_explorer(self, fen, db_name, body=None, max_age=7 * 24 * 3600):
        conn = self.connect()
        if body is None:
            row = conn.execute(
                "SELECT body, fetched_at FROM explorer_cache WHERE fen = ? AND db = ?", (fen, db_name)
            ).fetchone()
            if row and (time.time() - row["fetched_at"]) < max_age:
                return row["body"]
            return None
        with self._write_lock:
            conn.execute(
                "INSERT INTO explorer_cache (fen, db, body, fetched_at) VALUES (?,?,?,?) "
                "ON CONFLICT(fen) DO UPDATE SET body=excluded.body, db=excluded.db, "
                "fetched_at=excluded.fetched_at",
                (fen, db_name, body, int(time.time())),
            )
            conn.commit()
        return body

"""The game library: PGN files on disk plus a SQLite index over them.

Layout (DATA_DIR defaults to ./library, or /data on Railway with a volume):

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
import uuid
from datetime import datetime, timedelta

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
  added_at INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS games_source_id ON games(source_id) WHERE source_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS games_collection ON games(collection_id);
CREATE INDEX IF NOT EXISTS games_white ON games(white);
CREATE INDEX IF NOT EXISTS games_black ON games(black);
CREATE INDEX IF NOT EXISTS games_eco ON games(eco);
CREATE INDEX IF NOT EXISTS games_date ON games(date);

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
            columns = {r[1] for r in conn.execute('PRAGMA table_info(games)')}
            if 'signature' not in columns:
                conn.execute('ALTER TABLE games ADD COLUMN signature TEXT')
            conn.execute('CREATE INDEX IF NOT EXISTS games_signature ON games(signature)')
            # Older libraries receive signatures once, without changing their PGNs.
            for row in conn.execute('SELECT id FROM games WHERE signature IS NULL').fetchall():
                text = self.game_pgn(row['id'])
                if text:
                    conn.execute('UPDATE games SET signature=? WHERE id=?', (self.signature(text), row['id']))

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
                      (SELECT COUNT(*) FROM games g WHERE g.collection_id = c.id) AS games
               FROM collections c ORDER BY c.name"""
        ).fetchall()
        return [dict(r) for r in rows]

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

    def delete_collection(self, ident, remove_files=False):
        info = self.collection(ident)
        if not info:
            return False
        with self._write_lock:
            conn = self.connect()
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

    def add_games(self, pgn_text, collection="My games", source="import", skip_duplicates=True):
        """Append every game in `pgn_text` to a collection. Returns a summary dict."""
        info = self.ensure_collection(collection)
        texts = pgnutil.split_games(pgn_text)
        if not texts:
            return {"added": 0, "duplicates": 0, "skipped": 0, "collection": info["name"]}

        path = self._pgn_path(info["name"])
        rel = os.path.relpath(path, self.dir)
        added = duplicates = skipped = 0
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

            with open(path, "a", encoding="utf-8", newline="\n") as handle:
                for text in texts:
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
                        duplicates += 1
                        continue
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
                if batch and cursor.rowcount:
                    conn.execute('INSERT INTO import_members VALUES (?,?)', (batch, cursor.lastrowid))
            conn.commit()

        return {
            "added": added,
            "duplicates": duplicates,
            "skipped": skipped,
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
        return out

    SORTS = {
        "date": "date DESC, id DESC",
        "date_asc": "date ASC, id ASC",
        "white": "white COLLATE NOCASE ASC",
        "black": "black COLLATE NOCASE ASC",
        "elo": "MAX(COALESCE(white_elo,0), COALESCE(black_elo,0)) DESC",
        "added": "added_at DESC, id DESC",
        "length": "ply_count DESC",
    }

    def search(self, query=None, collection=None, player=None, white=None, black=None,
               eco=None, result=None, opening=None, min_elo=None, year=None,
               sort="date", limit=100, offset=0, event=None, min_length=None, max_length=None, tag=None,
               added_from=None, added_to=None, position=None, eco_to=None):
        where, params = [], []

        if collection:
            info = self.collection(collection)
            if not info:
                return {"total": 0, "games": []}
            where.append("collection_id = ?")
            params.append(info["id"])
        if query:
            like = "%" + query.strip() + "%"
            where.append("(white LIKE ? OR black LIKE ? OR event LIKE ? OR opening LIKE ? OR eco LIKE ?)")
            params.extend([like] * 5)
        if player:
            like = "%" + player.strip() + "%"
            where.append("(white LIKE ? OR black LIKE ?)")
            params.extend([like, like])
        if white:
            where.append("white LIKE ?")
            params.append("%" + white + "%")
        if black:
            where.append("black LIKE ?")
            params.append("%" + black + "%")
        if eco:
            where.append("eco LIKE ?")
            params.append(eco.upper() + "%")
        if opening:
            where.append("opening LIKE ?")
            params.append("%" + opening + "%")
        if result:
            where.append("result = ?")
            params.append(result)
        if min_elo:
            where.append("(COALESCE(white_elo,0) >= ? OR COALESCE(black_elo,0) >= ?)")
            params.extend([int(min_elo), int(min_elo)])
        if year:
            where.append("date LIKE ?")
            params.append(str(year) + "%")
        if event:
            where.append('event LIKE ?')
            params.append('%'+event+'%')
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
            where.append('eco <= ?')
            params.append(eco_to.upper())
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
            "event, site, round, eco, opening, ply_count, source, first_moves, added_at, signature, path, byte_offset, byte_length "
            "FROM games" + clause + " ORDER BY " + order + " LIMIT ? OFFSET ?",
            params + [int(limit), int(offset)],
        ).fetchall()
        return {"total": total, "games": [dict(r) for r in rows]}

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

    def stats(self):
        conn = self.connect()
        total = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
        by_source = {
            r["source"] or "unknown": r["n"]
            for r in conn.execute("SELECT source, COUNT(*) AS n FROM games GROUP BY source").fetchall()
        }
        players = conn.execute(
            """SELECT name, COUNT(*) AS n FROM (
                   SELECT white AS name FROM games UNION ALL SELECT black FROM games
               ) GROUP BY name ORDER BY n DESC LIMIT 10"""
        ).fetchall()
        openings = conn.execute(
            "SELECT opening, COUNT(*) AS n FROM games WHERE opening <> '' "
            "GROUP BY opening ORDER BY n DESC LIMIT 15"
        ).fetchall()
        return {
            "games": total,
            "collections": self.collections(),
            "by_source": by_source,
            "top_players": [dict(r) for r in players],
            "top_openings": [dict(r) for r in openings],
            "data_dir": self.dir,
        }

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

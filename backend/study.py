"""Position knowledge and portable study folders layered on the PGN library."""
import json
import os
import threading
from .chess import Chess
from . import pgnutil
from .store import slugify

SCHEMA = '''
CREATE TABLE IF NOT EXISTS positions (
 hash TEXT NOT NULL, game_id INTEGER REFERENCES games(id) ON DELETE CASCADE,
 ply INTEGER NOT NULL, next_san TEXT, PRIMARY KEY(hash, game_id, ply));
CREATE INDEX IF NOT EXISTS positions_game ON positions(game_id);
CREATE TABLE IF NOT EXISTS pins (
 id INTEGER PRIMARY KEY, hash TEXT NOT NULL, fen TEXT NOT NULL,
 title TEXT NOT NULL, url TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS pins_hash ON pins(hash);
CREATE TABLE IF NOT EXISTS folders (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL UNIQUE,
 parent_id INTEGER REFERENCES folders(id), created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS collection_folders (
 collection_id INTEGER PRIMARY KEY REFERENCES collections(id) ON DELETE CASCADE,
 folder_id INTEGER REFERENCES folders(id));
CREATE TABLE IF NOT EXISTS game_tags (
 game_id INTEGER REFERENCES games(id) ON DELETE CASCADE, tag TEXT NOT NULL,
 PRIMARY KEY(game_id, tag));
'''

class Study:
    def __init__(self, library):
        self.library = library
        library.connect().executescript(SCHEMA)
        if 'category' not in {r[1] for r in library.connect().execute('PRAGMA table_info(folders)')}:
            library.connect().execute("ALTER TABLE folders ADD COLUMN category TEXT NOT NULL DEFAULT 'Games to study'")
            library.connect().commit()
        self.lock = threading.Lock()
        self.state = {'running': False, 'done': 0, 'errors': 0, 'total': 0, 'collection': None}

    def index(self, collection):
        info = self.library.collection(collection)
        if not info:
            raise ValueError('Choose an existing collection')
        with self.lock:
            if self.state['running']:
                raise ValueError('Position indexing is already running')
            self.state = dict(running=True, done=0, errors=0, total=0, collection=info['name'])
        threading.Thread(target=self._index, args=(info['id'],), daemon=True).start()
        return self.state.copy()

    def _index(self, collection_id):
        db = self.library.connect()
        try:
            ids = [r[0] for r in db.execute('SELECT id FROM games WHERE collection_id=?', (collection_id,))]
            self.state['total'] = len(ids)
            for game_id in ids:
                try:
                    pgn = self.library.game_pgn(game_id)
                    game = Chess(pgnutil.headers(pgn).get('FEN') or Chess().fen())
                    moves = pgnutil.moves(pgn)
                    rows = []
                    for ply in range(len(moves) + 1):
                        rows.append((game.key(), game_id, ply, moves[ply] if ply < len(moves) else None))
                        if ply < len(moves):
                            game.move(moves[ply])
                    with self.library._write_lock, db:
                        db.execute('DELETE FROM positions WHERE game_id=?', (game_id,))
                        db.executemany('INSERT INTO positions VALUES (?,?,?,?)', rows)
                except (ValueError, TypeError):
                    self.state['errors'] += 1
                self.state['done'] += 1
        except Exception as err:
            self.state['error'] = str(err)
        finally:
            self.state['running'] = False
            self.library.close()

    def position(self, fen):
        key = Chess(fen).key()
        db = self.library.connect()
        games = [dict(r) for r in db.execute('''SELECT DISTINCT g.id,g.white,g.black,g.date,g.event,
            g.result,g.eco,g.opening FROM positions p JOIN games g ON g.id=p.game_id
            WHERE p.hash=? ORDER BY CASE WHEN g.date LIKE '0000%' OR g.date='' THEN 1 ELSE 0 END,
            g.date, g.id LIMIT 100''', (key,))]
        moves = [dict(r) for r in db.execute('''SELECT next_san AS san, COUNT(*) AS games,
            SUM(result='1-0') AS white, SUM(result='1/2-1/2') AS draws, SUM(result='0-1') AS black
            FROM (SELECT DISTINCT p.game_id,p.next_san,g.result FROM positions p JOIN games g ON g.id=p.game_id WHERE hash=? AND next_san IS NOT NULL)
            GROUP BY next_san ORDER BY games DESC''', (key,))]
        decades = [dict(r) for r in db.execute('''SELECT CAST(substr(g.date,1,4) AS INTEGER)/10*10 AS decade,
            COUNT(DISTINCT g.id) AS games FROM positions p JOIN games g ON g.id=p.game_id
            WHERE hash=? AND substr(g.date,1,4) > '0000' GROUP BY decade ORDER BY decade''', (key,))]
        return dict(hash=key, games=games, moves=moves, decades=decades,
                    pins=[dict(r) for r in db.execute('SELECT * FROM pins WHERE hash=?', (key,))],
                    indexed_games=db.execute('SELECT COUNT(DISTINCT game_id) FROM positions').fetchone()[0])

    def pin(self, body):
        fen = body['fen']
        title = str(body.get('title', '')).strip()
        url = str(body.get('url', '')).strip()
        if not title or (url and not url.startswith(('https://', 'http://'))):
            raise ValueError('Give a title and an HTTP(S) link, or leave the link empty')
        with self.library._write_lock, self.library.connect() as db:
            cur = db.execute('INSERT INTO pins(hash,fen,title,url,note) VALUES(?,?,?,?,?)',
                             (Chess(fen).key(), fen, title, url, str(body.get('note', ''))))
        return {'id': cur.lastrowid}

    def folders(self):
        db = self.library.connect()
        return dict(folders=[dict(r) for r in db.execute('SELECT * FROM folders ORDER BY path')],
                    assignments=[dict(r) for r in db.execute('SELECT * FROM collection_folders')],
                    root=os.path.join(self.library.dir, 'studies'))

    def create_folder(self, body):
        title = str(body.get('name', '')).strip()
        if not title:
            raise ValueError('Give the study folder a name')
        parent_id = body.get('parent_id') or None
        db = self.library.connect()
        parent = db.execute('SELECT path FROM folders WHERE id=?', (parent_id,)).fetchone() if parent_id else None
        if parent_id and not parent:
            raise ValueError('Parent folder does not exist')
        relative = '/'.join(filter(None, [parent['path'] if parent else '', slugify(title)]))
        base = os.path.realpath(os.path.join(self.library.dir, 'studies'))
        target = os.path.realpath(os.path.join(base, relative))
        if os.path.commonpath([base, target]) != base:
            raise ValueError('Invalid folder path')
        with self.library._write_lock, db:
            if db.execute('SELECT id FROM folders WHERE path=?', (relative,)).fetchone():
                raise ValueError('A folder with that name already exists here')
            os.makedirs(target, exist_ok=True)
            cur = db.execute('INSERT INTO folders(name,path,parent_id) VALUES(?,?,?)', (title, relative, parent_id))
            db.execute('UPDATE folders SET category=? WHERE id=?',(str(body.get('category') or 'Games to study').strip()[:100],cur.lastrowid))
        self.write_manifest(cur.lastrowid)
        return {'id': cur.lastrowid, 'path': target}

    def delete_folder(self, folder_id):
        """Remove a folder and everything nested inside it.

        Collections are only unassigned: their PGN files live in the library's
        collections directory, not in the study folder. On disk we take back the
        manifest we wrote and the directories we created, but a directory the user
        has put their own files in is left alone and reported back.
        """
        db = self.library.connect()
        folder = db.execute('SELECT * FROM folders WHERE id=?', (int(folder_id),)).fetchone()
        if not folder:
            raise ValueError('No such folder')
        prefix = folder['path'] + '/'
        doomed = [dict(r) for r in db.execute('SELECT id, name, path FROM folders')
                  if r['path'] == folder['path'] or r['path'].startswith(prefix)]
        # Children first: parent_id is a real foreign key.
        doomed.sort(key=lambda f: f['path'].count('/'), reverse=True)
        with self.library._write_lock, db:
            for row in doomed:
                db.execute('DELETE FROM collection_folders WHERE folder_id=?', (row['id'],))
            for row in doomed:
                db.execute('DELETE FROM folders WHERE id=?', (row['id'],))
        base = os.path.realpath(os.path.join(self.library.dir, 'studies'))
        kept = []
        for row in doomed:
            if not row['path']:
                continue
            target = os.path.realpath(os.path.join(base, row['path']))
            if os.path.commonpath([base, target]) != base or not os.path.isdir(target):
                continue
            manifest = os.path.join(target, 'study.json')
            if os.path.isfile(manifest):
                os.remove(manifest)
            try:
                os.rmdir(target)
            except OSError:                      # the folder still holds the user's own files
                kept.append(target)
        return {'deleted': len(doomed), 'kept': kept}

    def assign(self, body):
        db = self.library.connect()
        folder_id, collection_id = int(body['folder_id']), int(body['collection_id'])
        if not db.execute('SELECT 1 FROM folders WHERE id=?', (folder_id,)).fetchone():
            raise ValueError('No such folder')
        if not self.library.collection(collection_id):
            raise ValueError('No such collection')
        old = db.execute('SELECT folder_id FROM collection_folders WHERE collection_id=?', (collection_id,)).fetchone()
        with self.library._write_lock, db:
            db.execute('INSERT OR REPLACE INTO collection_folders VALUES(?,?)', (collection_id, folder_id))
        self.write_manifest(folder_id)
        if old and old[0] != folder_id:
            self.write_manifest(old[0])
        return {'saved': True}

    def write_manifest(self, folder_id):
        db = self.library.connect()
        folder = db.execute('SELECT * FROM folders WHERE id=?', (folder_id,)).fetchone()
        if not folder:
            return
        target = os.path.join(self.library.dir, 'studies', folder['path'])
        entries = []
        for row in db.execute('''SELECT c.name FROM collection_folders f JOIN collections c
                              ON c.id=f.collection_id WHERE f.folder_id=?''', (folder_id,)):
            entries.append(dict(name=row['name'], pgn=os.path.relpath(self.library._pgn_path(row['name']), target)))
        with open(os.path.join(target, 'study.json'), 'w', encoding='utf-8') as f:
            json.dump(dict(name=folder['name'], category=folder['category'], collections=entries), f, indent=2)

    def categorize_folder(self, ident, category):
        category=str(category).strip()[:100]
        if not category:
            raise ValueError('Choose a category')
        with self.library._write_lock, self.library.connect() as db:
            if not db.execute('UPDATE folders SET category=? WHERE id=?',(category,int(ident))).rowcount:
                raise ValueError('No such folder')
        self.write_manifest(int(ident))
        return {'saved':True}

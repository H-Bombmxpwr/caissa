"""Streaming imports of portable chess files. Archives are read, never extracted."""
import bz2
import csv
import gzip
import io
import json
import os
import re
import sqlite3
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from contextlib import contextmanager
from . import pgnutil, lichess

SUPPORTED = ('.pgn', '.zip', '.gz', '.bz2', '.zst', '.epd', '.csv')

# ChessBase writes PGN in the Windows code page, not UTF-8. Reading such a file as
# UTF-8 with errors='replace' turns every accented name — Réti, Polgár, Şuba — into
# U+FFFD, and once written to the library those letters are gone for good. So the
# encoding is sniffed from the start of the file and applied to the whole of it:
# one file is written in one encoding, and guessing per chunk would only produce a
# file that is half right.
SNIFF_BYTES = 65536
FALLBACK_ENCODINGS = ('cp1252', 'latin-1')


def sniff_encoding(sample, more_follows=True):
    """Pick the encoding for a PGN file from its opening bytes."""
    if sample.startswith(b'\xff\xfe') or sample.startswith(b'\xfe\xff'):
        return 'utf-16'
    try:
        sample.decode('utf-8-sig')
        return 'utf-8-sig'
    except UnicodeDecodeError as err:
        # A multi-byte character cut in half by the end of the sample is not evidence
        # of anything; only a failure inside the sample proper counts.
        if more_follows and err.start >= len(sample) - 4:
            return 'utf-8-sig'
    for encoding in FALLBACK_ENCODINGS:
        try:
            sample.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return 'utf-8-sig'


def decoded(binary, encoding=None):
    """Wrap a binary stream as text, sniffing the encoding when the stream allows it."""
    if encoding is None:
        encoding = 'utf-8-sig'
        try:
            sample = binary.read(SNIFF_BYTES)
            binary.seek(0)
            encoding = sniff_encoding(sample, more_follows=len(sample) == SNIFF_BYTES)
        except (OSError, AttributeError, io.UnsupportedOperation):
            pass                                    # not seekable: UTF-8 it is
    return io.TextIOWrapper(binary, encoding=encoding, errors='replace')


@contextmanager
def streams(path):
    lower = path.lower()
    if lower.endswith('.zip'):
        with zipfile.ZipFile(path) as archive:
            for entry in archive.infolist():
                if entry.filename.lower().endswith('.pgn'):
                    with archive.open(entry) as raw:
                        head = raw.read(SNIFF_BYTES)
                        encoding = sniff_encoding(head, more_follows=len(head) == SNIFF_BYTES)
                    with archive.open(entry) as raw:
                        with decoded(raw, encoding) as stream:
                            yield stream
        return
    if lower.endswith('.zst'):
        try:
            import zstandard
        except ImportError as err:
            raise ValueError('ZST files need the optional package: pip install zstandard') from err
        with open(path, 'rb') as raw, zstandard.ZstdDecompressor().stream_reader(raw) as reader:
            # A zstd reader cannot be rewound, and the dumps that use it are UTF-8.
            with io.TextIOWrapper(reader, encoding='utf-8-sig', errors='replace') as stream:
                yield stream
    else:
        opener = gzip.open if lower.endswith('.gz') else bz2.open if lower.endswith('.bz2') else open
        with opener(path, 'rb') as raw:
            with decoded(raw) as stream:
                yield stream

def game_stream(stream):
    chunk, body_seen, brace_depth = [], False, 0
    for line in stream:
        if brace_depth == 0 and line.lstrip().startswith('[') and body_seen:
            yield ''.join(chunk)
            chunk, body_seen = [], False
        chunk.append(line)
        if line.strip() and not line.lstrip().startswith(('[', '%')):
            body_seen = True
        # A header-looking line within a PGN comment does not begin a new game.
        brace_depth = max(0, brace_depth + line.count('{') - line.count('}'))
    if ''.join(chunk).strip():
        yield ''.join(chunk)

def epd_stream(stream):
    for line in stream:
        if not line.strip():
            continue
        fields = line.split(maxsplit=4)
        if len(fields) < 4:
            raise ValueError('Invalid EPD: expected four FEN fields')
        fen = ' '.join(fields[:4]) + ' 0 1'
        operations = fields[4] if len(fields) > 4 else ''
        bm = re.search(r'(?:^|;)\s*bm\s+([^;]+)', operations)
        title = re.search(r'(?:^|;)\s*id\s+"([^"]+)"', operations)
        yield '[Event "'+(title[1] if title else 'EPD problem')+'"]\n[SetUp "1"]\n[FEN "'+fen+'"]\n[Result "*"]\n\n'+(bm[1].split()[0] if bm else '')+' *'

def puzzle_csv(stream):
    from .chess import Chess
    for row in csv.DictReader(stream):
        game = Chess(row['FEN'])
        moves = row['Moves'].split()
        if len(moves) < 2:
            continue
        game.move(moves[0])  # lichess CSV starts before the opponent's setup move.
        fen = game.fen()
        sans = [game.move(m) for m in moves[1:]]
        yield '[Event "Lichess puzzle '+row['PuzzleId']+'"]\n[SetUp "1"]\n[FEN "'+fen+'"]\n[Result "*"]\n[Themes "'+row.get('Themes','')+'"]\n\n'+' '.join(sans)+' *'

def import_local(library, path, collection):
    total = dict(added=0, duplicates=0, skipped=0, linked=0)
    if os.path.isdir(path):
        paths = (os.path.join(root, f) for root, dirs, files in os.walk(path) for f in sorted(files)
                 if f.lower().endswith(SUPPORTED))
    else:
        paths = [path]
    def consume(stream, file):
        lower = re.sub(r'\.(?:gz|bz2|zst)$', '', file.lower())
        reader = epd_stream if lower.endswith('.epd') else puzzle_csv if lower.endswith('.csv') else game_stream
        batch = []
        for game in reader(stream):
            batch.append(game)
            if len(batch) >= 100:
                flush(batch)
                batch = []
        flush(batch)
    def flush(batch):
        if batch:
            result = library.add_games('\n\n'.join(batch), collection, 'file')
            for key in total:
                total[key] += result[key]
    for file in paths:
        if not file.lower().endswith(SUPPORTED):
            raise ValueError('Unsupported format. Export CBH, CBV or SI4 to PGN in ChessBase or SCID vs PC.')
        if file.lower().endswith('.zip'):
            with zipfile.ZipFile(file) as archive:
                for entry in archive.infolist():
                    if entry.filename.lower().endswith('.pgn'):
                        with archive.open(entry) as raw, io.TextIOWrapper(raw, encoding='utf-8-sig', errors='replace') as stream:
                            consume(stream, entry.filename)
        else:
            with streams(file) as stream:
                consume(stream, file)
    return total

ATTACH_COLUMNS = (
    'collection_id', 'path', 'byte_offset', 'byte_length', 'white', 'black',
    'white_elo', 'black_elo', 'result', 'date', 'event', 'site', 'round', 'eco',
    'opening', 'variant', 'time_control', 'fen', 'ply_count', 'first_moves',
    'source', 'source_id', 'added_at', 'signature', 'annotator', 'termination',
    'has_annotations', 'event_date', 'event_type', 'white_team', 'black_team',
    'white_title', 'black_title', 'white_fide_id', 'black_fide_id', 'source_title',
    'variation', 'speed', 'rated')


def reference_games(handle, encoding, start_at=0):
    """Yield (offset, length, text) for every game in an open PGN, without loading it.

    Offsets are what make attaching possible, so they are counted in bytes off the
    file itself rather than inferred from decoded text: a game is looked up later by
    seeking to exactly this many bytes and reading exactly this many more.

    `start_at` is one of those offsets from an earlier pass, which is what lets a scan
    of an eight-gigabyte file be picked up where it stopped rather than begun again.
    """
    if start_at:
        handle.seek(start_at)
    chunk, start, offset, body = [], start_at, start_at, False
    for raw in handle:
        # A header line only starts a new game once the previous one has had moves;
        # a bracket inside a comment is not a new game.
        if body and raw.startswith(b'[Event ') and chunk:
            blob = b''.join(chunk)
            yield start, len(blob), blob.decode(encoding, 'replace')
            chunk, start, body = [], offset, False
        chunk.append(raw)
        offset += len(raw)
        stripped = raw.strip()
        if stripped and not stripped.startswith((b'[', b'%')):
            body = True
    if chunk:
        blob = b''.join(chunk)
        yield start, len(blob), blob.decode(encoding, 'replace')


def attach_reference(library, path, collection, progress=None, batch_size=20000,
                     resume=False, deadline=None):
    """Register a reference PGN where it already lies, instead of copying it in.

    The library keeps only headers and a byte offset in SQLite and reads move text back
    from the file on demand, so a multi-gigabyte base does not need to be ingested — it
    needs to be pointed at. The scan records where each game starts and how long it is;
    the game list, the analysis board and every export then open the original file at
    that offset. Nothing is duplicated and nothing is rewritten.

    The trade is that the file has to stay where it is. It is stored relative to the
    library folder when it lives inside one, so moving the whole library is still safe.

    Duplicate detection is deliberately skipped. It costs a hash and an index probe per
    game, and holds every signature seen in memory — affordable for an import of a few
    thousand games, not for ten million. A reference base is attached once, whole.

    A scan of that size is worth being able to stop and pick up. `deadline` is a clock
    time to stop cleanly at, and `resume` carries on from the offset the last pass
    committed, so the work survives a closed app or a machine that needs its memory
    back. The result says whether the end of the file was reached.
    """
    # A path from the app is relative to the library, not to wherever the server was
    # started; an absolute one from a file picker is taken as given.
    path = os.path.expanduser(str(path).strip())
    path = os.path.abspath(path if os.path.isabs(path) else os.path.join(library.dir, path))
    if not os.path.isfile(path):
        raise ValueError('No PGN at ' + path)
    if not path.lower().endswith('.pgn'):
        raise ValueError('Attach a .pgn file. Extract archives first.')
    info = library.ensure_collection(collection, 'games')
    try:
        stored = os.path.relpath(path, library.dir)
        if stored.startswith('..'):
            stored = path
    except ValueError:                       # a different drive: keep it absolute
        stored = path

    with open(path, 'rb') as handle:
        encoding = sniff_encoding(handle.read(SNIFF_BYTES))
    total = dict(added=0, duplicates=0, skipped=0, linked=0)
    state = dict(since_checkpoint=0, scanned=0, committed=False)
    now = int(time.time())
    rows = []
    statement = ('INSERT INTO games (' + ','.join(ATTACH_COLUMNS) + ') VALUES ('
                 + ','.join('?' * len(ATTACH_COLUMNS)) + ')')

    def flush(conn):
        """Write a batch, and never let one strange game cost the whole scan.

        A third-party compilation of ten million games will contain something the schema
        refuses; the first attempt at this one died 860,000 games in, on four games
        quoting the same lichess broadcast URL. A batch that will not go in as a batch is
        retried a row at a time, so the other 19,999 games still land and the count of
        what was refused is honest.
        """
        if not rows:
            return 0
        try:
            conn.executemany(statement, rows)
            rows.clear()
            return 0
        except sqlite3.DatabaseError:
            conn.rollback()
        refused = 0
        for row in rows:
            try:
                conn.execute(statement, row)
            except sqlite3.DatabaseError:
                refused += 1
        rows.clear()
        return refused

    def record(conn, refused):
        total['added'] -= refused
        total['skipped'] += refused
        # The offset goes in with the rows it belongs to: whatever is committed here is
        # what a later pass may safely skip past.
        conn.execute('UPDATE reference_bases SET scanned_bytes=? WHERE collection_id=?',
                     (state['scanned'], info['id']))
        conn.commit()
        state['committed'] = True
        # Ten million inserts in WAL mode grow the log to gigabytes unless it is folded
        # back into the database now and then. PASSIVE yields rather than waiting, so a
        # reader with the library open never blocks the scan or is blocked by it.
        state['since_checkpoint'] += 1
        if state['since_checkpoint'] >= 2:
            conn.execute('PRAGMA wal_checkpoint(PASSIVE)')
            state['since_checkpoint'] = 0

    with library._write_lock:
        conn = library.connect()
        # Attaching is idempotent: any earlier attempt at this same file is cleared
        # first, so a scan that was interrupted — the machine ran out of memory, the
        # app was closed — is fixed by attaching again rather than by hand. The base is
        # registered now rather than at the end, so a partial one is still visible in
        # Master games and can be detached from there.
        row = conn.execute('SELECT scanned_bytes FROM reference_bases WHERE collection_id=? AND path=?',
                           (info['id'], stored)).fetchone() if resume else None
        state['scanned'] = row['scanned_bytes'] if row else 0
        if not state['scanned']:
            conn.execute("DELETE FROM games WHERE collection_id=? AND source='reference' AND path=?",
                         (info['id'], stored))
            conn.execute('INSERT OR REPLACE INTO reference_bases VALUES (?,?,?,0,0)',
                         (info['id'], stored, now))
            conn.commit()
        try:
            with open(path, 'rb') as handle:
                for offset, length, text in reference_games(handle, encoding, state['scanned']):
                    # Every game read is accounted for, written or skipped, so the
                    # offset a pass commits is a true "everything before here is done".
                    state['scanned'] = offset + length
                    try:
                        meta = pgnutil.describe(text)
                    except (ValueError, KeyError, IndexError):
                        total['skipped'] += 1
                        continue
                    if meta['variant'].lower() not in ('standard', 'chess', 'from position'):
                        total['skipped'] += 1
                        continue
                    if not meta['ply_count'] and not meta['fen']:
                        total['skipped'] += 1
                        continue
                    rows.append((
                        info['id'], stored, offset, length, meta['white'], meta['black'],
                        meta['white_elo'], meta['black_elo'], meta['result'], meta['date'],
                        meta['event'], meta['site'], meta['round'], meta['eco'],
                        meta['opening'], meta['variant'], meta['time_control'], meta['fen'],
                        meta['ply_count'], meta['first_moves'], 'reference',
                        # source_id is the unique key that stops the same online game being
                        # imported twice. A compilation is not an online account: this base
                        # carries lichess broadcast URLs whose last segment names the round
                        # rather than the game, so several games share one "id" and the
                        # unique index refuses them. A base claims no online identity.
                        None,
                        now, library.signature(text), meta['annotator'], meta['termination'],
                        meta['has_annotations'], meta['event_date'], meta['event_type'],
                        meta['white_team'], meta['black_team'], meta['white_title'],
                        meta['black_title'], meta['white_fide_id'], meta['black_fide_id'],
                        meta['source_title'], meta['variation'], meta['speed'], meta['rated']))
                    total['added'] += 1
                    if len(rows) >= batch_size:
                        record(conn, flush(conn))
                        if progress:
                            progress(total['added'], 0)
                        # Stopping only at a batch boundary means the offset just
                        # committed is exactly the boundary: no game is claimed
                        # without being written, and none is written twice.
                        if deadline is not None and time.time() > deadline:
                            break
            record(conn, flush(conn))
            finished = state['scanned'] >= os.path.getsize(path)
            if finished:
                conn.execute('UPDATE reference_bases SET complete=1 WHERE collection_id=?',
                             (info['id'],))
            conn.commit()
            total['complete'] = finished
        except BaseException:
            # A half-attached base is worse than no base: the reader would be searching
            # some unknown fraction of it. Undo this scan's rows and let the error out.
            # Whatever earlier passes committed stays; only this pass's uncommitted
            # work is dropped, so a failure costs a batch rather than the whole scan.
            conn.rollback()
            # A pass that committed nothing leaves nothing: a base with no games and no
            # progress is a phantom, not something to resume.
            if not state['committed']:
                conn.execute("DELETE FROM games WHERE collection_id=? AND source='reference' AND path=?",
                             (info['id'], stored))
                conn.execute('DELETE FROM reference_bases WHERE collection_id=?', (info['id'],))
                conn.commit()
            raise
    if progress:
        progress(total['added'], 0)
    total.update(collection=info['name'], collection_id=info['id'], path=stored,
                 bytes=os.path.getsize(path), scanned_bytes=state['scanned'])
    return total

def reference_dependents(library, collection_id):
    """Collections that shelve games belonging to this base.

    A carved collection links to the base's rows rather than copying them, which is what
    makes carving free — and what makes detaching destructive: the link is a foreign key
    that cascades. So the dependents are counted before anything is deleted.
    """
    return [dict(r) for r in library.connect().execute(
        """SELECT c.id, c.name, COUNT(*) AS games
           FROM game_collections gc
           JOIN games g ON g.id = gc.game_id
           JOIN collections c ON c.id = gc.collection_id
           WHERE g.collection_id = ? AND g.source = 'reference' AND c.id <> ?
           GROUP BY c.id, c.name ORDER BY games DESC""", (collection_id, collection_id))]


def detach_reference(library, collection, force=False):
    """Forget an attached base. The PGN on disk is never touched.

    Collections carved out of the base hold links to its rows, so detaching empties them
    too. That is a surprise worth refusing by default: the caller is told which
    collections would be emptied, and has to ask again to go through with it.
    """
    info = library.collection(collection)
    if not info:
        raise ValueError('No such collection')
    dependents = reference_dependents(library, info['id'])
    if dependents and not force:
        listed = ', '.join('%s (%d games)' % (d['name'], d['games']) for d in dependents[:4])
        raise ValueError('Detaching would also empty ' + listed
                         + ('' if len(dependents) <= 4 else ' and %d more' % (len(dependents) - 4))
                         + ', because those collections shelve the base\u2019s games rather than copies.')
    with library._write_lock:
        conn = library.connect()
        removed = conn.execute(
            "DELETE FROM games WHERE collection_id=? AND source='reference'",
            (info['id'],)).rowcount
        conn.execute('DELETE FROM reference_bases WHERE collection_id=?', (info['id'],))
        conn.commit()
    return {'deleted': removed, 'collection': info['name'],
            'emptied': [d['name'] for d in dependents]}


def import_source(library, source, collection):
    if source.startswith(('https://', 'http://')):
        suffix = urllib.parse.urlparse(source).path.lower()
        if not suffix.endswith(SUPPORTED):
            raise ValueError('Use a direct PGN or archive download URL')
        ext = next(e for e in SUPPORTED if suffix.endswith(e))
        if suffix.endswith('.csv.zst'):
            ext = '.csv.zst'
        imports = os.path.join(library.dir, 'downloads')
        os.makedirs(imports, exist_ok=True)
        req = urllib.request.Request(source, headers={'User-Agent':'Caissa/1.0 (personal chess study)'})
        fd, path = tempfile.mkstemp(suffix=ext, dir=imports)
        try:
            with os.fdopen(fd, 'wb') as out, urllib.request.urlopen(req, timeout=60) as response:
                while True:
                    chunk = response.read(1024*1024)
                    if not chunk:
                        break
                    out.write(chunk)
            return import_local(library, path, collection)
        finally:
            os.remove(path)
    return import_local(library, os.path.abspath(os.path.expanduser(source)), collection)

def _month_key(value):
    """A YYYY-MM sort key from a date, or None. Accepts 2024-06-01 and 2024.06.01."""
    if not value:
        return None
    digits = re.match(r'(\d{4})[-./](\d{1,2})', str(value).strip())
    return '%s-%02d' % (digits[1], int(digits[2])) if digits else None


def chesscom(library, user, collection, maximum=100, perf=None, since=None, until=None):
    """Import a chess.com account, newest game first.

    `maximum` of 0 means every game the account has. `perf` narrows to one time control
    — bullet, blitz, rapid, classical or correspondence — and `since`/`until` are ISO
    dates: whole months outside the range are never fetched, which is what keeps "every
    rapid game this year" from downloading a decade.
    """
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', user):
        raise ValueError('Give a valid chess.com username')
    # chess.com's own brackets disagree with the library's at the edges — it calls a
    # 30-minute game rapid, and its slowest bracket "daily" — so the time control is
    # read from each game's own PGN with the same rule the index uses. The fetch and
    # the report that follows it then describe exactly the same set of games.
    speed = (perf or '').strip().lower() or None
    first, last = _month_key(since), _month_key(until)
    base = 'https://api.chess.com/pub/player/'+urllib.parse.quote(user.lower())+'/games/archives'
    archives = json.loads(lichess._request(base, 'application/json'))['archives']
    total = dict(added=0, duplicates=0, skipped=0, linked=0)
    remaining = maximum if maximum and maximum > 0 else None
    collection_id = None
    for archive in reversed(archives):
        if not archive.startswith('https://api.chess.com/pub/player/'):
            continue
        month = _month_key('-'.join(archive.rsplit('/', 2)[-2:]))
        if (first and month and month < first) or (last and month and month > last):
            continue
        games = json.loads(lichess._request(archive, 'application/json')).get('games', [])
        pgns = [g['pgn'] for g in reversed(games)
                if g.get('pgn') and g.get('rules', 'chess') == 'chess'
                and (not speed or pgnutil.speed_of(
                    pgnutil.headers(g['pgn']).get('TimeControl')) == speed)]
        if remaining is not None:
            pgns = pgns[:remaining]
        if not pgns:
            continue
        result = library.add_games('\n\n'.join(pgns), collection, 'chesscom')
        collection_id = result.get('collection_id', collection_id)
        for key in total:
            total[key] += result[key]
        if remaining is not None:
            remaining -= len(pgns)
            if remaining <= 0:
                break
    total['user'] = user
    total['collection'] = collection
    total['collection_id'] = collection_id
    return total

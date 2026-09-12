"""Streaming imports of portable chess files. Archives are read, never extracted."""
import bz2
import csv
import gzip
import io
import json
import os
import re
import tempfile
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

def chesscom(library, user, collection, maximum=100):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', user):
        raise ValueError('Give a valid chess.com username')
    base = 'https://api.chess.com/pub/player/'+urllib.parse.quote(user.lower())+'/games/archives'
    archives = json.loads(lichess._request(base, 'application/json'))['archives']
    total, remaining = dict(added=0, duplicates=0, skipped=0, linked=0), maximum
    for archive in reversed(archives):
        if not archive.startswith('https://api.chess.com/pub/player/'):
            continue
        games = json.loads(lichess._request(archive, 'application/json')).get('games', [])
        pgns = [g['pgn'] for g in reversed(games) if g.get('pgn') and g.get('rules','chess')=='chess'][:remaining]
        result = library.add_games('\n\n'.join(pgns), collection, 'chesscom')
        for key in total:
            total[key] += result[key]
        remaining -= len(pgns)
        if remaining <= 0:
            break
    return total

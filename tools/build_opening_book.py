"""Build the shipped offline book. Build-only dependency: pip install chess.

Source games are CC0 Lichess exports, filtered by the Lichess Elite Database.
The runtime uses only SQLite and Caissa's own chess rules.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import urllib.request
import zipfile
import chess

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend import pgnutil
SOURCE='https://database.nikonoel.fr/lichess_elite_2025-11.zip'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--archive',type=Path,default=ROOT/'tmp/lichess_elite_2025-11.zip')
    parser.add_argument('--plies',type=int,default=48)
    args=parser.parse_args()
    args.archive.parent.mkdir(parents=True,exist_ok=True)
    if not args.archive.exists():
        print('Downloading '+SOURCE,flush=True)
        urllib.request.urlretrieve(SOURCE,args.archive)
    target=ROOT/'data/opening-book.sqlite3'
    staging=target.with_suffix('.building')
    db=sqlite3.connect(staging)
    db.executescript('DROP TABLE IF EXISTS moves; DROP TABLE IF EXISTS metadata; CREATE TABLE moves(hash TEXT,san TEXT,white INTEGER,draws INTEGER,black INTEGER,PRIMARY KEY(hash,san)) WITHOUT ROWID; CREATE TABLE metadata(body TEXT); PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;')
    batch={}; games=0; errors=0
    def consume(text):
        nonlocal games,errors
        head=pgnutil.headers(text)
        result=head.get('Result')
        if result not in ('1-0','1/2-1/2','0-1') or head.get('FEN'):return
        board=chess.Board();rows=[];seen=set()
        try:
            for san in pgnutil.moves(text,limit=args.plies):
                key=hashlib.sha256(' '.join(board.fen(en_passant='legal').split()[:4]).encode()).hexdigest()[:32]
                move=board.parse_san(san);san=board.san(move);pair=(key,san)
                if pair not in seen:rows.append(pair);seen.add(pair)
                board.push(move)
        except ValueError:
            errors+=1;return
        for pair in rows:
            counts=batch.setdefault(pair,[0,0,0]);counts[('1-0','1/2-1/2','0-1').index(result)]+=1
        games+=1
        if games%2000==0:flush()
    def flush():
        db.executemany('INSERT INTO moves VALUES(?,?,?,?,?) ON CONFLICT(hash,san) DO UPDATE SET white=white+excluded.white,draws=draws+excluded.draws,black=black+excluded.black',[(key,san,*counts) for (key,san),counts in batch.items()]);db.commit();batch.clear()
        print(f'{games:,} games processed; {errors} rejected',flush=True)
    with zipfile.ZipFile(args.archive) as archive:
        for name in archive.namelist():
            if not name.lower().endswith('.pgn'):continue
            with io.TextIOWrapper(archive.open(name),encoding='utf-8-sig',errors='replace') as stream:
                lines=[]
                for line in stream:
                    if line.startswith('[Event ') and lines:
                        consume(''.join(lines));lines=[]
                    lines.append(line)
                if lines:consume(''.join(lines))
    flush()
    db.execute('DELETE FROM moves WHERE white+draws+black<2')
    entries,positions=db.execute('SELECT COUNT(*),COUNT(DISTINCT hash) FROM moves').fetchone()
    meta=dict(title='Lichess Elite · November 2025',source=SOURCE,source_page='https://database.nikonoel.fr/',license='CC0-1.0',games=games,rejected=errors,positions=positions,entries=entries,max_plies=args.plies,min_games=2,selection='2500+ versus 2300+, excluding bullet; online rated games, not the over-the-board Masters database',sha256=hashlib.sha256(args.archive.read_bytes()).hexdigest())
    db.execute('INSERT INTO metadata VALUES(?)',(json.dumps(meta),));db.commit();db.execute('VACUUM');db.close()
    staging.replace(target)
    (ROOT/'data/opening-book.json').write_text(json.dumps(meta,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(meta),flush=True)

if __name__=='__main__':main()

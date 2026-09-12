"""Read the shipped reference without importing it into a personal library."""
import json
from pathlib import Path
import sqlite3
from .chess import Chess

BOOK=Path(__file__).resolve().parents[1]/'data/opening-book.sqlite3'

def lookup(fen):
    if not BOOK.is_file():
        raise ValueError('Bundled opening book is missing. Reinstall the complete application or run tools/build_opening_book.py.')
    db=sqlite3.connect(BOOK.as_uri()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    try:
        meta=json.loads(db.execute('SELECT body FROM metadata').fetchone()[0])
        rows=[dict(r) for r in db.execute('SELECT san,white,draws,black,white+draws+black AS games FROM moves WHERE hash=? ORDER BY games DESC,san',(Chess(fen).key(),))]
        return dict(source='bundled',fen=fen,moves=rows,games=[],reference_games=[],total=sum(m['games'] for m in rows),book=meta)
    finally:
        db.close()

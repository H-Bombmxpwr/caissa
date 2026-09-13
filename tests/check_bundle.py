"""Smoke-test the built executable without touching the real library."""
import hashlib
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
bundle=ROOT/'dist/Caissa'
for name in ['data/opening-book.sqlite3','js/notation.js','js/sounds.js','js/library-tools.js','css/library-tools.css','js/computer.js','js/autocomplete.js','css/polish.css','js/workspace.js']:
    expected=(ROOT/name).read_bytes()
    actual=(bundle/'_internal'/name).read_bytes()
    assert hashlib.sha256(actual).digest()==hashlib.sha256(expected).digest(),name
with tempfile.TemporaryDirectory(prefix='caissa-bundle-') as folder:
    result=subprocess.run([str(bundle/'Caissa.exe'),'--smoke'],env=dict(os.environ,DATA_DIR=folder),timeout=45,capture_output=True)
    assert result.returncode==0,(result.returncode,result.stderr.decode(errors='replace'))
    assert (Path(folder)/'library.db').is_file()
    with closing(sqlite3.connect(Path(folder)/'library.db')) as db:
        assert db.execute('SELECT COUNT(*) FROM games').fetchone()[0]==0
print('PASS: bundled executable starts with an empty temporary library; offline book and new assets match the source')

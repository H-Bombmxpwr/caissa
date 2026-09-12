"""Build the ECO opening index from lichess's chess-openings data set.

The data is CC0 ("As a collection of facts, this data set is in the public domain"),
carries the moves for every line, and distinguishes what a bare ECO code cannot: E87
alone is three different Saemisch variations. Keying on the position after each line's
moves means a game reaches the right name even when it transposes into it.

    py tools/fetch_openings.py
"""
import csv
import io
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from backend.chess import Chess                                   # noqa: E402

BASE = 'https://raw.githubusercontent.com/lichess-org/chess-openings/master/'
TARGET = os.path.join(ROOT, 'data', 'openings.eco.json')

index, skipped, rows = {}, 0, 0
for volume in 'abcde':
    text = urllib.request.urlopen(BASE + volume + '.tsv', timeout=60).read().decode('utf-8')
    for row in csv.DictReader(io.StringIO(text), delimiter='\t'):
        eco, name, moves = row.get('eco'), row.get('name'), row.get('pgn')
        if not (eco and name and moves):
            continue
        rows += 1
        game = Chess()
        plies = 0
        for token in moves.split():
            if token.endswith('.') or token[0].isdigit() and '.' in token:
                continue
            if not game.move(token):
                break
            plies += 1
        else:
            # Deeper lines win, so a game is named as precisely as its moves allow.
            key = game.key()
            if key not in index or plies > index[key][2]:
                index[key] = [eco, name, plies]
            continue
        skipped += 1

with open(TARGET, 'w', encoding='utf-8') as handle:
    json.dump(index, handle, separators=(',', ':'), sort_keys=True)

print('%d lines read, %d positions indexed, %d unplayable' % (rows, len(index), skipped))
print('wrote %s (%.0f KB)' % (TARGET, os.path.getsize(TARGET) / 1024))

"""Fetch redistributable SVG piece sets from lichess, preserving upstream credits.

Every set here is credited in assets/piece/CREDITS.md with its author and licence.
Two of them carry conditions worth knowing before you redistribute this repository:
alpha is "free for personal non commercial use" (lichess lists it as non-free), and
maestro is CC BY-NC-SA 4.0. Both are fine for personal study; neither is fine to sell.
"""
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1] / 'assets' / 'piece'
BASE = 'https://raw.githubusercontent.com/lichess-org/lila/master/'

# name -> (label, author, licence)
SETS = {
    'merida':   ('Merida',   'Armando Hernandez Marroquin', 'GPLv2+'),
    'chessnut': ('Chessnut', 'Alexis Luengas', 'Apache 2.0'),
    'alpha':    ('Alpha',    'Eric Bentzen', 'free for personal non-commercial use'),
    'fantasy':  ('Fantasy',  'Maurizio Monge', 'MIT'),
    'celtic':   ('Celtic',   'Maurizio Monge', 'MIT'),
    'spatial':  ('Spatial',  'Maurizio Monge', 'MIT'),
    'rhosgfx':  ('Rhos',     'RhosGFX', 'CC0 1.0'),
    'maestro':  ('Maestro',  'sadsnake1', 'CC BY-NC-SA 4.0'),
}

for name in SETS:
    folder = ROOT / name
    folder.mkdir(parents=True, exist_ok=True)
    for color in 'wb':
        for piece in 'KQRBNP':
            filename = color + piece + '.svg'
            data = urllib.request.urlopen(BASE+'public/piece/'+name+'/'+filename, timeout=30).read()
            if b'<svg' not in data:
                raise ValueError('Expected SVG: '+name+'/'+filename)
            (folder / filename).write_bytes(data)
    print('Fetched', name)

(ROOT / 'LICHESS-COPYING.md').write_bytes(urllib.request.urlopen(BASE+'COPYING.md',timeout=30).read())
(ROOT / 'GPL-2.0.txt').write_bytes(urllib.request.urlopen('https://www.gnu.org/licenses/old-licenses/gpl-2.0.txt',timeout=30).read())
(ROOT / 'Apache-2.0.txt').write_bytes(urllib.request.urlopen('https://raw.githubusercontent.com/LexLuengas/chessnut-pieces/master/LICENSE.txt',timeout=30).read())
(ROOT / 'MIT-chess-art.txt').write_bytes(urllib.request.urlopen('https://raw.githubusercontent.com/maurimo/chess-art/main/LICENSE',timeout=30).read())

rows = ['| Set | Author | Licence |', '| --- | --- | --- |',
        '| cburnett (default) | Colin M.L. Burnett | GPLv2+ |']
rows += ['| %s | %s | %s |' % (label, author, licence) for label, author, licence in SETS.values()]
(ROOT / 'CREDITS.md').write_text(
    '# Bundled piece sets\n\n'
    'All sets come from [lichess](https://github.com/lichess-org/lila/tree/master/public/piece);\n'
    '`LICHESS-COPYING.md` is their upstream credits file. Refresh them with\n'
    '`py tools/fetch_pieces.py`.\n\n' + '\n'.join(rows) + '\n\n'
    'Alpha and Maestro are free to use personally but not commercially. Everything else\n'
    'here is free software or public domain.\n', encoding='utf-8')
print('Wrote CREDITS.md')

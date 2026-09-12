"""Fetch redistributable SVG piece sets from lichess, preserving upstream credits."""
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1] / 'assets' / 'piece'
BASE = 'https://raw.githubusercontent.com/lichess-org/lila/master/'
for name in ('merida', 'chessnut'):
    folder = ROOT / name
    folder.mkdir(parents=True, exist_ok=True)
    for color in 'wb':
        for piece in 'KQRBNP':
            filename = color + piece + '.svg'
            data = urllib.request.urlopen(BASE+'public/piece/'+name+'/'+filename, timeout=30).read()
            if b'<svg' not in data:
                raise ValueError('Expected SVG: '+filename)
            (folder / filename).write_bytes(data)
    print('Fetched', name)
(ROOT / 'LICHESS-COPYING.md').write_bytes(urllib.request.urlopen(BASE+'COPYING.md',timeout=30).read())
(ROOT / 'GPL-2.0.txt').write_bytes(urllib.request.urlopen('https://www.gnu.org/licenses/old-licenses/gpl-2.0.txt',timeout=30).read())
(ROOT / 'Apache-2.0.txt').write_bytes(urllib.request.urlopen('https://raw.githubusercontent.com/LexLuengas/chessnut-pieces/master/LICENSE.txt',timeout=30).read())

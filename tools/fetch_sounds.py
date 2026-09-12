"""Fetch the bundled sound sets, so nobody has to hand-pick audio files.

Two sources, and they are not on the same footing:

* **lichess** publishes its sound sets in lichess-org/lila under licences that permit
  redistribution — AGPLv3+ for the sets by Enigmahack and the lila authors, CC BY-NC-SA
  4.0 for lisp. They are fetched into `assets/sound/` and committed, exactly as the SVG
  piece sets already are, with every author and licence recorded in CREDITS.md.

* **chess.com** does not. Its audio is proprietary and its terms do not allow us to
  redistribute it, so it is never committed: `--chesscom` downloads it into
  `assets/sound/chesscom/`, which .gitignore keeps out of the repository. The sounds
  play locally for whoever fetched them and travel no further.

Usage:
    py tools/fetch_sounds.py              # the lichess sets
    py tools/fetch_sounds.py --chesscom   # also fetch chess.com's, for this machine only
    py tools/fetch_sounds.py --only piano standard
"""
import argparse
import json
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1] / 'assets' / 'sound'
LILA = 'https://raw.githubusercontent.com/lichess-org/lila/master/public/sound/'
CHESSCOM = 'https://images.chesscomfiles.com/chess-themes/sounds/_MP3_/default/'
AGENT = {'User-Agent': 'Caissa chess study (local, non-commercial)'}

# lichess set -> (label, author, licence). Taken from lila's own COPYING.md; the sets
# it does not list separately fall under the repository's AGPLv3+.
LICHESS_SETS = {
    'standard':   ('Lichess standard', 'the lila authors', 'AGPLv3+'),
    'piano':      ('Lichess piano', 'Enigmahack', 'AGPLv3+'),
    'sfx':        ('Lichess sfx', 'Enigmahack', 'AGPLv3+'),
    'futuristic': ('Lichess futuristic', 'Enigmahack', 'AGPLv3+'),
    'nes':        ('Lichess NES', 'Enigmahack', 'AGPLv3+'),
    'lisp':       ('Lichess lisp', 'EdinburghCollective', 'CC BY-NC-SA 4.0'),
    'robot':      ('Lichess robot', 'the lila authors', 'AGPLv3+'),
    'woodland':   ('Lichess woodland', 'the lila authors', 'AGPLv3+'),
}

# The events this app plays, mapped onto the file each source names them with.
# lichess ships no castle or promotion sound of its own, so those reuse Move —
# which is what lichess itself plays for them.
LICHESS_FILES = {
    'start': 'Confirmation', 'move': 'Move', 'opponent': 'Move', 'capture': 'Capture',
    'castle': 'Move', 'check': 'Check', 'promotion': 'Move', 'end': 'Checkmate',
    'illegal': 'Error', 'notify': 'GenericNotify', 'lowtime': 'LowTime', 'premove': 'Select',
}
CHESSCOM_FILES = {
    'start': 'game-start', 'move': 'move-self', 'opponent': 'move-opponent',
    'capture': 'capture', 'castle': 'castle', 'check': 'move-check',
    'promotion': 'promote', 'end': 'game-end', 'illegal': 'illegal',
    'notify': 'notify', 'lowtime': 'tenseconds', 'premove': 'premove',
}


SILENCE = 'Silence'


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=60) as res:
        return res.read()


def resolve(url, depth=3):
    """Fetch a file, following the symlinks lila uses to share sounds between sets.

    A symlink in git is a file whose contents are the target path, and that is what
    raw.githubusercontent hands back — so a 14-byte "../Silence.mp3" arrives where an
    MP3 was expected. Following it is how a set that borrows the standard Move sound
    ends up with the sound rather than with the word.

    Returns (bytes, silent). `silent` is True when the trail ends at lila's Silence
    file, which is lichess's way of saying this set plays nothing for this event.
    """
    data = get(url)
    for _ in range(depth):
        if len(data) > 256 or b'\n' in data.strip():
            break                                   # too big to be a path: it is audio
        try:
            target = data.decode('ascii').strip()
        except UnicodeDecodeError:
            break
        if not target.endswith(('.mp3', '.ogg')) or ' ' in target:
            break
        if Path(target).name.startswith(SILENCE):
            return b'', True
        url = urllib.parse.urljoin(url, target)
        data = get(url)
    return data, False


def fetch_set(name, files, base, suffix='.mp3'):
    """Download one set. An event the source leaves silent is recorded as absent."""
    folder = ROOT / name
    folder.mkdir(parents=True, exist_ok=True)
    written, missing = {}, []
    for event, stem in files.items():
        try:
            data, silent = resolve(base + stem + suffix)
        except (urllib.error.HTTPError, urllib.error.URLError) as err:
            missing.append('%s (%s)' % (event, err))
            continue
        if silent:
            missing.append('%s (silent upstream)' % event)
            continue
        if len(data) < 64:
            missing.append('%s (not audio)' % event)
            continue
        target = folder / (event + '.mp3')
        target.write_bytes(data)
        written[event] = target.name
    (folder / 'manifest.json').write_text(json.dumps(written, indent=2), encoding='utf-8')
    return written, missing


def write_credits(fetched):
    lines = [
        '# Sound credits',
        '',
        'Every bundled sound set comes from lichess (lichess-org/lila, `public/sound`),',
        'fetched by `tools/fetch_sounds.py`. The licence below is the one lila records',
        'for that set; where lila lists no separate licence the set is covered by the',
        "repository's own AGPLv3+.",
        '',
        '| Set | Author | Licence |',
        '| --- | --- | --- |',
    ]
    for name, (label, author, licence) in LICHESS_SETS.items():
        if name in fetched:
            lines.append('| `%s` — %s | %s | %s |' % (name, label, author, licence))
    lines += [
        '',
        '## chess.com',
        '',
        "chess.com's sounds are proprietary and are **not** part of this repository.",
        '`py tools/fetch_sounds.py --chesscom` downloads them to `assets/sound/chesscom/`',
        'on your own machine, where `.gitignore` keeps them out of version control. Use',
        'them for your own study; do not redistribute them.',
        '',
        '## Caissa presets',
        '',
        'The `wood` and `digital` sets are synthesized in `js/sounds.js` and are part of',
        'this project. They need no download and are always available.',
    ]
    (ROOT / 'CREDITS.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chesscom', action='store_true',
                        help="also fetch chess.com's proprietary sounds, for this machine only")
    parser.add_argument('--only', nargs='*', metavar='SET', help='limit to these lichess sets')
    args = parser.parse_args()

    wanted = args.only or list(LICHESS_SETS)
    unknown = [name for name in wanted if name not in LICHESS_SETS]
    if unknown:
        parser.error('unknown set(s): ' + ', '.join(unknown))

    fetched = {}
    for name in wanted:
        written, missing = fetch_set(name, LICHESS_FILES, LILA + name + '/')
        fetched[name] = written
        print('%-12s %2d sounds%s' % (name, len(written),
                                      '  (missing: ' + ', '.join(missing) + ')' if missing else ''))
    write_credits(fetched)

    if args.chesscom:
        written, missing = fetch_set('chesscom', CHESSCOM_FILES, CHESSCOM)
        print('%-12s %2d sounds%s' % ('chesscom', len(written),
                                      '  (missing: ' + ', '.join(missing) + ')' if missing else ''))
        print("chess.com's sounds are proprietary: they stay in assets/sound/chesscom/,\n"
              'which .gitignore keeps out of the repository. Do not redistribute them.')

    print('\nWrote', ROOT)
    return 0


if __name__ == '__main__':
    sys.exit(main())

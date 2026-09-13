# Move sounds

Three kinds of sound set, chosen in **Settings → Sound → Move sounds**.

The same sound settings apply to every moving chess board: analysis, the opening
explorer's Collection tree and Reference databases, computer play, repertoire drills,
and blindfold exercises. Mouse moves, keyboard moves and automatic replies all use
the shared board sound player. Captures, checks, castling, promotion and checkmate
use their corresponding event; backward navigation and jumps use one move sound.
Initial board setup and repeated redraws are silent. Volume, disabled events and
the **Off** sound set are respected everywhere.

## Bundled sample sets

The lichess sound sets ship with the app: **standard**, **piano**, **sfx**,
**futuristic**, **NES**, **lisp**, **robot** and **woodland**. Choose one and it works —
there are no files to supply.

Fetch or refresh them with:

```powershell
py tools\fetch_sounds.py
py tools\fetch_sounds.py --only piano standard
```

Twelve events get a sound: game start, your move, opponent move, capture, castling,
check, promotion, game end, illegal move, notification, low time, and pre-move.

No set covers all twelve — lichess plays nothing for check or checkmate in its standard
set, and ships no castling sample anywhere. A missing sample is borrowed: from your
chosen set, then from lichess standard, then from any installed set that has one, and
only then from the synthesized preset. The settings row says which set a borrowed sound
came from.

## The chess.com set

chess.com's audio is proprietary and is **not** redistributed here. Fetch it for your own
machine:

```powershell
py tools\fetch_sounds.py --chesscom
```

It lands in `assets/sound/chesscom/`, which `.gitignore` keeps out of the repository and
which the build spec strips out of any executable. Once fetched, it appears in the sound
set dropdown like any other. It is the only set with a genuine sample for all twelve
events, including castling and pre-move.

## Caissa presets

**Caissa wood** and **Caissa digital** are synthesized with an oscillator. They need no
files, work in any build, and are the safe default. You can still attach your own audio
file to an individual event while using them.

## Your own files

**My own audio files** takes a file per event, up to 1 MB each, stored as data URLs in
your library preferences so they travel with the library.

## Credits

Every bundled set's author and licence is recorded in `assets/sound/CREDITS.md`, taken
from lila's own `COPYING.md`. The sets by Enigmahack and the lila authors are AGPLv3+;
the lisp set is CC BY-NC-SA 4.0.

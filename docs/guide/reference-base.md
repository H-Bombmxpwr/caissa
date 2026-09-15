# A reference base

A reference base is a very large PGN — millions of games — that you keep alongside your
library and search, rather than read. Caissa **attaches** one instead of importing it:
the scan records where each game starts in the file, and every reader opens the original
at that offset. Nothing is copied and nothing is rewritten.

That is possible because the library never stored move text in the first place. SQLite
holds a game's headers and three numbers — which file, which byte, how many bytes — and
the moves are read from the PGN when you open the game. An import copies the PGN into a
collection folder so the library owns it. An attach skips the copy.

| | Import | Attach |
| --- | --- | --- |
| Disk for an 8.6 GB base | 8.6 GB copy + index | index only |
| First run | reads and writes 8.6 GB | reads 8.6 GB |
| If the PGN moves | nothing breaks | those games stop opening, and Caissa says so |

Attaching is the right choice for a base you downloaded and will not edit. Importing is
the right choice for everything else, because a collection that owns its PGN is a
collection you can move, rename and delete without thinking about it.

## The recommended setup

This is the setup the guide is written against, and a good default:

```
Documents/Chess Analysis/          your library folder
  library.db                       headers, offsets, positions, repertoires
  reference/
    LumbrasGigaBase_OTB_Complete.pgn    8.6 GB · ~10 million games · attached
  collections/
    my-games/                      your own games, imported from Lichess
    masters-carlsen-najdorf/       carved out of the base, position-indexed
  studies/
    reference/                     the base, filed as a study folder
  books/                           PDFs you read beside the board
```

One large base for breadth, your own games for the Player Lab, and small collections cut
out of the base for the openings you actually study. The base answers *did anyone ever
play this, and how did it go*; the carved collections answer *what should I play here*,
because those are the ones the opening explorer reads.

### Getting a base

Caissa does not ship one — a games database is somebody else's compilation, and the
project only bundles material it is licensed to. Supply your own:

- **Lumbras GigaBase** — a free community compilation of over-the-board games, published
  as a `.7z` archive. What this guide's example uses.
- **A ChessBase export** — export a database to PGN from ChessBase itself. Caissa does
  not read CBH, CBV or SI4.
- **TWIC archives** — every issue of The Week in Chess, concatenated.

Extract the archive first: Caissa attaches `.pgn` files, not archives. Windows can do it
from the command line without installing anything:

```powershell
mkdir "$env:USERPROFILE\Documents\Chess Analysis\reference"
tar -xf "$env:USERPROFILE\Downloads\LumbrasGigaBase_OTB_Complete.7z" `
    -C "$env:USERPROFILE\Documents\Chess Analysis\reference"
```

Put the `.pgn` in a `reference` folder inside your library. That is where Caissa looks.

## Attaching it

Open **Master games**. A PGN sitting unattached in `reference/` is offered by name, with
its path already filled in — press **Attach**. The scan reads the file once at roughly
4,000 games a second, so a ten-million-game base takes about three quarters of an hour,
and the progress card in the corner counts as it goes.

What you get:

- A collection named after the file, filed under a **Reference** study folder.
- Roughly 600 bytes of database per game — about 6 GB for ten million.
- No second copy of the PGN.

To attach a base that lives somewhere else, type its full path instead. A path inside
the library is stored relative to it, so moving the whole library folder keeps working;
an outside path is stored as given.

## Working with it

**Master games** is built around two jobs, because at this size there is no browsing.

### Finding one game

Every field narrows the same search: player, colour, outcome, opponent, tournament,
rating floor, opening name, ECO range, years. A surname alone finds a career, and the box
suggests names from the base as you type.

**Player and tournament match from the start of the name**, not anywhere inside it.
Names in most bases are stored *Surname, First*, so `Carlsen` finds Carlsen, Magnus, and
`Carlsen, M` narrows it further; a forename on its own finds nothing. Capitalisation does
not matter. This is what keeps the search instant: a prefix is a range an index answers
directly, while a substring means reading all ten million rows — about thirty-five
seconds a search. The database's own free-text box still matches anywhere in a name, for
when that is what you need.

**Opponent or free text** searches the whole game record — both players, event, site,
annotator — the same way the database's search box does.

Results list the forty highest-rated matches; opening one puts it on the analysis board,
read straight out of the base. **Open in the database** takes the same search to the
game list, where you can sort and page through all of it.

### Cutting a collection out of it

This is what the base is for. Search for something worth studying — *Carlsen, Najdorf,
2015 onwards* — and choose **Save as a collection**. The matching games are shelved into
a collection of their own. They are not copied: the collection points at the same PGN.

Tick **Index its positions** and the new collection is indexed as soon as it is saved.
That is the step that matters, because indexing is what the opening explorer, the
position context panel and the Player Lab read.

## Why the base itself is not position-indexed

The position index holds one row per half-move, so it can answer "what was played from
here" for any position. A collection of a thousand games is about eighty thousand rows.
Ten million games would be eight hundred million — tens of gigabytes, hours to build, and
slower to query than the thing it is meant to accelerate.

So the base stays header-only, and indexing is something you spend on the few hundred
games you are actually studying. If you want broad offline coverage for the explorer,
carve a wide slice — every game over 2500, say — and index that instead of the whole
base.

## Keeping it

**The PGN has to stay where it is.** If you move or delete it, the games remain in the
index but cannot be opened, and Master games says which base is broken. Put the file
back, or detach and attach it again from its new home.

**Detach** is under the ⋯ on the base's card. It forgets the games and leaves the PGN
alone. Collections carved out of the base shelve its games rather than copies, so they
would be emptied too — Caissa refuses the first time and names them, and only goes ahead
if you ask again. If you want to keep a carved collection permanently, export it to PGN
and import that copy.

**A base is a snapshot.** It stops at the day it was published. Keep it current with
**The Week in Chess** — one issue per week, imported normally — or re-download the base
and attach the new file.

**Attaching again is safe.** If a scan is interrupted — the machine ran short of memory,
the app was closed — attach the same file again and it starts over cleanly rather than
doubling up. A base that was left half-scanned still shows in Master games, so you can
see that it needs finishing.

## What it costs

Measured on the setup above, with Lumbras GigaBase OTB Complete:

| | |
| --- | --- |
| PGN | 8.6 GB, about 10 million games |
| Scan | roughly 45 minutes, about 4,000 games a second |
| Database | about 600 bytes a game, roughly 6 GB |
| Copied | nothing |

Search timings on ten million games:

| Search | Time |
| --- | --- |
| Player, or player with an opening, a rating floor and a year range | under a second |
| Tournament by name | under a second |
| Rating floor, year range or opening name **alone** | several seconds |
| Free text alone | ten seconds or more |

Naming a person or an event lets the search read an index and stop; everything else has
to consider most of the base. So lead with a name, then narrow — which is how you would
search anyway. Master games says which kind of search it is running.

Indexing a carved collection of a thousand games takes seconds.

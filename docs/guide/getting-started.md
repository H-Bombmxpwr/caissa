# Getting started

## Install and run

Fetch the engine first. It is about 80 MB and is deliberately not stored in git:

```powershell
py tools\fetch_stockfish.py
```

Then install the dependencies and start the app. Caissa uses
[uv](https://docs.astral.sh/uv/); `uv sync` creates `.venv` and installs the exact
versions recorded in `uv.lock`, so you never create or activate an environment yourself:

```powershell
uv sync
uv run desktop.py
```

`uv sync --no-dev` installs only the two packages the application needs, without the
test, build and documentation tooling. If you would rather not install uv,
`py -m venv .venv` followed by `.venv\Scripts\python -m pip install pywebview psutil`
gets you the same runtime by hand.

`desktop.py` opens a native window (Edge WebView2 through pywebview). Other ways in:

| Command | What it does |
| --- | --- |
| `py desktop.py` | the app in its own window |
| `py desktop.py --browser` | the same app in your default browser |
| `py desktop.py --smoke` | start, check health, print paths, exit — useful in CI |
| `py server.py` | plain HTTP server on <http://localhost:8000>, no window |

Two optional fetches round out the install:

```powershell
py tools\fetch_sounds.py      # bundled lichess move sounds
py tools\fetch_pieces.py      # the alternative SVG piece sets
```

## Where your library lives

On Windows the library is `%APPDATA%\Caissa\library`, whether you launched from source
or from the built executable. It sits outside the application folder on purpose: you can
delete the app, download it again, and your games and settings are still there.

```
library/
  library.db          the SQLite index
  collections/        one folder per collection, each holding games.pgn
  studies/            study folders, with a study.json manifest each
  books/              PDFs you have added
```

> **Important**
>
> `library.db` is an *index*, not the library. Every game is a run of bytes inside a
> `games.pgn` file, and the database only records where. If the index is lost you have
> lost search, not chess — re-import the PGN files and everything comes back.

Move the library somewhere else from **Settings → Storage folder**. The change takes
effect at the next launch, and the current library stays active until then.

## Your first session

1. **Import something.** Go to **Import games** and either choose a PGN file or paste
   one in. Name the collection first — it is required, because an unnamed pile of games
   is what makes a database hard to use later.
2. **Look at the list.** The **Database** module shows what you imported. Sort it,
   search it, and use **Filters** for anything more specific than the search box.
3. **Open a game.** Double-click a row. The analysis board opens with the moves, the
   engine panel and the context tabs.
4. **Turn on the engine.** Tick **Live analysis**. Stockfish runs locally and the board
   draws an arrow per line, each in its own colour.
5. **Keep something.** Select the move you care about and choose **Add to repertoire**,
   or pin a note to the position from the **Study** tab.

## The modules

| Module | What it is for |
| --- | --- |
| **Database** | every game, with search, filters, sorting and bulk deletion |
| **Analysis board** | one game at a time: moves, engine, notes, context, panels |
| **Repertoire** | your opening lines, and the drills that rehearse them |
| **Master games** | building a reference library from free collections |
| **Import games** | PGN, archives, URLs, online accounts, lichess studies |
| **Study folders** | organising collections into folders on disk |
| **Tactics** | Chess Tempo, plus your own problem sets |
| **Books** | PDFs, readable beside the board |
| **Blindfold** | the seven-level visualisation trainer |
| **Settings** | board, pieces, sounds, storage, and your lichess account |

## Working offline

Everything that matters works with no connection: your games, the engine, the bundled
opening book, your PDFs, and every blindfold exercise. Only these need the network, and
each says so when it cannot reach it:

- importing from lichess or chess.com
- the online opening explorer (Masters and rated games)
- the seven-piece endgame tablebase
- Wikipedia background on the **Facts** tab

Lookups you have already made are cached in your library, so yesterday's tablebase
answer is still there today.

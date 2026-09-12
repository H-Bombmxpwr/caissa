# Caissa

A desktop chess workbench — a lighter ChessBase. It keeps a local database of games as ordinary
PGN files, analyzes them with a bundled Stockfish, builds and drills opening repertoires, pulls in
master games and your own online games, links positions to free study material and chess history,
and trains blindfold visualization.

See [SCOPE.md](SCOPE.md) for what the app is, what it is not, and where it is going.

## Running it

First time only — fetch the engine (about 80 MB, not stored in git):

```powershell
py tools\fetch_stockfish.py
```

Then, from source:

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python desktop.py
```

`desktop.py` opens a native window (Edge WebView2 via pywebview). Useful flags:

| Command | What it does |
|---|---|
| `py desktop.py` | the app in its own window |
| `py desktop.py --browser` | same app, opened in your default browser |
| `py desktop.py --smoke` | start, check health, print paths, exit |
| `py server.py` | plain server on <http://localhost:8000>, no window |

Your library lives in `./library` when running from source and in
`%APPDATA%\Caissa\library` once installed. Override either with `DATA_DIR`.

## Building the .exe

```powershell
.venv\Scripts\python -m pip install pyinstaller
.\build.ps1
```

Output lands in `dist\Caissa\`. Stockfish and the web assets are bundled in.

## Where things live

```
desktop.py            native-window entry point
server.py             HTTP server: static app + JSON API
backend/
  store.py            the library — PGN files on disk + SQLite index
  api.py              JSON API routes
  chess.py            chess rules in Python (0x88, perft-verified)
  study.py            position index, pins, study folders on disk
  literature.py       free study material for a position
  importers.py        PGN / ZIP / GZ / BZ2 / ZST / EPD / CSV, folders, URLs, chess.com
  pgnutil.py          PGN splitting, tag parsing, move extraction
  engine.py           bundled Stockfish over UCI, plus batch annotation
  lichess.py          throttled lichess client, masters crawler, dump importer
js/
  workspace.js        the desktop workspace: database, analysis, repertoire, studies
  engine.js           chess rules in the browser (0x88, perft-verified)
  board.js            chessground-style board: transforms, drag, shapes, blindfold
  app.js              the blindfold trainer shell: levels, peek control, stats
  pgn.js              PGN reader with variations
  ai.js / stockfish.js  in-browser fallback engines
  drills/l1..l7.js    the seven blindfold levels
data/                 openings, endgames, studies, lectures.json
tools/                fetch_stockfish.py, make_icon.py
assets/               the Caissa mark (png + generated ico)
vendor/stockfish/     the bundled engine (fetched, gitignored)
library/              your games, studies and index (gitignored)
tests/                see below
```

## Tests

```powershell
py -m unittest discover -s tests -p "test_*.py"    # backend: 52 tests, no network
powershell -File tests\run.ps1                     # chess engine perft + SAN + data validity
```

The Python suite covers the library, every API route the workspace calls, the position index and
its transposition keys, study folders, literature links, and the Python rules engine on the five
standard perft positions.

`tests/run.ps1` puts the JavaScript rules engine through the same perft positions under Windows
Script Host (no Node needed on this machine), plus SAN round-trips and a legality check of every
stored opening, endgame and study.

Browser-side checks, with the app running (`py server.py`):

- <http://localhost:8000/tests/workspace-smoke.html> — opens every workspace module, plays a
  move on the analysis board, walks the context tabs, reports uncaught errors
- <http://localhost:8000/tests/smoke.html> — mounts every training level, pokes it, reports errors
- <http://localhost:8000/tests/visual.html> — board renderer preview

Each can be run headlessly, which is how they are checked here:

```powershell
msedge --headless=new --virtual-time-budget=30000 --dump-dom `
  http://localhost:8000/tests/workspace-smoke.html
```

## Blindfold training

The original seven-level trainer is now a module inside the app. Hold `Space` or the **Peek**
button to reveal the board; peeks are counted. Two blindfold styles, as on lichess: hide the
pieces (board and coordinates stay) or hide the board entirely. Peeking never reveals computed
answers — only the position itself.

## Licensing and credits

Bundling Stockfish (GPLv3) and the cburnett piece set (GPL) makes this application **GPLv3**.

- [Stockfish](https://github.com/official-stockfish/Stockfish) — engine
- [lichess](https://lichess.org) — cburnett pieces, game export API, tablebase
- Chess Tempo — tactics, used in-app through their own site, never copied
- Exercises: AdviceCabinet, *7 Levels of Blindfold Chess Exercises for Everyone*

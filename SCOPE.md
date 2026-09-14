# Caissa — Scope

_Last updated: 2026-09-13_

## Player analysis

Player lab now provides local player-pattern reports, opponent prep with online
imports, saved-evaluation and clock aggregation, rating-filtered observed moves,
and Stockfish best-move practice with persistent retests. Keyboard board exploration,
optional spoken readout, accessible notation labels, and an experimental training
rating complement these features. See [Player lab](docs/guide/player-lab.md).

Maia inference, validated tactical motifs, population comparisons, theory departures,
rating calibration, and proof of improvement in subsequent games remain future work.

## What this is

A **downloadable desktop chess application** — a lighter ChessBase. It owns a local
database of games, analyzes them with a bundled Stockfish, helps build and drill opening
repertoires, pulls in master games and your own online games, links each position to free
study material, and trains blindfold visualization.

It started as a browser-based blindfold trainer (the seven exercises). That trainer is now
**one module inside the app**, not the whole thing.

### The one-line test

> Open the app, double-click a game you played last night, see where it went wrong, add the
> refutation to your repertoire, watch the free lecture that covers the position, then drill
> the line blindfolded — without leaving the app or being online.

## What it is not

- Not a chess server — you do not play live opponents in it.
- Not a ChessBase clone feature-for-feature. No CBH writing, no printing, no cloud accounts.
- Not a website. It runs as an installed application; a web build stays possible because the
  UI is HTML, but the browser is not the target.

## Shape of the thing

```
Caissa.exe            PyInstaller bundle
  ├── pywebview window        native window hosting the UI (Edge WebView2)
  ├── local HTTP server       the same API the browser build uses, on 127.0.0.1
  ├── Stockfish (bundled)     real binary, UCI over a pipe, full CPU
  └── library/                your data — PGN files + SQLite index
```

- **Backend**: Python standard library, `psutil` for engine resource measurements,
  and `pywebview` for the window. No web framework.
- **Frontend**: plain HTML/CSS/JS, no build step, no npm. Chess rules run in the browser engine
  (`js/engine.js`) so the board is instant; the backend has its own copy (`backend/chess.py`) for
  indexing positions during import. Both are perft-verified against the same five positions.
- **Data**: games live as ordinary `.pgn` files in `library/collections/<name>/games.pgn`; SQLite
  indexes them (offset + length per game) for instant search. Your data stays portable — any
  other program can read those files.
- **Default library location**: `%APPDATA%\Caissa\library` for source and installed
  launches. Legacy source libraries are copied on first launch; override with `DATA_DIR`.
  Desktop Settings includes a native folder picker. The chosen folder is remembered
  outside the installation; the library is copied on next launch and the original retained.

## Modules

The shipped offline book contains 280,246 high-rated Lichess games represented by
346,642 positions and 450,114 continuations through 24 moves. It is prebuilt and
independent of the personal library; online Masters and rated-game references remain
available for broader coverage. See `data/OPENING-BOOK-CREDITS.md` for provenance.
Analysis includes keyboard navigation, collapsible variation trees, native PGN export,
full-width panels, PGN header display, and configurable move sounds and animation speed.
Study folders display an explicit nested tree and unfiled collections separately.

The workbench now includes a local PDF Books module and an Opening book with local
PGN statistics plus cached Lichess Masters and rated-game references, without a fixed depth cutoff;
both can also be enabled as analysis panels. PDFs can open in a separate reading
window. ChessBase CTG/CTB/CTO and Polyglot BIN book import are not implemented.
Database metadata includes tournament, round, annotator and annotation status, with
combined filters and categorized study folders. Position indexing is accessible from
Database, Study folders, Opening book and analysis. Imported prose comments and
termination tags are retained; result codes alone are never treated as resignation.

### 1. Database (the spine)
- Collections of games; import, search, sort, tag, delete, export.
- Search by player, event, ECO, opening, result, year, rating, length, collection.
- Position search — "show me games that reached this position" — via the move index.
- Duplicate detection on import (source id first, then header+moves signature).
- Everything else in the app reads and writes through this.

### 2. Analysis board
- Open any game; step, branch, and annotate; variations tree; NAGs and text comments.
- Bundled Stockfish: live eval, best lines (multi-PV), and **batch annotation** of a whole game
  in the background — blunder/mistake/inaccuracy tags stored in the database.
- Save annotations back into the game's PGN.
- Position → everything: which of your games reached it, what masters played, what literature
  covers it, what you have pinned to it.

### 3. Repertoire
- White and Black trees, built by hand, from your own games, or from master games.
- Coverage report: where the tree ends but opponents keep playing; transposition detection.
- Drill mode with spaced repetition, normal or blindfolded (shares the level-3 engine).
- Stored in the database, exportable as PGN with variations.

### 4. Openings and master games
- Master game sources (free, no account needed):
  - **The Week in Chess** — 1,661 weekly zips, ~2,500 games each (~4M games). Primary bulk source.
  - **PGN Mentor** — per-player and per-event collections.
  - **lichess opening explorer** — *now requires a free API token* (returns 401 without one);
    supported when you paste a token, optional otherwise.
- Position statistics computed from your own library, so the explorer is a bonus and not a
  dependency.

### 5. Your online games
- **lichess**: import by username, all the filters the API offers, throttled server-side so the
  "one export at a time" limit is never tripped.
- **chess.com**: public API by username (verified working, monthly archives).
- Both dedupe against what is already in the library, so re-importing is safe and cheap.

### 6. Literature and video for a position
Three layers, in order of certainty:
1. **Deterministic free sources** — always correct, no keys:
   - Wikibooks *Chess Opening Theory* (exact move-path URLs, existence-checked via the MediaWiki API)
   - the lichess opening page for the named opening
   - the Wikipedia article for the opening
2. **Curated video index shipped with the app** — a JSON file mapping openings/ECO codes to free
   lectures (Naroditsky speedruns, Saint Louis Chess Club, Hanging Pawns and friends). Seeded by
   us, extensible by you, updatable without a new release.
3. **Your own pinned links and notes**, attached to a position by FEN so they resurface through
   any transposition. This is the part that compounds — your knowledge base, in your file.

Not in scope: scraping YouTube without an API key, or anything that redistributes paid content.

### 7. History — where ideas came from

Chess knowledge has provenance, and the app should hand it to you for whatever you are looking
at: a position, an opening, a player, a game.

- **Position provenance.** For the position on the board: the earliest game in the library that
  reached it, who played it, and where. "First seen: Labourdonnais–McDonnell, London 1834" is a
  fact the library can answer by itself once positions are indexed.
- **Opening timeline.** Games per decade for this opening, its peak era, when it fell out of
  fashion and when it came back, and the players most associated with it — all computed from the
  master database rather than scraped.
- **Player pages.** Reachable from any game: era, record in the library, favourite openings, most
  famous games, plus a free Wikipedia summary for the biography.
- **The name itself.** Openings are named after people and places; the panel says who Najdorf,
  Ruy López or Nimzowitsch were and links the free article.
- **Idea lineage.** Where a specific plan or novelty first appears in the library, and the games
  that popularised it afterwards.

Every fact is either computed from your own database (and therefore checkable) or a link to free
material — Wikipedia, Wikibooks, lichess. Nothing invented.

**What this requires**: a position index (see below) and a chess rules engine on the Python side.

### 8. Blindfold training (the original seven levels)
Square colors, piece tours, opening recall, endgame technique, knight-vs-queen tour, studies,
and analyzing your own games blindfolded — now fed by the database instead of a hard-coded list,
with the peek button and per-level statistics intact.

### 9. Tactics

Chess Tempo's problem set is the one worth training on — better curated and better rated than the
alternatives. It is also Chess Tempo's commercial core: their `robots.txt` disallows
`/chess-problems/` and `/chess-tactics/`, and there is no public puzzle API. So the app uses it
rather than copying it:

1. **Chess Tempo in-app** — a tab that opens their trainer in the embedded webview, signed into
   your own account. You get their tactics, their ratings, their spaced repetition, without
   leaving Caissa. This is the primary path.
2. **Your own exports** — problem sets a Chess Tempo membership lets you download (PGN/EPD) import
   like any other file and become a local, blindfold-capable training set.
3. **Puzzles from your own library** — Stockfish scans your games and the master database for
   positions with a forced win that was missed or found, tagged by theme and stored as a local
   set. Nobody else has these: they are your mistakes and your model games.

The lichess puzzle database (4M+ puzzles, CSV, freely downloadable) stays supported as an optional
offline set, but it is not the default.

**Never**: scraping Chess Tempo's problems or circumventing their membership.

## Two pieces of machinery everything leans on

### The position index
A table of `(position hash, game id, ply)` for every recorded ply of every game in an indexed
collection. It is what makes these possible:

- "show me every game that reached this position", including by transposition
- position provenance and opening timelines for the History module
- repertoire gap analysis ("opponents played on here and my tree stops")
- opening statistics from *your* library, so the app is useful with no network at all

Indexing is per collection and opt-in. Full-game indexing uses more disk and CPU than
the original 24-ply opening index. Re-index older collections to include endgames.

### A chess rules engine in Python
`backend/chess.py` mirrors the browser engine (`js/engine.js`): 0x88 move generation, SAN, FEN.
The browser keeps its own copy because the UI must be instant offline; the Python side needs one
to walk games during import (hashing positions, classifying ECO, detecting transpositions)
without a browser in the loop. Both are held to the same standard — the same perft numbers on the
same five positions.

## Importing — "any format it comes in"

| Format | Support |
|---|---|
| `.pgn` | Yes, streamed; multi-gigabyte files are fine |
| `.zip` of PGNs (TWIC, PGN Mentor) | Yes, stdlib `zipfile` |
| `.gz`, `.bz2` | Yes, stdlib |
| `.zst` (lichess dumps) | Yes with the optional `zstandard` package, clear message without it |
| A folder of PGNs | Yes, recursive scan |
| A URL to any of the above | Yes |
| chess.com / lichess accounts | Yes, via their public APIs |
| ChessBase `.cbh`/`.cbv`, Scid `.si4` | **Not supported.** Proprietary/complex binary formats; the app tells you to export to PGN from ChessBase or SCID vs PC rather than pretending. Revisit only if it becomes the main blocker. |

## Non-goals (deliberately cut)

- Playing engine games / online play.
- Cloud sync, accounts, multi-user. One person, one machine, one library.
- Mobile.
- Chess variants. Standard chess only (variant games are skipped on import).
- Printing and publishing layouts.

## Licensing

Bundling Stockfish (GPLv3) and the cburnett piece set (GPL) makes the distributed application
**GPLv3**. The repository carries the license, the Stockfish source link, and attribution for
lichess assets. Nothing here redistributes paid or non-free content.

## Build and distribution

- `python desktop.py` — run the desktop app from source.
- `python server.py` — run the same thing in a browser (development, or a future hosted build).
- `tools/fetch_stockfish.py` — downloads the Stockfish binary into `vendor/` (not committed).
- `build.ps1` → PyInstaller → `dist/Caissa/Caissa.exe`.
- Railway's role, later: a small page that *hosts the download*, not the app itself.

## Status

| | |
|---|---|
| Done | Rules engines in JS **and Python** (both perft-verified), board renderer, seven blindfold levels, library store + SQLite index, JSON API, importers (PGN/ZIP/GZ/BZ2/ZST/EPD/CSV, folders, URLs, lichess, chess.com), bundled Stockfish 19 over UCI, desktop shell, **workspace UI (database, analysis board, repertoire, studies, imports, masters, tactics, appearance)**, **position index with transposition keys**, **study folders on disk**, **literature links**, **history panel**, test suites (52 Python tests, browser engine suites, two browser smokes) |
| In progress | Repertoire drilling polish, masters harvesting, tactics module |
| Next | TWIC bulk harvesting, Chess Tempo tab, puzzles from your own games, installer |
| Later | Tactics from the lichess puzzle DB, server-side batch annotation queue, download page |

## Open questions

- Spaced repetition schedule for repertoire drilling — simple SM-2, or interval buckets?
- How much of the seven-level trainer should read from the database (e.g. level 7 studying only
  your real games) versus staying self-contained?
- Installer: PyInstaller folder + a zip is simplest; an Inno Setup installer would look more like
  a real product. Worth it?

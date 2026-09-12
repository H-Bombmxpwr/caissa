# Architecture

## The shape of it

```{mermaid}
flowchart LR
    W[desktop.py<br/>pywebview window] --> S
    B[browser] --> S[server.py<br/>static files + JSON API]
    S --> A[backend.api<br/>routes]
    A --> L[backend.store<br/>PGN files + SQLite index]
    A --> E[backend.engine<br/>Stockfish over UCI]
    A --> St[backend.study<br/>position index]
    A --> Li[backend.lichess<br/>throttled client]
    L --> D[(library.db)]
    L --> P[(collections/*.pgn)]
```

Two entry points, one server. `desktop.py` opens a native Edge WebView2 window;
`server.py` serves the same application over plain HTTP. There is no build step, no
bundler and no framework: the browser loads the files as they are written.

## Where the chess rules live

Twice, on purpose.

- **`js/engine.js`** is the real one. It runs in the browser, does legality, SAN,
  variations and the move tree, and is perft-verified on the five standard positions.
- **`backend/chess.py`** is a second implementation for the things the server must do
  alone: hashing positions for the index, validating a FEN, and replaying a repertoire
  PGN. It is perft-verified against the same positions.

The server never needs chess rules to import a file. Splitting PGN, reading tags and
pulling out the main line are text operations, which is why a hundred-thousand-game
archive imports without a rules engine touching it.

## Concurrency

- **One write lock** over the library. SQLite handles readers; the lock serialises the
  writers.
- **One connection per thread**, through `threading.local`.
- **Two engine processes**: a long-lived one for batch annotation, and a dedicated one
  for live analysis, so annotating a game cannot stall the arrows on the board.
- **One throttled queue** for lichess, with a shared cooldown after a `429`. The browser
  can ask as often as it likes.
- **Background threads** for indexing, annotation, the masters crawler and sensor
  polling. Each publishes progress through a status endpoint rather than holding a
  request open.

## The front end

`js/workspace.js` is the workbench: modules, the analysis board, panels, dialogs. It is
plain DOM built through a small `h()` helper, with no virtual DOM and no reactivity
system — state changes call a render function.

| File | What it is |
| --- | --- |
| `board.js` | the board: transforms, dragging, shapes, blindfold modes |
| `engine.js` | chess rules in the browser |
| `pgn.js` | PGN reading with variations |
| `notation.js` | the two notation layouts |
| `library-tools.js` | PDF reader, opening book, position library |
| `sounds.js` | sample sets, fallbacks and the synthesized presets |
| `app.js`, `drills/l1..l7.js` | the blindfold trainer |

## Design rules worth keeping

**PGN is the format, not an export.** Games are stored as the text they arrived as. The
database is an index over that text and can be rebuilt from it.

**A missing reading is reported as missing.** The telemetry panel labels a sensor the
machine will not publish rather than estimating it. The same rule applies to Wikipedia
facts and to opening names.

**Destructive things preview first.** Bulk deletion shows the count, a sample and the
filters, and confirms against row identity so a concurrent import cannot widen it.

**Network work happens on the server.** One process, one queue, one place to handle rate
limiting, and one place where a token can be kept out of the page.

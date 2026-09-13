# Testing

Nothing here needs the network, and nothing touches your real library — every suite runs
against a temporary one.

## The Python suite

```powershell
.venv\Scripts\python -m unittest discover -s tests -t . -p "test_*.py"
```

| File | Covers |
| --- | --- |
| `test_backend.py` | the library, importing, search, collections |
| `test_workbench.py` | every API route the workspace calls |
| `test_workspace.py` | filters, sorting, deletion previews, import batches |
| `test_storage.py` | storage relocation and restart persistence |
| `test_chess.py` | the Python rules engine on the five standard perft positions |
| `test_library_tools.py` | books, the opening book, position library |
| `test_facts_matching.py` | Wikipedia matching, including what it refuses to claim |
| `test_analysis_quality.py` | annotation judgments |
| `test_repertoire_and_kinds.py` | repertoire import, collection kinds, the lichess account, engine and sensor statistics |
| `test_chessbase.py` | ChessBase encodings, tags, filters and sorts |
| `test_collection_links.py` | games shelved in several collections, and the routes that manage them |
| `test_autoimport.py` | the lichess game watcher: settings, windows, failures and teardown |
| `test_openingtree.py` | the explorer: player perspective, filters, trends and weakest-line collapsing |
| `test_fetch_stockfish.py` | picking and unpacking the right engine build for each platform |

## The JavaScript rules engine

```powershell
powershell -File tests\run.ps1
```

Runs under Windows Script Host — no Node needed. Perft on the standard positions, SAN
round-trips, and a legality check of every stored opening, endgame and study.

## Browser regressions

These drive a real Edge through Playwright:

```powershell
.venv\Scripts\python -m pip install playwright
.venv\Scripts\python tests\workbench_browser.py
.venv\Scripts\python tests\sounds_browser.py
.venv\Scripts\python tests\autoimport_browser.py
.venv\Scripts\python tests\explorer_browser.py
.venv\Scripts\python tests\deploy_browser.py
.venv\Scripts\python tests\analysis_quality_browser.py
```

`workbench_browser.py` checks board rendering against the rules engine, navigation,
shapes, panel layout and persistence, the live engine and its telemetry grid, the
five-colour line palette, tablebase UI, annotation round-trips, import undo, filtered
deletion, and the two smoke pages.

`autoimport_browser.py` drives the auto-import card with lichess stubbed out: the card
appears only once an account is connected, settings persist without a save button, a
check really imports, a second check imports nothing, the run is undoable, and switching
off — or forgetting the token — stops the watcher.

`explorer_browser.py` indexes a small collection and drives the explorer: it opens on
the collection tree, the score follows the named player rather than White, clicking a
move walks the tree and the breadcrumb walks back, the filters narrow it, the trend is
per year, and the weakest list names the line that cost the points.

`deploy_browser.py` starts `deploy/serve.py` as its own process with the repository
kept off the path, so it fails if the download page ever grows a dependency on the
application. It checks that each platform is offered its own build, that the asset names
match what the release workflow produces, and that the folder stays small.

`sounds_browser.py` checks the sound catalogue against what is actually on disk, that
every file it claims is served as audio, that every event resolves to a real sample
through the fallback chain, and that the settings card offers the bundled sets without
asking for files.

## Smoke pages

With `py server.py` running:

- <http://localhost:8000/tests/workspace-smoke.html> — opens every module, plays a move,
  walks the context tabs, reports uncaught errors
- <http://localhost:8000/tests/smoke.html> — mounts every training level and pokes it
- <http://localhost:8000/tests/visual.html> — board renderer preview

Headless:

```powershell
msedge --headless=new --virtual-time-budget=30000 --dump-dom `
  http://localhost:8000/tests/workspace-smoke.html
```

## The built executable

```powershell
.venv\Scripts\python tests\check_bundle.py
```

Starts `dist/Caissa/Caissa.exe` against a temporary library, checks it comes up with an
empty library, and verifies the bundled assets match the sources byte for byte.

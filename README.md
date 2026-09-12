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

Your library lives in `%APPDATA%\Caissa\library` on Windows, for both source and
executable launches. It stays outside the software folder, so replacing or deleting
the application and downloading it again preserves your games and settings.
Override this location with `DATA_DIR`. On Linux/macOS the default is
`$XDG_DATA_HOME/Caissa/library` or `~/.local/share/Caissa/library`.

In the desktop app, open **Settings → Storage location → Browse folders…** to use
the native folder picker. Select an empty folder and click **Use selected folder**.
Close all Caissa windows and reopen: Caissa copies the whole library, including the
latest changes, to that folder before opening it. The original remains as a backup.
You can cancel the pending change in Settings before restarting. Failed copies keep
the original library active and display an error in Settings.

The selected path is remembered in `%APPDATA%\Caissa\storage.json` (the corresponding
Caissa app-data folder on other platforms), outside the application installation.
This small location file stays there so a fresh download can find your chosen folder.
Browser launches also honor this setting, but the native folder picker requires the
desktop app. An explicit `DATA_DIR` override takes precedence and disables relocation
through Settings. Reconnect an external drive before launching if it holds your library.

On the first source launch, an existing `./library` is copied to the new location
if that location does not exist; the original is retained. Close older copies of
Caissa before migrating. An explicit `DATA_DIR` always takes precedence.

Back up the **whole library folder while Caissa is closed**: PGN files, `library.db`,
study folders, and any SQLite sidecar files. The database contains annotations' current
file offsets, deletion state, repertoires, tags, import history, preferences, trainer
progress, and cached lookups. PGNs alone do not preserve all that information.
Browser storage is only a fallback for training progress; the local API saves it to disk.
The library path is returned by `/api/health` and printed by `desktop.py --smoke`.

## Building the .exe

```powershell
cd path\to\blindfold
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pip install pyinstaller
.venv\Scripts\python tools\fetch_stockfish.py
.\build.ps1
.\dist\Caissa\Caissa.exe
```

Output lands in `dist\Caissa\`. Stockfish and the web assets are bundled in.
Distribute or copy the **entire `dist\Caissa` directory**, including `_internal`;
the executable does not require Python on the target machine. The desktop window
requires Microsoft Edge WebView2. To make a downloadable archive:

```powershell
Compress-Archive -Path .\dist\Caissa -DestinationPath .\dist\Caissa-Windows.zip -Force
```

The build never bundles your personal library. Keep `DATA_DIR` outside the app folder
if you override it, for example `$env:DATA_DIR = 'D:\ChessLibrary'` before launching.

## Workbench controls

- Database previews show the last recorded mainline position, including the final
  position of full games. The preview stays beside the list while scrolling.
- **Filters** combine player, colour, outcome, opening/ECO range, event, result, rating
  range, move length, tags, date added, collection, and position. Colour and outcome are
  read from the player you name, so *Carlsen · Played White · Won* means exactly that. A
  rating floor asks that at least one player is above it; a ceiling asks that neither is.
  Opening names autocomplete from the games already in your library and fill in the ECO
  range they cover there, which then finds the same openings in PGNs that carry no opening
  name. **Clear all fields** empties the lot. The same picker drives **Master games**. **Delete matching games** previews the
  count and examples, then deletes exactly those unchanged entries after confirmation.
  Deleted entries leave their original PGN text on disk; collection exports omit them.
- Imports report progress in a corner of the window and keep running if you move to
  another view; when one finishes, the library counts and the open view refresh themselves.
- Pasted and loaded PGN needs a collection name — choosing a file fills it in from the file
  name. Online games go to their own collection (`lichess imports`, `chess.com imports`)
  rather than mixing into `My games`.
- **Study folders → Collections** can delete a collection, with the choice of whether its
  PGN files go with it. A collection you delete stays deleted; only an empty library is
  given a starter one.
- **Online & imports → Recent imports → Undo import** removes only games newly
  added by that batch. Existing duplicates survive. History persists across restarts;
  partially completed archive imports can also be undone. Imports made before this
  feature have no batch history: use collection/date filters for those.
- Index a collection from **Study folders** before searching its positions. Indexing
  now includes the entire game; re-index older collections to include their endgames.
- **Study folders → Delete** removes a folder and everything nested inside it. The
  collections filed there are only released, never deleted: their games and PGN files
  stay in the library. On disk Caissa takes back the `study.json` manifest it wrote and
  the directories it created; a directory holding files you put there yourself is left
  alone and reported in the confirmation.
- On the analysis board, scroll the wheel to step through moves. Drawing follows
  [chessground](https://github.com/lichess-org/chessground), the library lichess draws
  with, so the habits carry over: right-drag (or shift-drag) paints an arrow that follows
  the pointer as you go, releasing on the square you started from leaves a circle instead.
  Plain is green, Shift or Ctrl red, Alt blue, both yellow. Drawing the same arrow again
  removes it; drawing it in another colour recolours it. A plain click on the board clears
  every drawing, as does **Clear arrows**. Drawing works on view-only boards too.
- The analysis board opens in tabs. **＋** adds one, and opening a game from the database
  or from **Master games** puts it on its own tab rather than displacing your work. Each
  tab keeps its own game and its own panel arrangement.
- **Panels** chooses which of Notation, Stockfish, Game tags, Position context and Endgame
  tablebase a board shows. The arrows in a panel's head reorder it or send it across to the
  other column, the grip along its bottom edge sets its height, and the divider between the
  two columns sets their widths. Only one arrangement is remembered for new tabs: the tab
  you close last, or tab one if several are open when the app exits.
- Annotations are saved into the game as you type them; there is no Keep button. **Save
  game** still writes the PGN to disk.
- PGN comment commands are read rather than shown as noise. `{[%evp from,to,cp,cp,...]}`
  — lichess's engine evaluation for every ply of the main line — appears as a score beside
  each move instead of a wall of numbers in your notes, and a per-move `[%eval]` is used
  where it appears, variations included. A variation move sharing a ply with the main line
  gets no score of its own, because it is a different position. Commands are put back
  unchanged when the PGN is written out, and prose in the same comment is untouched.
- Numeric annotation glyphs are shown as symbols: `$1`–`$6` as `!` `?` `!!` `??` `!?` `?!`,
  and the standard positional set (`$10` `=`, `$14`–`$19` `⩲ ⩱ ± ∓ +− −+`, `$140` `∆`, and
  the rest) rather than raw `$n`.
- The position context panel has a **Facts** tab: background reading about the game from
  Wikipedia, grouped by what each article is actually about — the players, the event and
  place, and anything a search for both players turns up, which is offered as *possibly*
  about this game rather than asserted. Only pages the API returned are shown, and
  disambiguation pages are skipped. A game with no players or event recorded says so
  instead of guessing. Results are cached in your library, so a game you have looked up
  once reads offline; a failed or offline lookup is never cached as the answer.
- Each Stockfish line carries its depth as a chip and an **Add to tree** button that grafts
  the line into the notation as a variation — up to ten moves of it, or the whole line if
  it is shorter — and puts you on its first move so the arrow keys walk through it.
- Drag the board's lower-right corner to resize it. **Copy FEN**, **Reset board**, and
  **Board editor** are available directly in analysis. Editing starts a new study;
  save it to keep it. Blindfold controls belong to the trainer.
- **Analyze / Live analysis** runs continuous Stockfish search. Lines and depth update
  without replacing them with a thinking message. Toggle **Best move arrows** and
  **Color variations** separately. CPU is measured with 100% representing one core;
  memory is the engine process's resident memory, not its configured hash size.
- Engine lines keep a fixed colour by rank: first green, second blue, third red, fourth
  yellow. A line's rank badge, its evaluation and the arrow it draws all share that
  colour, and each arrow is numbered with its rank so the board and the panel line up.
- **Notation → One move per line** lays the game out one move number per row, White and
  Black side by side, with variations broken out between the rows. Switch it off for the
  running paragraph. The choice is saved with your other appearance settings.
- **Endgame tablebase** appears only once the position is down to seven pieces, which
  is as far as the lichess tables reach; above that the card stays out of the way.
  Toggle it to look a position up. The initial lookup needs internet; cached positions remain available offline. Results are from
  the side-to-move perspective, including each candidate move's result for that player.
  Cursed wins and blessed losses account for the 50-move rule. No large tablebase files
  are bundled. API semantics: [lichess tablebase](https://github.com/lichess-org/lila-tablebase#http-api).
- **Master games** searches the [PGN Mentor catalog](https://www.pgnmentor.com/files.html),
  imports the selected player collection, then applies local filters. For Fischer's
  King's Indian games, use Fischer and ECO E60–E99. This works even without opening
  names in the PGN; it does not search an un-downloaded game's moves remotely.
- **Settings → Appearance** covers dark mode, fourteen board palettes (four of them dark),
  nine piece sets and four piece treatments, orientation, coordinates and animation. The
  piece set and treatment pickers show real thumbnails of the artwork on a light/dark
  square pair, and the treatment previews follow whichever set you have chosen. All of it
  is stored with your library.
- **Settings → Storage location → Show in folder** opens the library folder in your file
  manager. It needs the desktop app; browser launches show the path but cannot open it.
- The database's opening column shows the ECO code beside the opening name from the PGN.
  When a game carries a code but no name, the code's volume is shown instead (A flank,
  B semi-open, C open and French, D closed and semi-closed, E Indian).

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
py -m unittest discover -s tests -p "test_*.py"    # backend regressions, no network
powershell -File tests\run.ps1                     # chess engine perft + SAN + data validity
```

The Python suite covers the library, every API route the workspace calls, the position index and
its transposition keys, study folders, literature links, and the Python rules engine on the five
standard perft positions.

For the workbench interaction regressions (requires installed Microsoft Edge):

```powershell
.venv\Scripts\python -m pip install playwright
.venv\Scripts\python tests\workbench_browser.py
```

This uses a temporary library and checks import undo, filtered deletion, board controls,
continuous Stockfish, tablebase UI, settings persistence, and both browser smoke suites.

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
- [lichess](https://lichess.org) — piece distribution, game export API, tablebase;
  board interactions informed by [Chessground](https://github.com/lichess-org/chessground)
- Piece sets are credited one by one in `assets/piece/CREDITS.md`, alongside the upstream
  `assets/piece/LICHESS-COPYING.md` and the bundled license texts.
  `py tools/fetch_pieces.py` refreshes them. Two carry conditions worth knowing before
  you redistribute this repository: **Alpha** (Eric Bentzen) is free for personal
  non-commercial use only, and **Maestro** (sadsnake1) is CC BY-NC-SA 4.0. Cburnett,
  Merida, Chessnut, Fantasy, Celtic, Spatial and Rhos are free software or public domain.
- Chess Tempo — tactics, used in-app through their own site, never copied
- Exercises: AdviceCabinet, *7 Levels of Blindfold Chess Exercises for Everyone*

<div align="center">

<img src="assets/caissa-128.png" alt="Caissa, muse of chess" width="128" height="128">

# Caissa

**A desktop chess workbench — a lighter ChessBase.**

[Documentation](https://h-bombmxpwr.github.io/caissa/) ·
[Getting started](https://h-bombmxpwr.github.io/caissa/guide/getting-started.html) ·
[HTTP API](https://h-bombmxpwr.github.io/caissa/reference/http-api.html) ·
[Scope](SCOPE.md)

</div>

---

It keeps a local database of games as ordinary
PGN files, analyzes them with a bundled Stockfish, builds and drills opening repertoires, pulls in
master games and your own online games, imports your lichess studies and your ChessBase exports,
links positions to free study material and chess history, and trains blindfold visualization.

Everything runs on your own machine. No account, no cloud library, no telemetry.

Start with [Running it](#running-it), [Your first study session](#your-first-study-session),
or [Building the .exe](#building-the-exe). The
[full documentation](https://h-bombmxpwr.github.io/caissa/) goes deeper than this file does.

See [SCOPE.md](SCOPE.md) for what the app is, what it is not, and where it is going.

## Running it

First time only — fetch the engine (about 80 MB, not stored in git):

```powershell
py tools\fetch_stockfish.py
```

Optional, and worth doing: the bundled move sounds and the alternative piece sets.

```powershell
py tools\fetch_sounds.py              # lichess sound sets
py tools\fetch_sounds.py --chesscom   # also the chess.com set, for this machine only
py tools\fetch_pieces.py              # SVG piece sets
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

## Your first study session

1. Open **Settings → Storage location** and choose where your chess library should live.
2. In **Online & imports**, select or paste a PGN and give its collection a name.
3. Open **Database**, select a game to preview its final recorded position, and double-click to analyze.
4. Use the mouse wheel or move buttons to review it. Add notes or variations and **Save game**.
5. Use **Study folders** to organize the collection, then **Index positions** to make its moves searchable.
6. Enable **Books** or **Opening book** from the analysis board's **Panels** menu when you want a reference beside the board.

## Find and organize games

The database table shows separate White and Black names and ratings, result, move count,
ECO/opening, tournament, date, round, annotator, annotation status and date added.
Scroll horizontally for the full table; its header stays visible while browsing.

**Filters** combines all selected conditions. You can narrow by either player, player color
and outcome, each side's rating range, tournament, site, round, annotator, termination,
played-date range, date added, source, collection, study category, annotations, opening/ECO,
result, game length, tags or an indexed position. Quick search matches each entered word
across player and game metadata. **Clear filters** starts over. Bulk deletion uses the same
filters and shows a count and preview before confirmation.

For example, choose Fischer, ECO E60–E99 and annotated games to find annotated King's Indian
games already in your library. To obtain games first, use **Master games**. Its surname field
suggests well-known players, names in your library and names from the cached PGN Mentor
catalog. This is a helpful starting list, not an exhaustive list of everyone in Lichess Masters.

Study folders have categories: **Games to study**, **Chess studies**, **Opening examples**,
**Model games**, **Endgames**, **Tactics**, and **Tournament preparation**. Change the category
on the folder card; it is saved in the library and its `study.json` manifest. Assign collections
to folders to find their games with the database's category filter.

Position indexing is available from **Database → Index positions**, **Study folders →
Collections & position indexing**, **Opening book**, and the analysis board's **Opening book**
panel. Analysis **Position context → Library / History** also offers indexing when needed.
The index covers the full recorded game. Check progress, then refresh the book or context view.

## Imported annotations and game facts

PGN comments before the first move, beside moves and after the final move are shown in
notation. Adjacent comments are combined instead of overwriting each other; semicolon
comments, annotation glyphs and variations are retained. Existing imports get searchable
annotator and annotation metadata from their original PGNs automatically.

A result such as `0-1` establishes who won, but does not establish resignation. Caissa shows
the result and the PGN's `Termination` tag when present, and preserves explicit comments such
as “White resigned.” It does not invent a resignation comment when the source contains none.

**Position context → Facts** includes local facts from the recorded main line: move count,
captures, castling, promotions, checkmate and annotator. Existing Wikipedia background links
provide further reading online and are cached for later use. Possible game matches are
labelled as such. Optional generated notes remain separately labelled; see the reference below.

## Books beside the board

Open **Books**, choose a PDF with the file picker, enter its title and optional author, and
select **Add PDF**. Files up to 128 MB are copied into your library's `books` directory.
Moving or replacing the original PDF afterward does not remove the library copy.

Select a book to read it in the app. The **Page → Go to page** control saves a page number
for that book; scrolling inside the PDF viewer does not update this bookmark automatically.
In analysis, use **Panels → Books** to show the reader beside your board. Resize or move the
panel with the existing panel controls. **Separate window** opens a dedicated reading window
that you can move to a second monitor (a separate browser window/tab in browser mode).
PDF viewing uses the browser/WebView2 PDF viewer; PDFs are not converted to playable games.

## Opening book

**Already installed:** Caissa includes an offline book built from the November 2025
Lichess Elite game archive: 2500+ versus 2300+ players, excluding bullet. It opens by
default under **Included book — Lichess Elite (offline)**. No account, download or
position-indexing step is needed. The included snapshot has **280,246 source games,
346,642 positions, and 450,114 continuations** in a 20 MB SQLite file. Counts appear
in the book panel and in [`data/opening-book.json`](data/opening-book.json).
This snapshot covers the first 48 plies (24 full moves) and keeps continuations played
in at least two games. For positions beyond its coverage, select an online reference
or your own indexed collections. It is separate from the over-the-board Masters database.
See [source and licensing details](data/OPENING-BOOK-CREDITS.md).

The **Opening book** module builds a reference from your own indexed PGN collections.
Its **Reference database** selector also provides deep online books from **Lichess Masters**
and **Lichess rated games**, through the [Lichess Opening Explorer API](https://github.com/lichess-org/lila-openingexplorer).
There is no fixed move-depth cutoff: follow continuations as far as the selected database
has games. Masters supports year ranges; rated games supports year-month ranges, rating
bands and time controls. Online results show their source and game count, with reference
game links. Positions are cached in your library for seven days; if refreshing an older
position fails, the saved results are shown with an explicit older-cache label. Unvisited
online positions require internet. This provides a broad reference without downloading
an entire remote database or limiting you to your two imported collections.

Choose a source collection, index it if necessary, and click a suggested move to explore.
Each move shows its frequency and White/draw/Black results, with matching games you can open.
**Back**, **Reset opening**, and **Analyze this position** let you move between exploration
and analysis. Enable **Panels → Opening book** on any analysis board to follow its position.

These are game statistics, not Stockfish scores or proof that a move wins. The module does
not import ChessBase CTG/CTB/CTO or Polyglot BIN books. Export games to PGN when available;
PDF books and the statistical opening book are separate kinds of reference.

## Build and practise a repertoire

1. Open a game or play a line in analysis. Select the last move you want to learn.
2. Choose **Add to repertoire**, name a repertoire or select one, and choose your playing color.
3. Open **Repertoire → Browse lines** to study, or **Drill due lines** to practise.
4. Enter your side's moves; the opponent's moves play automatically. Blindfold mode is optional.
5. Complete the line and select **Save review**. Successful reviews become less frequent;
   retries bring the line back tomorrow. Use **Export PGN** for a portable copy.

The same guide appears in the Repertoire module. Blindfold training remains a separate
seven-level module, and the Tactics module links to Chess Tempo for dedicated tactics practice.

### Importing a repertoire from a PGN

**Repertoire → Import repertoire PGN** (or the **Opening repertoire** card in Import games)
turns a lichess study export — or any PGN with variations — into drillable lines.

Every root-to-leaf path through a chapter becomes its own line, so alternatives written as
variations are drilled as alternatives. Each line is trimmed to end on a move by *your*
colour, because finishing a drill on the opponent's reply teaches nothing. A line that is
only the opening part of a longer line is dropped rather than drilled twice. Depth is
capped — twenty moves by default, up to as deep as the file goes — and a chapter that
cannot be replayed is skipped and counted instead of sinking the import. Importing into an
existing repertoire merges: existing lines keep their review history and only new lines are
added. The PGN itself is filed under an `openings` collection, searchable but out of the
game database.

## Your lichess account

**Settings → lichess account** connects a personal access token. It makes your own games
easier to import and your **private and unlisted studies** reachable at all — without a
token lichess will not admit an unlisted study exists.

The link on the card already requests the right scopes, `study:read` and `preference:read`,
both read-only. The token is verified with lichess before it is stored, so a mistyped or
expired one fails immediately. It lives in your local library's settings table, is sent to
lichess and nowhere else, and is never handed back to the page: the generic settings
endpoint refuses to read it and the account endpoint reports only the username and scopes.
A token revoked on lichess's side reads as disconnected, with the reason. **Forget this
token** removes it.

**Import my studies** lists every study lichess will show your token, newest first, with
checkboxes. Chapters are saved as `studies`-kind collections, and ticking **Also build
drillable repertoire lines** runs the same chapters through the repertoire importer in one
pass. A study that cannot be read is reported by name without stopping the others, and the
whole import is one undoable batch. See the
[lichess guide](https://h-bombmxpwr.github.io/caissa/guide/lichess.html).

## Online and offline use

**Settings → Connection** shows the device's connection status and updates when it changes.
**Check online services** checks reachability of PGN Mentor; a failed service check does not
necessarily mean the whole device is offline. Your stored games, PDFs, repertoire, position
index and bundled Stockfish work locally. New downloads, Wikipedia lookups and uncached
tablebase positions require internet. No online account is required for your local library.

## Detailed workbench reference

### Analysis navigation, notation and sounds

Right-click a notation move or a variation heading to delete that move and its
continuation, trim only following moves, or remove the whole enclosing variation.
The menu shows the number of moves affected, including nested branches. Other
branches stay intact; if your current position is removed, the board returns to
the surviving parent. Choose **Save changes** to persist the edit.

- Click the board or notation, then use **Left / Right** to step through moves,
  **Up / Down** to select sibling variations, and **Home / End** to reach the start
  or end of the current line. Typing fields retain their normal keyboard behavior.
- White and Black share a score-sheet row even when a move has a comment. Turn
  **One move per line** off for compact prose notation. Variations have labelled,
  collapsible branches; deeper branches start collapsed. **Expand variations** and
  **Collapse variations** control the whole tree. Select an alternative and use
  **Make main line** to promote it without losing the previous continuation.
- PGN `[%cal]` arrows and `[%csl]` circles appear on their position and as colored
  square/arrow labels beneath the move. Evaluations appear once as score badges.
  **Annotate game** updates evaluations while keeping prose and variations; it
  preserves existing annotation glyphs. Save the game to persist these changes.
- **Game tags** shows the PGN headers, including tournament and annotator, followed
  by your separate library labels. **Export PGN** opens native Save As in the desktop
  app and downloads a file in browser mode, including notes and variations.
- The **↔** panel control spans both columns beside the board. Toggle it again to
  return the panel to its original column. Full-width panels form a stack above the
  two smaller columns; arrangements are remembered per analysis tab.
- **Settings → Move sounds** offers the bundled lichess sets — standard, piano, sfx,
  futuristic, NES, lisp, robot, woodland — the synthesized Caissa wood/digital presets,
  or your own audio files. Twelve events have sounds: game start, your move, opponent
  move, capture, castling, check, promotion, game end, illegal move, notification, low
  time and pre-move. Each can be previewed and switched off individually. No set covers
  all twelve (lichess plays nothing for check in its standard set and ships no castling
  sample), so a missing sample is borrowed from another installed set rather than going
  silent, and the row says which. Run `py tools/fetch_sounds.py` to install the sets and
  `--chesscom` to add chess.com's on your own machine — those are proprietary and are
  never committed or shipped. **Animate moves and captures** and **Animation duration**
  control piece glides and capture fades. See the
  [sound guide](https://h-bombmxpwr.github.io/caissa/guide/sounds.html).

### Understanding folders and example games

**Study folders** displays a nested tree. Top-level folders contain indented
subfolders and collection entries, each showing its kind and count. Use the disclosure
arrows or **Expand all / Collapse all**. **Unfiled collections** are outside study
folders, at library level. Repertoires are a separate practice library. The collapsed
**All collections** section provides export, deletion and position-indexing tools.

In analysis, **Position context → Library** shows the number of candidate moves and
their game results, then example games reaching the current position. Filter examples
by player/tournament/annotator text, result, annotations and collection. These filters
search the whole position index, not just the initially displayed examples.

### Database and import management

- **The database lists games.** Every collection has a *kind* — `games`, `studies` or
  `openings` — and the **Content** dropdown defaults to Games, so saved study positions
  and imported opening trees stay out of the game list. They are filed, not hidden:
  choose **Study positions**, **Opening trees** or **Everything in the library** and
  they are listed with every filter still working, and the position index in analysis
  searches all three regardless. A collection's kind is fixed when it is created, so
  importing into an existing collection never moves somebody's games out of the
  database behind their back. **Save game** asks what you are saving and offers only
  the collections that can hold it.
- Database previews show the last recorded mainline position, including the final
  position of full games. The preview stays beside the list while scrolling.
- **Filters** combine player, colour, outcome, opening/ECO range, event, result, rating
  range, move length, tags, date added, collection, position, and the ChessBase tag
  block — team, player title, FIDE ID, event type, source publication, variation name
  and the tournament's own date. Colour and outcome are
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
- **ChessBase exports read correctly.** ChessBase writes PGN in the Windows code page,
  not UTF-8; read as UTF-8, `Réti` becomes `R<?>ti` and the letter is gone for good.
  Files are now decoded by sniffing — UTF-8 first, then Windows-1252, then Latin-1,
  applied to the whole file — on disk, inside archives, and through the browser's file
  picker alike. Its richer tag set is read and indexed too: `EventDate`, `EventType`,
  `WhiteTeam`/`BlackTeam`, `WhiteTitle`/`BlackTitle`, `WhiteFideId`/`BlackFideId`,
  `SourceTitle` and `Variation`. A library imported before those columns existed
  re-reads its own PGN once on the next launch, so nothing needs importing again.
  Names match whichever way the comma is spaced, so ChessBase's `Kasparov,Garry` and
  lichess's `Kasparov, Garry` find each other. What is still missing: native `.cbh`
  /`.cbv`/`.si4` files need an export step, and medals survive a round trip but are not
  filterable. See the
  [import guide](https://h-bombmxpwr.github.io/caissa/guide/importing.html#chessbase-exports).
- **Sorting** covers recently added, newest and oldest played, tournament date
  (`EventDate`, falling back to the game date), tournament name, tournament and round,
  highest rated, White, Black, result, ECO, opening, annotator, and longest games.
- **Study folders → Collections** can delete a collection, with the choice of whether its
  PGN files go with it. A collection you delete stays deleted; only an empty library is
  given a starter one.
- **Online & imports → Recent imports → Undo import** removes only games newly
  added by that batch. Existing duplicates survive. History persists across restarts;
  partially completed archive imports can also be undone. Imports made before this
  feature have no batch history: use collection/date filters for those.
- Index a collection from **Database → Index positions**, **Study folders**, or **Opening book** before searching its positions. Indexing
  now includes the entire game; re-index older collections to include their endgames.
- **Study folders → Delete** removes a folder and everything nested inside it. The
  collections filed there are only released, never deleted: their games and PGN files
  stay in the library. On disk Caissa takes back the `study.json` manifest it wrote and
  the directories it created; a directory holding files you put there yourself is left
  alone and reported in the confirmation.

### Board controls and analysis tabs

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
- **Panels** chooses which of Notation, Stockfish, Game tags, Position context, Endgame
  tablebase, Books and Opening book a board shows. The arrows in a panel's head reorder it or send it across to the
  other column, the grip along its bottom edge sets its height, and the divider between the
  two columns sets their widths. Only one arrangement is remembered for new tabs: the tab
  you close last, or tab one if several are open when the app exits.

### Notes, variations and position context

- Annotations are saved into the game as you type them; there is no Keep button. **Save
  game** still writes the PGN to disk.
- Arrows and circles belong to the move you drew them on. Step away and back and they
  return; the move list marks any move carrying a note or a drawing. They are written into
  the PGN as `[%cal]` and `[%csl]`, the same commands lichess uses, so they survive a round
  trip and open correctly elsewhere. **Clear arrows** clears that move's drawings.
- A game's opening name comes from the library index when the PGN file has no `[Opening]`
  tag of its own, so the analysis board and the database agree and the Study tab's teacher
  links work. Saving the game writes the tag into the PGN.
- **Library** and **History** read the position index. Until a collection is indexed they
  say so and offer to index the open game's collection there and then, rather than looking
  broken. **Game tags** lists the tags a game already has.
- PGN comment commands are read rather than shown as noise. `{[%evp from,to,cp,cp,...]}`
  — lichess's engine evaluation for every ply of the main line — appears as a score beside
  each move instead of a wall of numbers in your notes, and a per-move `[%eval]` is used
  where it appears, variations included. A variation move sharing a ply with the main line
  gets no score of its own, because it is a different position. Commands are put back
  unchanged when the PGN is written out, and prose in the same comment is untouched.
- Numeric annotation glyphs are shown as symbols: `$1`–`$6` as `!` `?` `!!` `??` `!?` `?!`,
  and the standard positional set (`$10` `=`, `$14`–`$19` `⩲ ⩱ ± ∓ +− −+`, `$140` `∆`, and
  the rest) rather than raw `$n`.
- **Optional AI note.** Copy `.env.example` to `.env` and set `GEMINI_API_KEY` to add a
  short, generated note about the game at the bottom of the Facts tab, below the sourced
  links. It is labelled as generated, because that is what it is: prose from a language
  model, not a source, and capable of being wrong. Everything else in the tab works
  without a key, and `.env` is gitignored and is not in `caissa.spec`'s bundle list, so no
  key is carried into a build. Dates, rounds and tournaments are *not* asked of the model
  — they are already in the PGN's own tags, where they are facts rather than recollection.
- The position context panel has a **Facts** tab: background reading about the game from
  Wikipedia, grouped by what each article is actually about — the players, the event and
  place, and anything a search for both players turns up, which is offered as *possibly*
  about this game rather than asserted. Only pages the API returned are shown, and
  disambiguation pages are skipped. A game with no players or event recorded says so
  instead of guessing. Results are cached in your library, so a game you have looked up
  once reads offline; a failed or offline lookup is never cached as the answer.

### Engine analysis and endgames

**Lines** runs from 1 to 5, and each line owns a colour that its arrow, its border and
its score all share — green, blue, red, yellow, purple. Five lines get five distinct
colours; none repeats another.

Below the controls, a telemetry grid reports what the search and the machine are doing:
engine name, search threads out of the logical cores available, physical core count,
hash size and how full it is, depth and seldepth, nodes and nodes per second, tablebase
hits, the engine process's own CPU and memory, whole-machine CPU and clock, memory in
use, CPU temperature and power draw.

Temperature and wattage usually read **not reported**, and that is honest rather than
broken: most Windows desktops publish no CPU thermal sensor at all, and a machine on
mains power reports no discharge rate. Nothing is estimated — a reading the machine will
not give is labelled missing. Run
[LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor) in
the background and real per-package temperature and watts appear within a few seconds;
laptops on battery report wattage without it. Sensors are polled on a background thread
and cached, so the readings never slow the search.

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

### Finding master games and appearance

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
- The database's opening column shows the ECO code beside the opening's name. A PGN that
  names its own opening is trusted; one carrying only a code is named from the moves it
  actually played, against lichess's CC0 opening data (`data/openings.eco.json`, rebuilt
  with `py tools/fetch_openings.py`). Matching on position rather than code means a game
  gets the specific line — *King's Indian Defense: Sämisch Variation*, not *E86* or
  *Indian defences* — and still lands correctly when it transposes. **Name openings** on
  the database page backfills games imported before this existed.

## Where things live

```
desktop.py            native-window entry point
server.py             HTTP server: static app + JSON API
backend/
  store.py            the library — PGN files on disk + SQLite index
  api.py              JSON API routes
  hardware.py         core counts, CPU temperature and power draw, where published
  repertoire.py       a PGN move tree walked into flat, drillable repertoire lines
  chess.py            chess rules in Python (0x88, perft-verified)
  study.py            position index, pins, study folders on disk
  books.py            PDF library metadata and file storage
  literature.py       free study material for a position
  importers.py        PGN / ZIP / GZ / BZ2 / ZST / EPD / CSV, folders, URLs, chess.com
  pgnutil.py          PGN splitting, tag parsing, move extraction
  engine.py           bundled Stockfish over UCI, plus batch annotation
  lichess.py          throttled lichess client, masters crawler, dump importer
js/
  library-tools.js    PDF reader, opening book and connection status
  workspace.js        the desktop workspace: database, analysis, repertoire, studies
  engine.js           chess rules in the browser (0x88, perft-verified)
  board.js            chessground-style board: transforms, drag, shapes, blindfold
  app.js              the blindfold trainer shell: levels, peek control, stats
  pgn.js              PGN reader with variations
  ai.js / stockfish.js  in-browser fallback engines
  drills/l1..l7.js    the seven blindfold levels
data/                 openings, endgames, studies, lectures.json
docs/                 the Sphinx documentation site (published to GitHub Pages)
tools/                fetch_stockfish.py, fetch_sounds.py, fetch_pieces.py, make_icon.py
assets/               the Caissa mark, the piece sets, the bundled sound sets
vendor/stockfish/     the bundled engine (fetched, gitignored)
library/              your games, studies and index (gitignored)
tests/                see below
```

## Tests

```powershell
py -m unittest discover -s tests -p "test_*.py"    # backend regressions, no network
py tools/build_exe.py                              # rebuild dist/Caissa/Caissa.exe
py tools/build_exe.py --clean                      # ...from scratch
powershell -File tests\run.ps1                     # chess engine perft + SAN + data validity
```

The Python suite covers the library, every API route the workspace calls, the position index and
its transposition keys, study folders, literature links, and the Python rules engine on the five
standard perft positions.

For the workbench interaction regressions (requires installed Microsoft Edge):

```powershell
.venv\Scripts\python -m pip install playwright
.venv\Scripts\python tests\workbench_browser.py
.venv\Scripts\python tests\sounds_browser.py
.venv\Scripts\python tests\analysis_quality_browser.py
```

This uses a temporary library and checks import undo, filtered deletion, board controls,
continuous Stockfish, tablebase UI, settings persistence, annotation round-trips, master
suggestions, PDF upload/range serving, opening-book navigation, and both browser smoke suites.

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

## Documentation

The prose guide, the HTTP API reference and the generated Python API live in `docs/` and
are published to <https://h-bombmxpwr.github.io/caissa/> by
`.github/workflows/docs.yml` on every push to `main`. Enable it once under
**Settings → Pages → Source: GitHub Actions**.

To build the site locally:

```powershell
.venv\Scripts\python -m pip install -r docs\requirements.txt
.venv\Scripts\python -m sphinx -b html -W --keep-going docs docs\_build\html
```

`-W` turns warnings into errors, which is what CI uses, so a broken cross-reference fails
the build rather than quietly shipping a dead link. The Python reference is generated from
the backend's own docstrings and cannot drift from the code.

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
- Opening names and lines: [lichess chess-openings](https://github.com/lichess-org/chess-openings),
  CC0 public domain.
- Piece sets are credited one by one in `assets/piece/CREDITS.md`, alongside the upstream
  `assets/piece/LICHESS-COPYING.md` and the bundled license texts.
  `py tools/fetch_pieces.py` refreshes them. Two carry conditions worth knowing before
  you redistribute this repository: **Alpha** (Eric Bentzen) is free for personal
  non-commercial use only, and **Maestro** (sadsnake1) is CC BY-NC-SA 4.0. Cburnett,
  Merida, Chessnut, Fantasy, Celtic, Spatial and Rhos are free software or public domain.
- Sound sets are credited in `assets/sound/CREDITS.md`, taken from lila's own
  `COPYING.md`: standard, robot and woodland by the lila authors and piano, sfx,
  futuristic and NES by Enigmahack are AGPLv3+; lisp by EdinburghCollective is
  CC BY-NC-SA 4.0. `py tools/fetch_sounds.py` fetches them.
  **chess.com's sounds are proprietary and are not redistributed here.**
  `--chesscom` downloads them to `assets/sound/chesscom/` for your own use;
  `.gitignore` and `caissa.spec` keep them out of the repository and out of any build.
- Chess Tempo — tactics, used in-app through their own site, never copied
- Exercises: AdviceCabinet, *7 Levels of Blindfold Chess Exercises for Everyone*

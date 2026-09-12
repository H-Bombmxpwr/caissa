# Building the executable

```powershell
py tools\build_exe.py
py tools\build_exe.py --clean     # from scratch
```

The result is `dist/Caissa/Caissa.exe` with an `_internal` folder beside it. The build
fetches whatever is missing first — the engine, the opening index, the offline opening
book — so a fresh clone builds in one command.

## What goes in

`caissa.spec` bundles `index.html`, `css/`, `js/`, `data/`, `assets/` and
`vendor/stockfish/`.

:::{warning}
`assets/sound/chesscom/` is stripped from the build. chess.com's audio is proprietary:
`tools/fetch_sounds.py --chesscom` puts it on your own machine for your own use, and
`.gitignore` plus the spec's filter keep it out of both the repository and any build you
hand to someone else.
:::

## Checking it

```powershell
.venv\Scripts\python tests\check_bundle.py
```

## Where the library goes

`%APPDATA%\Caissa\library`, the same path the source build uses. Replacing the
application does not touch it.

## Refreshing bundled assets

```powershell
py tools\fetch_stockfish.py        # the engine (~80 MB, gitignored)
py tools\fetch_pieces.py           # SVG piece sets, with their credits
py tools\fetch_sounds.py           # lichess sound sets
py tools\fetch_openings.py         # the ECO opening index
py tools\build_opening_book.py     # the offline opening book
py tools\make_icon.py              # the .ico from the .png
```

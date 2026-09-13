# Building the executable

```powershell
uv run python tools\build_exe.py
uv run python tools\build_exe.py --clean     # from scratch
uv run python tools\package_windows.py      # verified portable ZIP and SHA-256 checksum
```

The result is `dist/Caissa/Caissa.exe` with an `_internal` folder beside it. The build
fetches the engine and opening names if missing. The offline opening book is required;
if it is absent, build it with `tools/build_opening_book.py` first.

The packaging command creates `dist/Caissa-windows-x64.zip` and a `.zip.sha256`
checksum file. Extract the whole ZIP before launching; the executable needs its
accompanying folder. To put it on the download website, publish a GitHub Release
using the [release workflow](releasing.md).

## What goes in

`caissa.spec` bundles `index.html`, `css/`, `js/`, `data/`, `assets/` and
`vendor/stockfish/`.

> **Warning**
>
> `assets/sound/chesscom/` is stripped from the build. chess.com's audio is proprietary:
> `tools/fetch_sounds.py --chesscom` puts it on your own machine for your own use, and
> `.gitignore` plus the spec's filter keep it out of both the repository and any build you
> hand to someone else.

## Checking it

```powershell
uv run python tests\check_bundle.py
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

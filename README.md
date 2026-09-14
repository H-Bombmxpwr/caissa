<div align="center">

<img src="assets/caissa-128.png" alt="Caissa" width="112" height="112">

# Caissa

**A desktop chess workbench that studies your games and the player behind them.**

Your games, on your disk, as ordinary PGN. Analysed by a bundled Stockfish,
explored move by move, drilled as a repertoire, and studied blindfold.

Open **Player lab** for evidence-backed player reports, opponent preparation,
clock patterns, and scheduled practice from saved mistakes. See the
[Player lab guide](docs/guide/player-lab.md) for data requirements and limitations.

[![Documentation](https://img.shields.io/badge/Documentation-read%20the%20guide-315e48?style=for-the-badge)](https://h-bombmxpwr.github.io/caissa/)
[![Download](https://img.shields.io/badge/Download-Windows%20·%20macOS%20·%20Linux-2d6a4f?style=for-the-badge)](https://caissa.hxr.life/)

[![Licence](https://img.shields.io/badge/licence-GPLv3-blue)](#licence)
[![Docs build](https://github.com/H-Bombmxpwr/caissa/actions/workflows/docs.yml/badge.svg)](https://github.com/H-Bombmxpwr/caissa/actions/workflows/docs.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Works offline](https://img.shields.io/badge/works-offline-success)](https://h-bombmxpwr.github.io/caissa/guide/getting-started.html)

[Download](https://caissa.hxr.life/) ·
[Getting started](https://h-bombmxpwr.github.io/caissa/guide/getting-started.html) ·
[Importing](https://h-bombmxpwr.github.io/caissa/guide/importing.html) ·
[Opening explorer](https://h-bombmxpwr.github.io/caissa/guide/explorer.html) ·
[HTTP API](https://h-bombmxpwr.github.io/caissa/reference/http-api.html) ·
[Scope](SCOPE.md)

</div>

---

## What it is

Everything runs on your own machine. No account, no cloud library, no telemetry. The
network is used only when you ask for something that lives on it: a lichess import, an
endgame tablebase lookup, a Wikipedia summary.

|  |  |
| --- | --- |
| **A database you own** | Games are PGN text in folders you can read, copy and back up. SQLite is only an index over them — delete it and your games are still there. |
| **Analysis that explains itself** | Live Stockfish with up to five coloured lines, full search and machine telemetry, and one-click annotation of a whole game into your PGN. |
| **Openings, judged** | Walk a collection's tree and see how it went for whoever played it — scores from their side, trends by year, and the lines that cost the most points. |
| **Repertoires that drill** | A lichess study, or any PGN with variations, becomes spaced-repetition drills you play blindfold. |
| **Imports from anywhere** | PGN, ZIP/GZ/BZ2/ZST archives, folders, URLs, lichess (including private studies), chess.com, and ChessBase exports with their encoding and tags intact. |
| **Blindfold training** | The seven-level visualisation trainer, on the same board as everything else. |

## Install

Download it from **[caissa.hxr.life](https://caissa.hxr.life/)**, which offers the build
for the machine you are on; the files themselves are on
[Releases](https://github.com/H-Bombmxpwr/caissa/releases/latest) if you would rather
pick one by hand. Or run from source:

```bash
uv sync                                  # creates .venv from uv.lock
uv run python tools/fetch_stockfish.py   # the engine, ~80 MB, not stored in git
uv run desktop.py
```

Dependencies are managed with [uv](https://docs.astral.sh/uv/): `uv sync` builds the
environment from the committed `uv.lock`, and `uv run` uses it without activating
anything. Add `--no-dev` for just the two packages the application needs.

Optional extras: `uv run python tools/fetch_sounds.py` for the bundled move sounds, and
`uv run python tools/fetch_pieces.py` for the alternative piece sets.

Your library lives outside the application folder — `%APPDATA%\Caissa\library` on
Windows — so replacing or reinstalling the app never touches your games. Full
instructions, including the other ways to launch it, are in
**[Getting started](https://h-bombmxpwr.github.io/caissa/guide/getting-started.html)**.

## Documentation

The guide, the HTTP API reference and the generated Python API live at
**[h-bombmxpwr.github.io/caissa](https://h-bombmxpwr.github.io/caissa/)**, built from
[`docs/`](docs/) on every push.

| | |
| --- | --- |
| [Getting started](https://h-bombmxpwr.github.io/caissa/guide/getting-started.html) | install, run, where the library lives |
| [The game database](https://h-bombmxpwr.github.io/caissa/guide/database.html) | collections, search, sorting, deletion |
| [Importing games](https://h-bombmxpwr.github.io/caissa/guide/importing.html) | PGN, archives, online accounts, ChessBase |
| [The opening explorer](https://h-bombmxpwr.github.io/caissa/guide/explorer.html) | walking a collection's tree |
| [The analysis board](https://h-bombmxpwr.github.io/caissa/guide/analysis.html) | engine, telemetry, annotation, context |
| [Repertoires](https://h-bombmxpwr.github.io/caissa/guide/repertoire.html) | building lines and drilling them |
| [Your lichess account](https://h-bombmxpwr.github.io/caissa/guide/lichess.html) | studies, and games that import themselves |
| [Workbench reference](https://h-bombmxpwr.github.io/caissa/guide/reference.html) | every control, module by module |
| [Architecture](https://h-bombmxpwr.github.io/caissa/development/architecture.html) | how the pieces fit together |

## Contributing

```bash
uv run python -m unittest discover -s tests -p "test_*.py"   # backend, no network
powershell -File tests/run.ps1                                    # JS rules engine, perft
uv run python tests/workbench_browser.py                          # UI regressions, needs Edge
```

Every suite and what it covers is listed in
[Testing](https://h-bombmxpwr.github.io/caissa/development/testing.html). Build the
executable with `uv run python tools/build_exe.py` — see
[Building](https://h-bombmxpwr.github.io/caissa/development/building.html).

## Licence

Bundling Stockfish (GPLv3) and the cburnett piece set (GPLv2+) makes this application
**GPLv3**. Piece sets, sound sets and the services used are credited one by one in
[Licensing and credits](https://h-bombmxpwr.github.io/caissa/development/licensing.html).

Two things to know before redistributing: the **Alpha** piece set is free for personal
non-commercial use only, and **chess.com's sounds are proprietary** — they are never
committed or shipped, only fetched to your own machine on request.

<div align="center">
<sub>Built on <a href="https://github.com/official-stockfish/Stockfish">Stockfish</a> and the open work of <a href="https://lichess.org">lichess</a>.</sub>
</div>

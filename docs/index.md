# Caissa

<img src="_static/caissa.png" alt="Caissa, muse of chess" width="120" align="right">

A desktop chess workbench — a lighter ChessBase. It keeps your games as ordinary PGN
files on your own disk, analyses them with a bundled Stockfish, builds and drills
opening repertoires, imports from lichess, chess.com and ChessBase exports, and trains
blindfold visualisation.

Everything runs locally. There is no account, no cloud library, and no telemetry. The
network is used only when you ask for something that lives on it: a lichess import, an
endgame tablebase lookup, a Wikipedia summary.

**Start here:** [Getting started](guide/getting-started.md) ·
coming from ChessBase? [Importing games](guide/importing.md) ·
want your lichess studies? [Your lichess account](guide/lichess.md)

## What it does

| | |
| --- | --- |
| **A database you own** | Games live as PGN text in folders you can read, copy and back up. SQLite is only an index over them — delete it and your games are still there. |
| **Analysis that explains itself** | Live Stockfish with up to five coloured lines, full search and machine telemetry, and one-click annotation of a whole game into your PGN. |
| **Openings, judged** | Walk a collection's tree move by move and see how it went for whoever played it — scores from their side, trends by year, and the lines that cost the most points. |
| **Repertoires that drill** | Import a lichess study or any PGN with variations; every line becomes a spaced-repetition drill you play blindfold. |
| **Study material in place** | Position-indexed history, your own pinned notes, PDFs beside the board, and Wikipedia background for the game you are reading. |

## Guide

- [Getting started](guide/getting-started.md) — install, run, and where your library lives
- [The game database](guide/database.md) — collections, searching, sorting, deleting
- [Importing games](guide/importing.md) — PGN, archives, online accounts, ChessBase
- [The opening explorer](guide/explorer.md) — walking a collection's tree
- [The analysis board](guide/analysis.md) — engine, telemetry, annotation, context
- [Repertoires](guide/repertoire.md) — building lines and drilling them
- [Your lichess account](guide/lichess.md) — studies, and games that import themselves
- [Move sounds](guide/sounds.md) — the bundled sets and your own
- [Blindfold training](guide/blindfold.md) — the seven levels
- [Workbench reference](guide/reference.md) — every control, module by module

## Reference

- [HTTP API](reference/http-api.md) — every route the interface uses
- [Data model](reference/data-model.md) — the library on disk and in SQLite
- [Python modules](reference/python-api.md) — generated from the source

## Development

- [Architecture](development/architecture.md) — how the pieces fit together
- [Testing](development/testing.md) — the suites and what they cover
- [Building the executable](development/building.md)
- [Releasing](development/releasing.md) — the three platform builds, and how they are made
- [Licensing and credits](development/licensing.md)

```{toctree}
:hidden:
:caption: Guide

guide/getting-started
guide/database
guide/importing
guide/explorer
guide/analysis
guide/repertoire
guide/lichess
guide/sounds
guide/blindfold
guide/reference
```

```{toctree}
:hidden:
:caption: Reference

reference/http-api
reference/data-model
reference/python-api
```

```{toctree}
:hidden:
:caption: Development

development/architecture
development/testing
development/building
development/releasing
development/licensing
```

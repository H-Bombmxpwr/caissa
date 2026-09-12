---
hide-toc: false
---

# Caissa

```{image} _static/caissa.png
:alt: Caissa, muse of chess
:width: 140px
:align: right
```

A desktop chess workbench — a lighter ChessBase. It keeps your games as ordinary PGN
files on your own disk, analyses them with a bundled Stockfish, builds and drills
opening repertoires, imports from lichess, chess.com and ChessBase exports, and trains
blindfold visualisation.

Everything runs locally. There is no account, no cloud library, and no telemetry. The
network is used only when you ask for something that lives on it: a lichess import, an
endgame tablebase lookup, a Wikipedia summary.

:::{admonition} Start here
:class: tip

- New to the app? [Getting started](guide/getting-started.md)
- Coming from ChessBase? [Importing games](guide/importing.md#chessbase-exports)
- Want your lichess studies? [Your lichess account](guide/lichess.md)
:::

## What it does

::::{grid} 2
:::{grid-item-card} A database you own
Games live as PGN text in folders you can read, copy and back up. SQLite is only an
index over them — delete it and your games are still there.
:::
:::{grid-item-card} Analysis that explains itself
Live Stockfish with up to five coloured lines, full search and machine telemetry, and
one-click annotation of a whole game into your PGN.
:::
:::{grid-item-card} Your openings, judged
Walk a collection's tree move by move and see what happened when *you* played it —
scores from your side, trends by year, and the lines that cost the most points.
:::
:::{grid-item-card} Repertoires that drill
Import a lichess study or any PGN with variations; every line becomes a spaced-repetition
drill you play blindfold.
:::
:::{grid-item-card} Study material in place
Position-indexed history, your own pinned notes, PDFs beside the board, and Wikipedia
background for the game you are reading.
:::
::::

```{toctree}
:caption: Guide
:maxdepth: 2

guide/getting-started
guide/database
guide/importing
guide/explorer
guide/analysis
guide/repertoire
guide/lichess
guide/sounds
guide/blindfold
```

```{toctree}
:caption: Reference
:maxdepth: 2

reference/http-api
reference/data-model
reference/python-api
```

```{toctree}
:caption: Development
:maxdepth: 2

development/architecture
development/testing
development/building
development/licensing
```

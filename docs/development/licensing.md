# Licensing and credits

Bundling Stockfish (GPLv3) and the cburnett piece set (GPLv2+) makes this application
**GPLv3**.

## Bundled software

- [Stockfish](https://github.com/official-stockfish/Stockfish) — the engine, GPLv3.
- [lichess](https://lichess.org) — piece sets, sound sets, the game export API and the
  endgame tablebase. Board interaction is informed by
  [Chessground](https://github.com/lichess-org/chessground).
- Opening names and lines from
  [lichess chess-openings](https://github.com/lichess-org/chess-openings), CC0.

## Piece sets

Credited one by one in `assets/piece/CREDITS.md`, alongside the upstream
`assets/piece/LICHESS-COPYING.md` and the bundled licence texts. `py tools/fetch_pieces.py`
refreshes them.

Two carry conditions worth knowing before you redistribute this repository:

- **Alpha** (Eric Bentzen) — free for personal, non-commercial use only.
- **Maestro** (sadsnake1) — CC BY-NC-SA 4.0.

Cburnett, Merida, Chessnut, Fantasy, Celtic, Spatial and Rhos are free software or
public domain.

## Sound sets

Credited in `assets/sound/CREDITS.md`, taken from lila's own `COPYING.md`.

| Set | Author | Licence |
| --- | --- | --- |
| standard, robot, woodland | the lila authors | AGPLv3+ |
| piano, sfx, futuristic, nes | Enigmahack | AGPLv3+ |
| lisp | EdinburghCollective | CC BY-NC-SA 4.0 |

> **Take care**
>
> **chess.com's sounds are not redistributable.** They are proprietary, and nothing in this
> repository ships them. `tools/fetch_sounds.py --chesscom` downloads them to
> `assets/sound/chesscom/` on your own machine, where `.gitignore` and `caissa.spec` keep
> them out of the repository and out of any build. Use them for your own study; do not pass
> them on.

The **Caissa wood** and **Caissa digital** presets are synthesized in `js/sounds.js` and
are part of this project.

## Services used, not copied

- **Chess Tempo** — tactics, used through their own site in an embedded window.
- **Wikipedia** — summaries on the Facts tab, quoted with links to the source.
- **The Week in Chess** and **PGN Mentor** — freely published PGN collections, downloaded
  on request.

## Exercises

The blindfold curriculum follows AdviceCabinet's *7 Levels of Blindfold Chess Exercises
for Everyone*.

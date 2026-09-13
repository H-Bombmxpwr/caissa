# Sound credits

Every bundled sound set comes from lichess (lichess-org/lila, `public/sound`),
fetched by `tools/fetch_sounds.py`. The licence below is the one lila records
for that set; where lila lists no separate licence the set is covered by the
repository's own AGPLv3+.

| Set | Author | Licence |
| --- | --- | --- |
| `standard` — Lichess standard | the lila authors | AGPLv3+ |
| `piano` — Lichess piano | Enigmahack | AGPLv3+ |
| `sfx` — Lichess sfx | Enigmahack | AGPLv3+ |
| `futuristic` — Lichess futuristic | Enigmahack | AGPLv3+ |
| `nes` — Lichess NES | Enigmahack | AGPLv3+ |
| `lisp` — Lichess lisp | EdinburghCollective | CC BY-NC-SA 4.0 |
| `robot` — Lichess robot | the lila authors | AGPLv3+ |
| `woodland` — Lichess woodland | the lila authors | AGPLv3+ |

## chess.com

chess.com's sounds are proprietary and are **not** part of this repository.
`py tools/fetch_sounds.py --chesscom` downloads them to `assets/sound/chesscom/`
on your own machine, where `.gitignore` keeps them out of version control. Use
them for your own study; do not redistribute them.

## Caissa presets

The `wood` and `digital` sets are synthesized in `js/sounds.js` and are part of
this project. They need no download and are always available.

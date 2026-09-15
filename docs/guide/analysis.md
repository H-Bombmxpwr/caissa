# The analysis board

## Panels

The board is the fixed part; everything else is a panel you can move, resize, hide or
span across both columns. Drag a panel's grip to reorder it, drag its bottom edge to
resize it, and use **Panels** to choose which exist at all. Each board tab remembers its
own layout, and the layout is saved with your preferences.

Panels available: notation, engine, position notes, PGN tags, endgame tablebase, opening
book, position context, and the PDF reader.

## Moving around

| Key | Move |
| --- | --- |
| ← / → | back one move / forward down the main line |
| ↑ / ↓ | the previous / next sibling variation |
| Home / End | the start of the game / the end of this line |
| mouse wheel over the board | forward and back |

Playing a move that is not in the game creates a variation. Right-click a move for
deletion — the move and its continuation, the moves after it, or the whole variation.

## Live engine analysis

Tick **Live analysis** and Stockfish runs continuously on the current position, in its
own process so that annotating a game cannot stall it. **Lines** chooses how many
variations to search, from one to five.

### Line colours

Each line owns a colour, and its arrow, its border and its score all carry it: green,
blue, red, yellow, purple. Five lines get five distinct colours — no line repeats
another's, which is the whole point of numbering them on the board.

Turn the arrows off with **Best move arrows**. **Add to tree** writes a line into the
game as a real variation, up to ten moves of it.

### Popularity arrows

The **Opening book** panel draws arrows of its own, from whichever database it is
reading: **Popularity arrows** ranks the most played continuations 1 to 5, and **Show**
sets how many. They are dashed and thinner than the engine's, so the two can be on the
board at once without being confused for each other — one says what is played here, the
other says what the machine prefers. Hiding the panel clears them.

### The telemetry panel

Under the controls is a grid of what the search and the machine are actually doing:

| Reading | Meaning |
| --- | --- |
| **Engine** | the UCI engine answering, by its own `id name` |
| **Threads** | search threads out of the logical cores available |
| **Cores** | logical cores, and physical cores where the OS reports them |
| **Hash** | transposition table size, and how full the search has made it |
| **Depth** | full-width depth, and the deepest line searched (`seldepth`) |
| **Nodes** / **Speed** | positions examined, and per second |
| **Tablebase hits** | endgame probes that found an answer |
| **Engine CPU** | this process only — one fully busy core reads as 100% |
| **Engine memory** | resident memory held by the engine |
| **Machine CPU** | the whole machine, all cores averaged, with clock speed |
| **Memory in use** | whole machine |
| **CPU temperature** | from a sensor, if the machine publishes one |
| **Power draw** | watts, if anything on the machine reports them |

> **Temperature and wattage often read "not reported"**
>
> That is honest rather than broken. Most Windows desktops publish no CPU thermal sensor
> to the operating system at all, and a machine on mains power reports no discharge rate
> because it is not discharging. Nothing here is estimated: a reading the machine will not
> give is labelled missing rather than filled in with a plausible number.
>
> To get real values, run [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor)
> in the background. It publishes per-package temperature and watts over WMI, and both
> appear here within a few seconds. Laptops on battery report discharge wattage without it.

Sensors are read on a background thread and cached for a few seconds, so polling the
panel never blocks the search.

## Annotating a whole game

**Annotate game** walks the main line, scores every position, and writes the results
into the PGN:

- `[%eval …]` on each move, shown as a chip beside it in the notation
- `??`, `?` and `?!` glyphs where a move lost enough to earn one (300, 150 and 75
  centipawns respectively), and only where the move carries no glyph already

Nothing is written to disk until you choose **Save changes**.

## Endgame tablebase

Below seven pieces the tablebase card appears and, when enabled, reports the exact
result: win, loss, draw, and the distance to zeroing. Cursed wins and blessed losses are
labelled as such — they draw under the fifty-move rule. Answers are cached in your
library, so a position you have looked up once reads offline afterwards.

## Position context

Four tabs, each reading the position rather than the game:

- **Library** — the moves played from here in your indexed games, with results.
- **History** — the earliest dated game in your library that reached this position, and
  a decade histogram. It is a claim about your library, not about chess.
- **Study** — your own pinned notes and links for this exact position, plus opening
  references when the game names an opening.
- **Facts** — Wikipedia summaries for the players, the event and, where it is famous
  enough, the game. Every entry is a page that was actually found. An AI note may be
  appended and is labelled as such: it is not a source and can be wrong.

## Notes, glyphs and shapes

The comment box writes into the PGN as you type. Arrows and circles you draw on the
board are stored as `[%cal]` and `[%csl]` commands, the same ones lichess writes, so
they survive a round trip through any other PGN reader.


## Navigation and layout

The continuation strip beneath notation lists the main move and every alternative
from the current position. Use Up/Down to highlight a continuation and Right to enter
it; Left returns to the parent. When there is no branch ahead, Up/Down switches sibling
variations. Clicking a continuation enters it directly. Keyboard shortcuts leave text
fields and dialogs alone.

Panel arrows reorder full-width panels within the full-width row. Sending one to the
other column also returns it to half width. The Live analysis switch stays visibly on
while searching. **Engine & system usage** expands below the engine lines.

Position context separates Library continuations and examples, your Study notes,
History, and sourced Facts. History lists up to 100 games reaching the position,
oldest first, with direct links to separate analysis tabs and a decade timeline.
These dates describe your indexed library, not the first occurrence in chess history.

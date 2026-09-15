# Player lab

Player lab aggregates games into a scouting report. Enter the exact White or Black
name from the PGN (case does not matter). It can read games already in your library,
or fetch them from Lichess or Chess.com first. **Build report** does the whole job in
one run: fetch, index the new games so the opening explorer can read them, then build
the report. Imports go into a `Prep: handle` collection and use the normal import
history. Different handles are separate players; names are never matched by substring.

## What the two modes are for

Player lab replays one person's games and reports what keeps happening in them. Which
person that is, is the only difference between the two modes — the report is the same
either way, and every figure in it links to the games it came from.

**Opponent prep** is the obvious one, and it is what the lab opens on. Name someone you
are about to play. The report tells you what they open with as each colour, which lines
they score worst in, and where their clock runs low. Take a low-scoring line to the
analysis board and prepare against it.

**My prep** is the same report turned on yourself, and answers a different question:
*what do I keep getting wrong?* It shows the openings you actually play rather than the
ones you meant to, the lines you lose in, the moves that cost the most centipawns and the
time trouble around them. The part that only exists in this mode is the last step: any
mistake it finds can be saved as a **practice position**, which then comes back on a
schedule — 1, 3, 9, 27 and 30 days — until you play it right. That is the loop. The report
finds the leak; the practice positions close it.

## Start here

1. Name the player. **Opponent prep** wants their exact PGN name or online handle;
   **My prep** fills in your linked Lichess username by itself.
2. Choose where the games come from. **Games already in my library** uses what you
   have; the two online sources fetch first.
3. Set the fetch, if you are fetching. **Time control** narrows the fetch as well as the
   report. **How many games** defaults to 100 and takes any number; tick **Every game on
   the profile** for the whole account in that time control. Both dates are optional —
   leave them empty for the newest games, or fill either one to restrict the window.
4. **Build report**. Each stage reports what it did as it finishes.
5. Click any board to open that position on the analysis board, open an evidence game,
   or hand the collection to the opening explorer. In My prep, create practice from a
   saved mistake.

My prep fills your linked Lichess username from Settings. Online imports and
Lichess trainer fields use the same default. You can edit the name, especially
when local PGNs use your real name. Opponent and Chess.com fields do not inherit
your Lichess identity. Switching Player Lab modes keeps separate name drafts.
Scores always describe the selected player, including in opponent reports.

## Read a report

Choose a speed, date range, and minimum number of completed games. A first report
replays the matching games; subsequent reports reuse a local cache. Changing the
PGN, including its comments, invalidates that game's cache automatically.

The report shows score (wins plus half of draws), **what they open with**, low-scoring
lines to investigate, pawn-structure and material patterns, game phases, move quality
and clock pressure, and the mistakes behind them.

Openings are named from the moves actually played, using the lichess CC0 opening index,
and counted separately for each colour: the share is of that player's completed games
with that colour, and the score is theirs. A game whose PGN carries no `Opening` tag is
classified from its own first moves rather than left out of the count.

Every line, opening and mistake carries the board it happened on. Clicking a board opens
that position on the analysis board — a mistake opens its game at the move before the
mistake, with the move played drawn as an arrow. Evidence buttons name the game and its
date and open it.

**Open in the opening explorer** hands the explorer the collection just built and the
player's name, so the collection tree opens already reading their games.

A game contributes once per pattern even if the position recurs. Transposed opening
lines share a position key, with one representative move order displayed. Opening
snapshots are taken after the player's fourth, eighth, and twelfth turns in ordinary
games.

Small samples remain visible and are labelled. Conservative 95% Hoeffding bounds
describe uncertainty in the score under an independent-game assumption. Patterns
overlap; score differences are descriptive and do not establish cause. Opponent
strength, repeated opponents, selection bias, and changing skill can affect them.
An opening suggestion means the opponent previously scored poorly there; check
its soundness on the analysis board before using it. Print prep sheet opens the
browser/system print dialog.

## Evaluations and clocks

Move-quality statistics require adjacent saved numeric `[%eval]` comments. Lichess
exports carry both evaluations and clock times, so games fetched from Lichess arrive
ready to read. For any other source, use **Annotate game**, then **Save game**, on the
analysis board. Scores are normalized to the mover's perspective and reported as mean centipawn loss, not
an invented accuracy percentage. Mate evaluations and missing pairs are excluded.
The report includes coverage counts so unannotated games are not mistaken for
error-free games. Phase labels use simple material/move-number rules.

`[%clk H:MM:SS]` comments provide remaining time. Thinking time is measured from
consecutive clocks for the same player, plus the increment. Only simple base or
base+increment controls are supported for thinking time; staged controls, missing
clocks, and negative elapsed times are not filled in. The initial clock is used
only for a standard starting position. Low time means under 30 seconds *after*
the move, not necessarily when the decision began.

## Practice and retests

A saved move losing at least 150 centipawns can become a practice position.
**Create practice position** asks the local Stockfish for a best move and stores
the source game, position, phase theme, PGN fingerprint, and answer in SQLite.
This is a single-best-move exercise; another sound move may not match its answer.
The report keeps up to 100 mistakes and shows the eight costliest, each with its board
and a practice button.

Enter SAN or coordinates in a due exercise. The server checks the move and
schedules a retest: 1, 3, 9, 27, then 30 days after consecutive successes; a
miss returns tomorrow. Illegal input does not consume an attempt. Reloading the
page preserves progress and does not make a future exercise due. Deleting the
source game deletes its exercises. Editing the source preserves older exercises
as historical positions; newly created exercises use the edited PGN fingerprint.
Success counts measure practice only, and never label a weakness “fixed.”

## Visualization rating

Blindfold training now shows a persistent experimental visualization practice
rating. It starts at 1000, uses fixed level difficulty and a 24-point update
factor, and changes with recorded exercise outcomes. It is not calibrated against
players, does not equate the seven exercise types, and is not a chess rating.

## Keyboard and speech

Focus a board with Tab. Arrow keys explore squares in the displayed orientation;
Enter selects a movable piece or a legal destination; Escape clears selection.
**Read position** announces the side to move and occupied squares. Enable
**Speak** for optional system speech; the same information is available in the
screen-reader status region. Hidden pieces stay hidden until Peek reveals them.
Analysis also accepts typed SAN moves, with keyboard-accessible promotion choices.
Move-list buttons include move number and side in their accessible names.

These controls have browser interaction tests, but are not a claim of complete
screen-reader compatibility or an accessibility audit with blind players.

## Further work

The current implementation prioritizes local evidence and reviewable practice.
It does not implement Maia/lc0 model inference, population conversion benchmarks,
book-departure detection, validated tactical-motif tagging, calibrated
visualization ratings, or longitudinal proof that a weakness improved in games.
Those require additional models, reference data, or validation rather than labels
inferred from centipawn thresholds.

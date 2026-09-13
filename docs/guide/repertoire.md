# Repertoires

A repertoire is a set of lines you intend to play, each rehearsed until you can recall it
without the board.

## Building one from the board

Play or open the line, select its last move, and choose **Add to repertoire**. Pick an
existing repertoire or name a new one, and say which colour you play. The line is stored
as SAN from the position it began in.

## Importing a lichess study

Export the study from lichess (**Study menu → Download all chapters**) and use
**Repertoire → Import repertoire PGN**, or the **Opening repertoire** card in Import
games. It also accepts any other PGN with variations.

What the importer does with the tree:

- Every root-to-leaf path through a chapter becomes its own line, so the alternatives
  written as variations are drilled as alternatives.
- Each line is trimmed to end on a move by *your* colour. Finishing a drill on the
  opponent's reply teaches nothing.
- A line that is only the opening part of a longer line is dropped, because drilling it
  would be drilling the same moves twice.
- Depth is capped — twenty moves by default, up to "as deep as the file goes".
- A chapter whose movetext cannot be replayed is skipped and counted, rather than sinking
  the whole import.

Importing into an existing repertoire merges: lines already present keep their review
history, and only genuinely new lines are added.

The PGN itself is filed under an `openings` collection, so it stays searchable without
padding out the game database. Untick **Also keep the PGN in your library** if you only
want the lines.

Private lichess studies work the same way once your account is connected — see
[Your lichess account](lichess.md).

## Drilling

**Drill due lines** plays the opponent's moves for you and asks for yours, blindfold by
default, with a **Peek** button that counts how often you use it. When the line is done,
**Save review** schedules it: a clean run moves the line further away, a retry brings it
back tomorrow.

**Browse lines** lists everything in the repertoire, with the option to study a line on
the analysis board instead of drilling it.

**Export PGN** writes the whole repertoire out as one PGN, one game per line, each with
its starting FEN. It is a plain file; nothing about it is specific to this app.


## View the whole repertoire

Choose **View repertoire** to merge all saved lines with the same starting FEN into
one analysis tree. Shared moves appear once, and different replies become branches.
Different starting positions open separate tabs because they cannot share one legal
root. The merged view is an unsaved study: save it as PGN if you want it in the game
library. Editing it does not rewrite the original drill lines.

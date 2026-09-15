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

**Drill due lines** opens a full-size board and practises everything that is due;
**Drill all lines** practises the whole repertoire whether or not it is due. You play the
repertoire's colour, the board is oriented to it, and the opponent's moves are played for
you. Move by dragging a piece or by clicking its square and then its destination — there
is nothing to type. Promotions ask which piece you want. **Board size** resizes the board,
and **Moves played** lists only the moves you have actually reached, so it never shows you
the move you are being asked for.

Under the prompt, the drill names the opening you have reached — *B90 · Sicilian Defense:
Najdorf Variation* — from lichess's CC0 opening data, the same naming the game database
uses. It names the position you are standing in, not the one the line ends in, so it
follows you into the variation without telling you where the line is going. On a line that
leaves the named openings behind, or one starting from a set-up position that never joins
them, it simply shows nothing.

**Hint** works in two presses. The first marks the piece that moves, in blue; the second
marks the square it moves to, in amber. Stopping after the first press is the point — it
is usually all you need, and it leaves you to work out the rest. A hinted line counts as a
retry when the review is saved, so it comes back tomorrow, and the hint clears itself once
you play the move.

Blindfold mode is off by default. Tick it to hide the pieces as a memory exercise; a
**Peek** button then appears and counts how often you use it. A peek shows the position
but never the hint, so the two do not do each other's work.

A session that holds several lines drills them as one tree. Playing a saved move belonging
to a different line switches you onto that line rather than marking you wrong, and when a
line finishes the board jumps back to the last position the remaining lines still share,
so shared opening moves are not replayed. The counter under the board tracks how many of
the session's lines you have completed.

**Save review** schedules every line you completed in the session: a clean run moves a
line further away, a retry brings it back tomorrow. You do not have to finish the whole
session first — save whenever at least one line is done. Closing with completed lines
still unsaved asks for confirmation.

**Browse lines** lists everything in the repertoire, with the option to study a line on
the analysis board instead of drilling it, or to drill that single line.

## Renaming, changing side and removing lines

**Rename** on a repertoire card edits its name, and **Change side** edits the colour you
play — the same dialog, reached from either button, so either field can be changed from
either one. Changing the side flips the drill board and switches which moves are asked of
you.

To remove lines, choose **Browse lines**, tick the lines to delete, and use **Delete
selected lines**; the button carries the count. The remaining lines keep their review
history, and the imported source PGNs are untouched. Closing the dialog without deleting
changes nothing, and an emptied repertoire can be refilled from analysis or a PGN import.

**Export PGN** writes the whole repertoire out as one PGN, one game per line, each with
its starting FEN. It is a plain file; nothing about it is specific to this app.


## View the whole repertoire

Choose **View repertoire** to merge all saved lines with the same starting FEN into
one analysis tree. Shared moves appear once, and different replies become branches.
Different starting positions open separate tabs because they cannot share one legal
root. The merged view is an unsaved study: save it as PGN if you want it in the game
library. Editing it does not rewrite the original drill lines.

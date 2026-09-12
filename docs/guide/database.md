# The game database

## Collections, and what they hold

Every game belongs to exactly one collection, and every collection has a **kind**:

| Kind | Holds | Shown in the database by default |
| --- | --- | --- |
| `games` | games that were played | yes |
| `studies` | saved study positions and analysis | no |
| `openings` | imported opening trees and repertoire PGNs | no |

This is the answer to a problem that grows quietly: a database that mixes twelve
thousand played games with two hundred saved positions and a repertoire tree is no
longer a database of games. So the **Content** dropdown at the top of the database
defaults to **Games**, and the other two kinds stay out of the way.

They are not hidden, only filed. Choose **Study positions**, **Opening trees** or
**Everything in the library** from that dropdown and they are listed like anything else,
with every filter still working. The position index in the analysis board searches all
three regardless of the dropdown, so a position you saved in a study is still found when
you reach it on the board.

A collection's kind is set when it is created and never changes afterwards. Importing
into an existing collection cannot move somebody's games out of the database behind
their back.

## Searching

The search box matches players, event, opening, ECO, annotator, site, team, source
publication and variation name. Every word you type must match somewhere, so
`karpov najdorf` finds Karpov's Najdorfs rather than everything by either name.

**Filters** opens the full form. Every field narrows the same search, and they combine:

- **Player**, with colour and outcome read from the player you name. "Fischer, as
  White, who won" is three fields, not a special search.
- **Opening**, which fills in the ECO range that opening covers *in your own library* —
  so it finds the same openings in PGNs that carry no opening name at all.
- **ECO from / through**, rating bounds for either or each player, dates played, dates
  added, game length in plies, tags, annotation status, and import source.
- **Position FEN**, which searches the position index rather than the tags.
- The ChessBase tag block: team, player title, FIDE ID, event type, source publication,
  variation name, and the tournament's own date.

### Player names

ChessBase writes `Kasparov,Garry`; lichess writes `Kasparov, Garry`. Both spellings are
searched whichever way you type it, so you do not have to know which program produced
the file you are searching.

## Sorting

| Sort | Order |
| --- | --- |
| Recently added | newest import first |
| Newest / oldest played | by the game's own date |
| Tournament date | by `EventDate`, falling back to the game date |
| Tournament name / Tournament and round | event, then round order |
| Highest rated | by the stronger of the two ratings |
| White player / Black player / Result / ECO / Opening / Annotator | alphabetical |
| Longest games | by ply count |

## Deleting games

**Delete matching games** removes everything the current filters match. It always shows
a preview first: how many games, a sample of them, and the exact filter set in force.
Confirming deletes only rows whose identity still matches what the preview saw, so a
concurrent import cannot widen the deletion.

The index rows go; the PGN text on disk stays. Deleting a collection is the operation
that offers to remove files.

## Undoing an import

Every import is a batch. **Import games → Recent imports** lists them with the count each
added, and **Undo import** removes exactly those games — not duplicates that were
already in your library, and not games another import added to the same collection.

## Indexing positions

Searching by position needs an index, and building one walks every game in a collection
and records each position in it. Start it from **Study folders**, from the database's
**Index positions** button, or from the prompt the analysis board shows when a
position-based tab has nothing to read.

Indexing is per collection, and you only need to redo it when that collection changes.
Positions are stored under a transposition key, so a position reached by a different
move order is still the same position.

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

## One game, several collections

A game belongs to the collection it was imported into, and can be listed by others as
well. Importing a game the library already holds used to count it as a duplicate and drop
it, which quietly lost the fact that it belonged in both places. Now it is **linked**
instead: the same single row of PGN, shelved twice.

Wherever a game is shown, so are its collections. The database has a **Collections**
column — a game on more than one shelf shows the first name and a `+n`, with the full
list on hover — and the preview panel and the analysis board's **Game tags** panel both
list them.

**Collections…** on the preview, or **Add to another collection** in analysis, opens the
dialog that manages them. Adding links the game; unlinking removes it from that shelf.
The collection a game was imported into is its owner and cannot be unlinked — that is a
move, not a link.

> **Deleting a collection cannot destroy a shared game**
>
> If you delete a collection that owns a game another collection also holds, the game is
> handed to that other collection rather than deleted with the rest. Only games nothing
> else holds go.

An import now reports `linked` alongside `added`, `duplicates` and `skipped`, so
"0 added, 14 linked" tells you the games were already there and are now on this shelf too.

## Renaming a collection

**Study folders → All collections →** the row's ⋯ **→ Rename.** A collection's name is also the name of the
folder its PGN lives in, so renaming moves that folder and rewrites the games' stored
paths together — the games stay readable, and their study folder manifest is rewritten to
match. Nothing else changes: links, position indexes and review history all survive.

A name another collection already uses is refused rather than merging the two. If the
destination folder somehow already exists on disk, the files are left where they are; the
games still read correctly from the old folder and only new imports land under the new
name.

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

**Delete matching games**, in the ⋯ beside the filters, removes everything the current
filters match. It always shows
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

Indexing uses the same bottom-right progress card as imports. You can close the
collection chooser or switch tabs while it runs. Progress is no longer shown
as running text inside Study folders.

The initial status counts games needing an index. Once that total is available,
the card shows processed games and a percentage. Already indexed games are not
included in the remaining work. Completion reports any games that could not be
indexed; if no work remains, it says all games are already indexed. An import
and indexing job can each have a card at the same time.

Searching by position needs an index, and building one walks every game in a collection
and records each position in it. Start it from **Study folders**, from the database's
**Index positions** button, or from the prompt the analysis board shows when a
position-based tab has nothing to read.

Indexing is per collection, and you only need to redo it when that collection changes.
Positions are stored under a transposition key, so a position reached by a different
move order is still the same position.


## What position indexing does

Importing makes game headers and PGN searchable. **Index positions** does a separate
job: it reads each game's PGN, starts at its FEN (or the normal starting position),
and legally replays its main line. It records the starting position, every position
after a move, its game and ply, and the next SAN move in SQLite. The position key
uses piece placement, side to move, castling rights and legal en-passant availability;
move counters do not distinguish positions. This connects transpositions.

This powers exact-position search, local opening continuations and result counts,
example games, and the dated History view. It does **not** run Stockfish, evaluate
moves, download games, annotate your PGNs, or index PGN side variations. Repertoire
variation trees are a separate feature.

Indexing includes games owned by or linked into the chosen collection. Already indexed
games are skipped; saving an edited game invalidates its position rows, so the next
run picks it up again. Writes are committed in batches of 25 games. Completed
batches remain available if the app closes; start indexing again to finish.

The first run can take time because every move is parsed and checked for legality.
Long games take longer than short ones. Progress counts games processed in this run,
including errors, rather than moves or seconds remaining. An invalid main line is
reported as an error and is not partially indexed. Original PGNs remain unchanged.

In **Study folders**, collections show **Indexed**, **Partially indexed**, or
**Not indexed**, with an indexed/total count and a distinct border. Importing new
games or editing existing ones can turn a complete collection into a partial one.
Use the collection's Index positions action to catch up.

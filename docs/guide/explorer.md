# The opening explorer

A reference database answers *what is played here*. The explorer answers a different and
often more useful question about a collection you hold: **when this player played it,
what happened to them.**

That player may be you. It may just as easily be Fischer, or whoever a collection was
imported for — a database of one strong player's games read this way shows their
repertoire, what it scored, and where it let them down.

It opens on the **Collection tree**. Pick a collection, name a player, and walk the tree
move by move. Every number is from that player's side of the board, so a 38% score is 38%
for them, not for White. Leave the player box empty and the report reads from White's
side, like a conventional database.

## Walking the tree

Click a move in the list, or play one on the board, and the report follows. The line
currently on the board is written above it as a breadcrumb — click any move in it to jump
back to that point. **Back a move** and **Start again** do the obvious things, **Flip
board** turns it round (useful when the player under study was Black, and remembered
between visits), **Analyze this position** opens it on the analysis board, and **Open
these games** lists the games that reached it in the database.

There is no depth limit. The position index already holds every position of every game,
so twenty moves deep costs the same as one, and transpositions collapse for free because
positions are stored under a transposition key.

> **It reads the position index**
>
> A collection has nothing to say here until it has been indexed. Index it from the panel
> at the bottom of the explorer, from **Study folders**, or from the database's **Index
> positions** button. Re-index a collection after adding games to it.

## What each move shows

| Column | Meaning |
| --- | --- |
| The move | click to play it and go deeper |
| Volume bar | how many games, and what share of this position they were |
| Win/draw/loss bar | green, grey, red — from the named player's side |
| Score | that player's percentage after this move |
| Beneath it | average opponent rating, and the year it was last played |

Moves are ordered by how often they were played, not by how well they did.

## Filters

Every filter narrows the whole report — the moves, the trend and the weakest lines all
describe the same set of games.

- **Collection** — one collection, or every indexed one.
- **Player** — the name as it appears in the games; the box suggests the names that
  actually occur in the chosen collection.
- **Colour** — that player's games as White, as Black, or both.
- **Time control** — bullet, blitz, rapid, classical, correspondence, or a combination.
  Derived at import from the PGN's `TimeControl` tag.
- **Rated** — rated or casual, where the file says so.
- **From / Until** — a year, a month (`2023-06`) or a day.
- **Opponent rating** — the *opponent's* rating, not the named player's, so "how did they
  do against stronger opposition" is one filter.

## Trends

**Score by year from this position** turns the same games into a bar per year. A line that
used to work and stopped shows up here before it shows up anywhere else. The bar height is
the score out of 100; the game count is on hover.

## Where the points go

The weakest-line scan looks across the whole tree rather than one position, and ranks by
**points dropped** — games multiplied by the shortfall against an even score. Ranking by
score alone would surface a line played twice and lost; ranking by volume would just list
the main line. Points dropped surfaces the line that actually cost something.

Two kinds of entry are left out, because they say nothing of their own:

- **Pass-through nodes.** Every position along a line that lost seven games reports the
  same seven games. Only the deepest is kept, because it names the line rather than
  gesturing at it.
- **Pure aggregates.** "1.e4 cost 3.5 points" is only its children added together. A node
  is dropped when the lines kept beneath it account for all its games; if some of its
  games are not explained further down, it stays.

Set the minimum game count to taste — below three, single bad days dominate. Click any
line to put it on the board.

## Reference databases

The second tab is the conventional explorer: the bundled offline book, the indexed
collections read from White's side, and the lichess Masters and rated-games databases
online.

## How large is too large

The report aggregates in the database rather than in the application, so it stays quick on
collections far larger than one person's games. On a 20,000-game collection with 87,000
indexed positions, the opening position answers in about 45 ms and the full weakest-line
scan in about half a second.

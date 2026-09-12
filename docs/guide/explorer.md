# The opening explorer

A reference database answers *what do strong players play here*. The explorer answers a
more useful question about your own games: **when you played this, what happened to you.**

It opens on the **Collection tree**. Pick a collection, name yourself, and walk the tree
move by move: every number is from your side of the board, so a 38% score is 38% for you,
not for White.

## Walking the tree

Click a move in the list, or play one on the board, and the report follows. The line
you are on is written above the board as a breadcrumb — click any move in it to jump back
to that point. **Back a move** and **Start again** do the obvious things, **Analyze this
position** opens it on the analysis board, and **Open these games** shows the games that
reached it in the database.

There is no depth limit. The position index already holds every position of every game,
so twenty moves deep costs the same as one.

:::{admonition} It reads the position index
:class: important

A collection has nothing to say here until it has been indexed. Index it from the panel
at the bottom of the explorer, from **Study folders**, or from the database's **Index
positions** button. Re-index a collection after adding games to it.
:::

## What each move tells you

| Column | Meaning |
| --- | --- |
| The move | click to play it and go deeper |
| Volume bar | how many games, and what share of this position they were |
| Win/draw/loss bar | green, grey, red — from your side |
| Score | your percentage from that move |
| Beneath it | average opponent rating, and the year you last played it |

Moves are ordered by how often you played them, not by how well they did.

## Filters

Every filter narrows the whole report — the moves, the trend and the weakest lines all
describe the same set of games.

- **Collection** — one collection, or every indexed one.
- **Player** — the name as it appears in the games; the box suggests the names that
  actually occur. Leave it empty and the report reads from White's side, like a
  conventional database.
- **Colour** — your games as White, as Black, or both.
- **Time control** — bullet, blitz, rapid, classical, correspondence, or a combination.
  Read from the PGN's `TimeControl` tag.
- **Rated** — rated or casual, where the file says.
- **From / Until** — a year, a month (`2023-06`) or a day.
- **Opponent rating** — the *opponent's* rating, not yours, so "how do I do against
  stronger players" is one filter.

## Trends

**Score by year from this position** turns the same games into a bar per year. A line
that used to work and stopped shows up here before it shows up anywhere else. The bar
height is your score out of 100; the game count is on hover.

## Where the points go

The weakest-line scan looks across the whole tree rather than one position, and ranks by
**points dropped** — games multiplied by the shortfall against an even score. Ranking by
score alone would surface a line you played twice and lost; ranking by volume would just
list your main line. Points dropped surfaces the line that actually cost you.

Two kinds of entry are left out, because they say nothing of their own:

- **Pass-through nodes.** Every position along a line that lost seven games reports the
  same seven games. Only the deepest is kept, because it names the line rather than
  gesturing at it.
- **Pure aggregates.** "1.e4 cost you 3.5 points" is only its children added together. A
  node is dropped when the lines kept beneath it account for all its games; if some of
  its games are not explained further down, it stays.

Set the minimum game count to taste — below three, single bad days dominate. Click any
line to put it on the board.

## Reference databases

The second tab is the conventional explorer: the bundled offline book, your own indexed
games from White's side, and the lichess Masters and rated-games databases online. See
[the opening book](../guide/getting-started.md) for what each one covers.

## How large is too large

The report aggregates in the database rather than in the app, so it stays quick on
collections far larger than one person's games. On a 20,000-game collection with 87,000
indexed positions, the opening position answers in about 45 ms and the full weakest-line
scan in about half a second.

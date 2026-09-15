# Data model

## The shape of a library

```
library/
  library.db            SQLite index
  collections/
    my-games/games.pgn  the actual games, appended in import order
    opening-trees/games.pgn
  reference/
    GigaBase.pgn        a base read where it lies, never copied in
  studies/
    prep/study.json     a manifest naming the collections in this folder
  books/                PDFs, by id
```

The PGN files are the library. `library.db` records, for each game, the file it is in
and the byte range it occupies — so reading a game is a seek and a read, and losing the
index costs you search rather than games.

That indirection is also what lets a multi-gigabyte base be *attached* rather than
imported: its rows carry a path into `reference/` instead of into a collection folder,
and `games.source` is `reference`. See [A reference base](../guide/reference-base.md).

## Tables

### `collections`

`id`, `name` (unique), `kind`, `created_at`.

`kind` is `games`, `studies` or `openings`, decided when the collection is created and
fixed thereafter. See [The game database](../guide/database.md#collections-and-what-they-hold).

### `games`

The index row for one game. Beyond the location fields (`path`, `byte_offset`,
`byte_length`, `signature`):

| Columns | From |
| --- | --- |
| `white`, `black`, `white_elo`, `black_elo`, `result`, `date`, `event`, `site`, `round`, `eco`, `opening`, `variant`, `time_control`, `fen`, `ply_count` | the standard PGN seven-tag roster and its usual companions |
| `annotator`, `termination`, `has_annotations` | annotation provenance; `has_annotations` is derived from the movetext |
| `event_date`, `event_type`, `white_team`, `black_team`, `white_title`, `black_title`, `white_fide_id`, `black_fide_id`, `source_title`, `variation` | ChessBase's richer tag set — see [Importing games](../guide/importing.md#the-tags-chessbase-writes) |
| `speed`, `rated` | derived at import from `TimeControl` and the event name, so the [explorer](../guide/explorer.md) can filter by them |
| `first_moves` | the opening moves, for naming openings without replaying the game |
| `source`, `source_id`, `added_at` | where it came from and when |

`source_id` is unique where present (`lichess:<id>`, `chesscom:<id>`). Where a file
carries no such id, `signature` — a hash over the identifying tags and the moves —
catches duplicates instead.

### `game_collections`

`(game_id, collection_id, added_at)` — the extra shelves a game sits on. `games.collection_id`
remains the owning collection; this table holds only the links, so every query that
existed before it still means what it did.

A collection contains the games it owns plus the games linked onto it, which is how
`search(collection=…)`, the collection counts and the PGN export all read it. Both
columns cascade on delete, and deleting a collection first hands any game it owns but
another collection also holds to that other collection.

### `reference_bases`

`(collection_id, path, attached_at)` — the collections that are attached bases rather
than imported games. Their rows in `games` carry `source='reference'` and a `path` into
the library's `reference/` folder instead of a collection folder, so the PGN is read
where it lies.

The table exists because the same fact derived by scanning `games` for that source costs
a full table scan — about eight seconds on ten million rows, every time the Master games
view opens. Two rows of fact deserve two rows. Each base's game count is then read
through `games(collection_id)`, which is indexed.

### `positions`

`(hash, game_id, ply, next_san)`. The hash is a transposition key: the same position
reached by a different move order hashes the same, which is what makes the position
search useful. Built per collection by the indexer.

### `pins`, `folders`, `collection_folders`, `game_tags`

Your own annotations on the library: notes pinned to a position, study folders that
exist as real directories, the collections assigned to them, and free-text labels on
games.

### `repertoires`

`id`, `name`, `color`, `data`, `updated_at`. `data` is JSON:

```json
{
  "lines": [
    {"moves": ["e4", "e5", "Nf3"], "fen": "…", "due": 0, "interval": 0, "successes": 0}
  ]
}
```

`due` is an epoch milliseconds timestamp; `interval` is the current spacing in days.

### `settings`, `explorer_cache`, `import_batches`, `import_members`

Preferences (including the lichess token, which never leaves the server), cached online
explorer answers, and the batch records that make an import undoable.

## PGN handling

Reading is deliberately split. The server splits files, reads tags and extracts the main
line — it never needs to understand chess to do that. The browser has a full rules
engine and does the rest: variations, legality, SAN, and the move tree.

### Comment commands

`[%…]` commands inside comments are lifted out of the prose, shown beside the moves they
belong to, and written back on save:

| Command | Meaning |
| --- | --- |
| `[%eval …]` | the engine's score for this move |
| `[%evp a,b,c]` | the main line's evaluation per ply, on the root |
| `[%cal …]` | arrows you drew |
| `[%csl …]` | circled squares |
| `[%clk]`, `[%emt]`, `[%mdl]`, `[%tqu]` | clocks, elapsed time, ChessBase medals and training positions — preserved, not interpreted |

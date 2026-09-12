# HTTP API

Everything the interface does, it does through this API. It is served on
`http://localhost:8000/api/…` by `server.py`, binds to loopback only, and has no
authentication because it has no remote surface to authenticate.

Requests and responses are JSON, except the handful of endpoints that return a file.
Errors come back as `{"error": "…"}` with a 4xx or 5xx status and a message written to be
shown to a person.

## Library

:::{list-table}
:header-rows: 1
:widths: 12 30 58

* - Method
  - Path
  - What it does
* - `GET`
  - `/api/health`
  - liveness, paths, and whether the engine is available
* - `GET`
  - `/api/stats`
  - game, collection and index counts
* - `GET`
  - `/api/collections`
  - every collection with its `kind` and game count
* - `POST`
  - `/api/collections`
  - create one — `{name, kind}` where kind is `games`, `studies` or `openings`
* - `GET`
  - `/api/collections/<id>/pgn`
  - the whole collection as one PGN download
* - `DELETE`
  - `/api/collections/<id>`
  - remove it; `?files=1` also deletes its PGN files
:::

## Games

`GET /api/games` takes the filters below as query parameters and returns
`{total, games: [...]}`. `limit` defaults to 100 and caps at 500; `offset` pages. Every
game carries `collections`: `[{id, name, kind, owner}]`, the shelves holding it, owner
first.

A `collection` filter matches the games a collection owns *and* the games linked onto it.
Import responses report `linked` alongside `added`, `duplicates` and `skipped`.

**Selecting what is listed**

: `kind` — `games` (the database's default), `studies`, `openings`, or empty for
  everything. `collection` — id or name.

**Who played**

: `q` free text, `player`, `white`, `black`, `min_elo`, `max_elo`, `white_min_elo`,
  `white_max_elo`, `black_min_elo`, `black_max_elo`, `outcome` (`win`/`loss`/`draw`,
  read from the player you named), `result`.

**What was played**

: `eco`, `eco_to`, `opening`, `variation`, `min_length`, `max_length`, `position` (a FEN,
  matched through the position index).

**Where and when**

: `event`, `site`, `round`, `year`, `date_from`, `date_to`, `event_type`,
  `event_date_from`, `event_date_to`.

**ChessBase tags**

: `team`, `title`, `fide_id`, `source_title` — each matching either player where the tag
  is per-side.

**Provenance and your own labels**

: `annotator`, `termination`, `annotated` (`0`/`1`), `source`, `tag`, `category`,
  `added_from`, `added_to`.

**Order**

: `sort` — `added`, `date`, `date_asc`, `event_date`, `event`, `round`, `elo`, `white`,
  `black`, `eco`, `opening`, `result`, `annotator`, `length`.

:::{list-table}
:header-rows: 1
:widths: 12 30 58

* - Method
  - Path
  - What it does
* - `GET`
  - `/api/games/<id>`
  - one game, with its PGN text
* - `POST`
  - `/api/games`
  - import — `{pgn, collection, kind, source}`; returns added / duplicates / skipped
* - `PUT`
  - `/api/games/<id>`
  - replace a game's PGN, keeping its id
* - `DELETE`
  - `/api/games/<id>`
  - remove one game from the index
* - `GET`
  - `/api/games/<id>/collections`
  - the collections holding this game, owner first
* - `POST`
  - `/api/games/<id>/collections`
  - `{collection, kind}` — link it onto another shelf, creating the collection if needed
* - `DELETE`
  - `/api/games/<id>/collections/<name>`
  - remove a link; a game's own collection cannot be unlinked
* - `POST`
  - `/api/games/delete-preview`
  - `{filters}` → a token, the count, and a sample
* - `POST`
  - `/api/games/delete-confirm`
  - `{token}` → deletes exactly the rows the preview identified
:::

## Importing

:::{list-table}
:header-rows: 1
:widths: 12 30 58

* - Method
  - Path
  - What it does
* - `GET`
  - `/api/import/status`
  - progress of the import currently running
* - `GET`
  - `/api/import/history`
  - recent batches, with counts and undone state
* - `POST`
  - `/api/import/undo`
  - `{batch_id}` — remove exactly what that import added
* - `POST`
  - `/api/import/source`
  - `{path, collection}` — a file, folder, archive or URL
* - `POST`
  - `/api/import/lichess`
  - `{user, max, token, collection}`
* - `POST`
  - `/api/import/chesscom`
  - `{user, max, collection}`
:::

## The engine

:::{list-table}
:header-rows: 1
:widths: 12 30 58

* - Method
  - Path
  - What it does
* - `GET`
  - `/api/engine/info`
  - engine name, path, threads, hash, and core counts
* - `POST`
  - `/api/engine/live`
  - `{fen, multipv}` — start continuous analysis; 1 to 5 lines
* - `GET`
  - `/api/engine/live`
  - current lines, search statistics and machine telemetry
* - `DELETE`
  - `/api/engine/live`
  - stop it
* - `POST`
  - `/api/engine/analyze`
  - `{fen, movetime, depth, multipv}` — one blocking search
* - `POST`
  - `/api/engine/annotate`
  - `{game_id, positions, movetime}` — score a whole game in the background
* - `GET`
  - `/api/engine/annotate`
  - progress and results
* - `POST`
  - `/api/engine/stop`
  - stop the annotation run
:::

A `GET /api/engine/live` response carries `lines`, plus `depth`, `seldepth`, `nodes`,
`nps`, `hashfull`, `tbhits`, `time`, the engine's own `cpu_percent` and `memory_mb`, and
a `machine` object with `cores`, `cpu_percent`, `cpu_mhz`, memory, `temperature_c` and
`power_w`. Any reading the machine does not publish is `null` rather than estimated.

## Study and positions

:::{list-table}
:header-rows: 1
:widths: 12 30 58

* - Method
  - Path
  - What it does
* - `GET`
  - `/api/study/position?fen=…`
  - games, continuations, decades and pins for a position
* - `POST`
  - `/api/study/index`
  - `{collection}` — start indexing positions
* - `GET`
  - `/api/study/index`
  - indexing progress
* - `POST` / `DELETE`
  - `/api/study/pins[/<id>]`
  - your notes and links on a position
* - `GET` / `POST` / `DELETE` / `PUT`
  - `/api/study/folders[/<id>]`
  - study folders on disk, and their category
* - `POST`
  - `/api/study/assign`
  - `{folder_id, collection_id}`
* - `GET` / `PUT`
  - `/api/study/tags`
  - a game's library labels
:::

## Repertoires

:::{list-table}
:header-rows: 1
:widths: 12 30 58

* - Method
  - Path
  - What it does
* - `GET`
  - `/api/repertoires`
  - every repertoire, newest first
* - `GET`
  - `/api/repertoires/<id>`
  - one, with its lines as JSON
* - `POST` / `PUT`
  - `/api/repertoires[/<id>]`
  - create or replace
* - `DELETE`
  - `/api/repertoires/<id>`
  - remove one
* - `POST`
  - `/api/repertoires/import`
  - `{pgn, name, color, id, max_plies, keep_pgn, collection}` — a PGN tree becomes lines
:::

## lichess account

:::{list-table}
:header-rows: 1
:widths: 12 30 58

* - Method
  - Path
  - What it does
* - `GET`
  - `/api/lichess/account`
  - who the stored token belongs to, its scopes, and where to make one
* - `PUT`
  - `/api/lichess/account`
  - `{token}` — verified with lichess, then stored
* - `DELETE`
  - `/api/lichess/account`
  - forget the token
* - `GET`
  - `/api/lichess/studies`
  - studies visible to the token (or to `?user=` without one)
* - `POST`
  - `/api/lichess/studies`
  - `{studies: [{id, name}], collection, kind, as_repertoire, name, color}` — a blank
    `collection` files each study under its own name
:::

The token is never returned by any endpoint. `GET /api/settings/lichess_token` is
refused with `403`.

## Reference material

:::{list-table}
:header-rows: 1
:widths: 12 30 58

* - Method
  - Path
  - What it does
* - `GET`
  - `/api/book?fen=…`
  - opening book: bundled, your indexed games, or lichess online
* - `GET`
  - `/api/explorer?fen=…&db=…`
  - the lichess explorer, cached in your library
* - `GET`
  - `/api/tablebase?fen=…`
  - seven-piece endgame result, cached
* - `GET`
  - `/api/literature?moves=…`
  - free study references for a line
* - `GET`
  - `/api/facts?white=…&black=…`
  - Wikipedia background for a game
* - `GET`
  - `/api/openings?q=…`
  - opening names present in your library, with their ECO span
* - `POST`
  - `/api/openings/classify`
  - name the openings of games that carry none
* - `GET`
  - `/api/masters/*`
  - master-game search and the crawler
* - `GET`
  - `/api/network`
  - whether online services are reachable
:::

## Books, sounds and settings

:::{list-table}
:header-rows: 1
:widths: 12 30 58

* - Method
  - Path
  - What it does
* - `GET` / `POST`
  - `/api/books`
  - list PDFs, or add one as base64
* - `GET`
  - `/api/books/<id>/file`
  - the PDF itself, with range requests
* - `PUT`
  - `/api/books/<id>`
  - remember the page you are on
* - `GET`
  - `/api/sounds`
  - which sample sets are installed, and the events each covers
* - `GET` / `PUT`
  - `/api/settings/<key>`
  - preferences; secret keys are refused
:::

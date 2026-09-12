# Python modules

Generated from the backend's own docstrings, so it cannot drift from the code.

## The library

```{eval-rst}
.. automodule:: backend.store
   :members:
   :member-order: bysource
```

## PGN reading

```{eval-rst}
.. automodule:: backend.pgnutil
   :members:
```

## Importing

```{eval-rst}
.. automodule:: backend.importers
   :members: sniff_encoding, decoded, streams, game_stream, import_local, import_source, chesscom
```

## Chess rules

```{eval-rst}
.. automodule:: backend.chess
   :members: Chess
```

## The engine

```{eval-rst}
.. automodule:: backend.engine
   :members:
```

## Machine telemetry

```{eval-rst}
.. automodule:: backend.hardware
   :members:
```

## Repertoire lines from PGN

```{eval-rst}
.. automodule:: backend.repertoire
   :members:
```

## Position index and study folders

```{eval-rst}
.. automodule:: backend.study
   :members:
```

## lichess client

```{eval-rst}
.. automodule:: backend.lichess
   :members: account, studies, study_pgn, token_scopes, user_games, explorer, Throttle
```

## The API surface

```{eval-rst}
.. automodule:: backend.api
   :members: Api, ApiError
```

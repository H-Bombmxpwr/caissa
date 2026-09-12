# Included offline opening book

Caissa's offline book is built from **Lichess Elite, November 2025**, curated by
Nicolas Noel: <https://database.nikonoel.fr/>. It contains online rated games between
2500+ and 2300+ players, excluding bullet. It is distinct from Lichess's
over-the-board Masters database, which remains an online reference option.

The underlying games come from the **CC0** Lichess database exports:
<https://database.lichess.org/>. CC0 dedication:
<https://creativecommons.org/publicdomain/zero/1.0/>.

`opening-book.json` records the archive URL, its SHA-256, source game count,
position count, move-entry count and coverage limits. The SQLite book keeps
continuations recorded in at least two source games, through 48 plies (24 full
moves). Repeated visits to the same position/continuation in one game count once.
Counts describe this snapshot, not the entire Lichess database.

Rebuild with `python -m pip install chess`, then
`python tools/build_opening_book.py`. python-chess is a GPL-3.0+ build tool;
the application uses its own chess rules and SQLite to read the finished book.
The build tool downloads into ignored `tmp/`; source PGNs are not bundled.
`data/opening-book.sqlite3`, this credit file and the metadata are bundled.

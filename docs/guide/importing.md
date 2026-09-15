# Importing games

Everything arrives as PGN in the end. What differs is where it comes from and how it is
encoded.

## PGN files and clipboard

**Import games → PGN files & clipboard**. Choose one or more `.pgn` files, or paste the
text. Name the collection first; the name is required, and the file names itself if you
have not typed one.

Duplicates are detected two ways: by source id where the file carries one (a lichess or
chess.com game id), and otherwise by a signature over the tags and the moves. Re-importing
the same file adds nothing and says so.

## ChessBase exports

ChessBase cannot be read natively — `.cbh`, `.cbv` and `.si4` are undocumented binary
formats, so export to PGN from ChessBase itself (**File → Export → PGN**, or right-click
a database and choose the PGN format). Everything after that is handled.

### Encoding

> **Why your accented names used to break**
>
> ChessBase writes PGN in the Windows code page, not UTF-8. Read as UTF-8, `Réti` becomes
> `R<?>ti` and the original letter is gone for good, because the replacement happens before
> anything is stored.
>
> Files are now decoded by sniffing: UTF-8 first, and where that is genuinely impossible,
> Windows-1252 and then Latin-1, applied to the whole file rather than guessed per chunk.
> UTF-16 files are detected from their byte-order mark. The same rule applies to files you
> drop in through the browser, to files read from disk, and to PGNs inside a ZIP.

### The tags ChessBase writes

ChessBase's tag set is richer than lichess's, and these are read, stored and searchable:

| Tag | Used for |
| --- | --- |
| `EventDate` | sorting and filtering by the tournament rather than the game |
| `EventType` | filtering by format, e.g. `swiss`, `team-swiss`, `k.o.` |
| `WhiteTeam`, `BlackTeam` | club and league play — one filter matches either side |
| `WhiteTitle`, `BlackTitle` | shown beside the name, and filterable (`GM`, `IM`, …) |
| `WhiteFideId`, `BlackFideId` | telling apart players who share a name |
| `SourceTitle` / `Source` | the publication a game came from |
| `Variation`, `SubVariation` | shown next to the opening name |
| `Annotator`, `Termination`, `PlyCount` | as elsewhere |

A library imported before these columns existed re-reads its own PGN once on the next
launch and fills them in — you do not need to import anything again.

### What is still missing

For completeness, the things ChessBase does that this does not:

- **Native database files.** `.cbh`/`.cbv`/`.si4` need an export step.
- **Medals and training annotations.** ChessBase's `[%mdl …]` and `[%tqu …]` commands
  survive a round trip inside the PGN, but nothing filters on them.
- **Player and tournament entities.** Players are matched by name and FIDE ID, not by a
  curated player database with photographs and biographies.

## Archives, folders and URLs

**Archives, folders & URLs** streams `.pgn`, `.zip`, `.gz`, `.bz2` and — with the
optional `zstandard` package — `.zst`, from a local path or an HTTPS URL. A folder is
scanned recursively. Nothing is extracted to disk: archives are read as streams, so a
multi-gigabyte dump does not need a multi-gigabyte temporary file.

```text
C:\Chess\TWIC                      a folder, scanned recursively
C:\Chess\twic1500g.zip             a local archive
https://theweekinchess.com/...zip  downloaded and streamed
```

## A base too big to import

A multi-gigabyte PGN — Lumbras GigaBase, a ChessBase export — is not imported. It is
**attached**: scanned once so the index knows where each game starts, then read where it
lies. Put it in a `reference` folder inside your library and attach it from **Master
games**. See [A reference base](reference-base.md).

## Your online games

**Your online games** imports from lichess or chess.com by username. A lichess token is
optional here but makes rate limits kinder, and if you have connected your account in
Settings the stored token is used automatically. **Import every game on the account**
works for both services; without it, set a maximum. Lichess exports arrive with their
clock times and stored evaluations, which is what the Player Lab reads to find time
trouble and costly moves.

### Following an import

Imports appear in a progress card in the bottom-right corner. You can switch
tabs while they run. When the total is known, the card shows a filling bar,
games processed, and a percentage. Fetching an online export may take time
before a game count is available.

For streamed downloads whose total is unknown, the card shows a cumulative
processed-game count and explains that games are still arriving. It does not
show a bouncing bar or estimate a percentage. Counts continue across batches
instead of restarting with each batch.

Completion shows a full bar and the numbers added, duplicated, and skipped.
The card disappears after eight seconds, or you can dismiss it immediately.
Errors remain visible until dismissed. Dismissing a notification does not undo
an import; use import history for that.

## lichess studies

**lichess studies** imports whole studies, including private and unlisted ones once your
account is connected. See [Your lichess account](lichess.md).

## Master games

The **Master games** module points at free collections — The Week in Chess by issue
number, and PGN Mentor's player and tournament files — and imports them the same way.

PGN Mentor publishes **one archive per player**, so "import Morozevich" always means his
entire career, not the part you searched for. That archive is kept as `Masters / <player>`.
What you searched for — an opening or ECO range, a colour, an outcome, a span of years —
is then saved as a collection of its own, named for the search:

```
Masters / Morozevich                                  every game in the archive
Masters / Morozevich / King's Indian Defense 1996–2012  just the ones you asked for
```

The second collection holds *links*, not copies: each game still lives in the archive and
is simply shelved in both places, so the same player can carry as many opening collections
as you care to look up without the library storing anything twice. Searching the same
player again for a different opening adds another shelf beside the first.

If a search matches nothing in the archive, no shelf is made and the whole archive is
shown instead, with a message saying so.

**Year from** and **Year through** narrow by the game's date and, when set, become part of
the collection's name — so the same opening over two different periods stays two
collections rather than one.

## Naming openings

Games imported without an `Opening` tag can be named from the bundled ECO data:
**Database → Name openings**. It never overwrites a name a file already carries.

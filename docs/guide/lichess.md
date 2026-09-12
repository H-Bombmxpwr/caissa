# Your lichess account

Connecting your lichess account does two things: it makes your own games easier to
import, and it makes your **private and unlisted studies** reachable at all. Without a
token, lichess will not admit an unlisted study exists.

## Connecting

1. **Settings → lichess account → Open lichess token page.** The link already asks for
   the right permissions.
2. The scopes requested are `study:read` and `preference:read`. Both are read-only —
   nothing here can play a game, write a study, or change your account.
3. Create the token, copy it, paste it into **Personal access token**, and choose
   **Connect account**.

The token is checked with lichess before it is stored, so a mistyped or expired token
fails immediately rather than silently later. Once connected, the card shows which
account it belongs to and which scopes it carries.

:::{admonition} Where the token lives
:class: note

In your local library's settings table, on your own disk. It is sent to lichess and
nowhere else, and it is never handed back to the page: the generic settings endpoint
refuses to read it, and the account endpoint reports only the username and scopes. Use
**Forget this token** to remove it.

A token that has been revoked on lichess's side shows as disconnected with the reason,
rather than looking connected and failing on use.
:::

## Importing studies

**Import my studies** — from the account card, or from **Import games → lichess
studies** — lists every study lichess will show your token, newest first, with
checkboxes.

**Save chapters into** decides the filing. The default, *a collection per study named
after it*, is almost always what you want: pick a study called "john games" and you get a
collection called `john games`. Choose *one collection for all of them* to pool several
studies under a single name instead.

Chapters are saved with kind `studies`, so they stay out of the game database while
remaining fully searchable (choose **Study positions** in the database's Content
dropdown). Because that means they would not appear in the default view, the database
opens on the new collection as soon as the import finishes, so there is nothing to go
hunting for. Tick **Also build drillable repertoire lines** to run the same chapters
through the [repertoire importer](repertoire.md) in one pass.

A chapter you already have elsewhere in the library is
[linked](database.md#one-game-several-collections) rather than skipped, so a study that
collects games you have imported before still lists all of them.

A study that cannot be read — revoked access, or a chapter that exports nothing — is
reported by name and does not stop the others from importing. The whole import is one
undoable batch, listed under **Recent imports**.

## Importing games automatically

**Settings → lichess account → Import my games as they are played** puts new games into
your library on their own. The server asks lichess, on the interval you choose, what has
been played since it last looked, and files the answer.

| Setting | What it does |
| --- | --- |
| How often | 5 minutes to twice a day. Fifteen minutes is a reasonable default. |
| Most games per check | a ceiling, so a marathon blitz session cannot flood a check |
| Collection | where they go — `My lichess games` by default |
| Rated games only | skips casual games |
| Index positions after each import | keeps the position search current, so a game you just played turns up under **Library** and **History** on the analysis board |

**Check lichess now** runs a check immediately, whether or not the watcher is on.

:::{admonition} Switching it on does not backfill
:class: note

The window starts from the moment you enable it. Pulling in a decade of blitz because
somebody ticked a box is not a welcome surprise, so history stays a deliberate act —
use **Import games → Your online games** for that.
:::

Three details worth knowing:

- **Each check overlaps the last by ten minutes**, so a game that ended in the gap between
  checks is still caught. The repeat costs nothing: duplicates are recognised by lichess
  game id.
- **A failed check does not move the window forward.** If your connection drops, the next
  check asks for the same period again rather than skipping it.
- **Every run is an undoable batch**, listed under **Import games → Recent imports** as
  "Auto-import from lichess", so a run that brought in something you did not want can be
  taken back like any other import.

The watcher stops when you switch it off, when you forget the token, and when the app
closes. It never runs without a connected account.

## Importing your games

**Import games → Your online games** takes a username and a maximum. If your account is
connected the stored token is used automatically, which raises the rate limits lichess
applies.

All lichess requests go through one throttled queue in the server: one request at a time,
with a shared cooldown after a `429`. Clicking "load" repeatedly cannot make it worse.

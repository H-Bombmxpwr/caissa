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

Chapters are saved into a collection of kind `studies`, so they stay out of the game
database while remaining fully searchable there (choose **Study positions** in the
database's Content dropdown). Tick **Also build drillable repertoire lines** to run the
same chapters through the [repertoire importer](repertoire.md) in one pass.

A study that cannot be read — revoked access, or a chapter that exports nothing — is
reported by name and does not stop the others from importing. The whole import is one
undoable batch, listed under **Recent imports**.

## Importing your games

**Import games → Your online games** takes a username and a maximum. If your account is
connected the stored token is used automatically, which raises the rate limits lichess
applies.

All lichess requests go through one throttled queue in the server: one request at a time,
with a shared cooldown after a `429`. Clicking "load" repeatedly cannot make it worse.

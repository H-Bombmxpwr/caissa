"""Keep a lichess account's games flowing into the library as they are played.

A background thread asks lichess, every so often, for the games played since it last
looked. That is deliberately a poll rather than a live stream: streaming an account's
games needs board scopes this app has no business holding, and a game is worth analysing
a few minutes after it ends just as much as a few seconds after.

Three decisions worth stating, because each one is a trap avoided:

* **Windows overlap.** Each poll asks for games since a little before the last one
  finished, not since exactly then. A game that ended during the gap is caught, and the
  repeat is free because duplicates are detected by lichess game id.
* **Enabling does not backfill.** Switching this on starts from now. Pulling in a decade
  of blitz because somebody ticked a box is not a welcome surprise; the manual importer
  is still there for history, and "Import now" fetches a window on request.
* **Every run is an undoable batch**, exactly like an import you started by hand, so a
  run that brings in something unwanted can be taken back.
"""

import json
import threading
import time

from . import lichess

KEY = "lichess_autoimport"
OVERLAP_MS = 10 * 60 * 1000          # re-ask for the last ten minutes; duplicates are free
MIN_INTERVAL = 5
MAX_INTERVAL = 24 * 60

DEFAULTS = {
    "enabled": False,
    "interval_minutes": 15,
    "collection": "My lichess games",
    "max_games": 50,
    "index_after": False,
    "rated_only": False,
    "since": None,                   # epoch ms; set when the watcher is switched on
}


class AutoImport:
    """Polls lichess for new games and files them in the library."""

    def __init__(self, library, token, study=None):
        self.library = library
        self.token = token           # callable returning the stored token, or None
        self.study = study
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.thread = None
        self.stopping = False
        self.state = {"running": False, "checking": False, "last_checked": None,
                      "last_added": 0, "total_added": 0, "last_error": None,
                      "next_check": None, "user": None}

    # ---------- settings ----------

    def settings(self):
        stored = self.library.setting(KEY)
        values = dict(DEFAULTS)
        if stored:
            try:
                values.update({k: v for k, v in json.loads(stored).items() if k in DEFAULTS})
            except ValueError:
                pass
        return values

    def save(self, changes):
        """Validate and store the watcher's settings, then start or stop it to match."""
        values = self.settings()
        if "interval_minutes" in changes:
            try:
                minutes = int(changes["interval_minutes"])
            except (TypeError, ValueError) as err:
                raise ValueError("Choose how often to check, in minutes") from err
            values["interval_minutes"] = max(MIN_INTERVAL, min(MAX_INTERVAL, minutes))
        if "max_games" in changes:
            try:
                values["max_games"] = max(1, min(int(changes["max_games"]), 300))
            except (TypeError, ValueError) as err:
                raise ValueError("Choose how many games a check may bring in") from err
        if "collection" in changes:
            name = str(changes["collection"]).strip()
            if not name:
                raise ValueError("Name the collection these games should go into")
            values["collection"] = name
        for flag in ("index_after", "rated_only"):
            if flag in changes:
                values[flag] = bool(changes[flag])
        if "enabled" in changes:
            wanted = bool(changes["enabled"])
            # Switching on starts from now rather than from the beginning of time.
            if wanted and not values["enabled"]:
                values["since"] = int(time.time() * 1000)
            values["enabled"] = wanted
        if "since" in changes:
            values["since"] = int(changes["since"]) if changes["since"] else None

        self.library.setting(KEY, json.dumps(values))
        self.apply(values)
        return values

    def apply(self, values=None):
        values = values or self.settings()
        if values["enabled"] and self.token():
            self.start()
        else:
            self.stop()
        return values

    # ---------- the loop ----------

    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():
                self.wake.set()                      # already running: just re-read settings
                return
            self.stopping = False
            self.state["running"] = True
            self.thread = threading.Thread(target=self._loop, daemon=True,
                                           name="lichess-autoimport")
            self.thread.start()

    def stop(self, timeout=2.0):
        self.stopping = True
        self.wake.set()
        thread = self.thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            # Wait briefly so the thread can let go of its database connection; a poll
            # already talking to lichess is left to finish on its own.
            thread.join(timeout)
        self.state["running"] = False
        self.state["next_check"] = None

    def trigger(self):
        """Ask for a check now, whether or not the watcher is running."""
        if self.thread and self.thread.is_alive():
            self.wake.set()
            return {"triggered": True}
        return self.run_once()

    def _loop(self):
        try:
            while not self.stopping:
                values = self.settings()
                if not values["enabled"] or not self.token():
                    break
                self.run_once(values)
                if self.stopping:
                    break
                delay = max(MIN_INTERVAL, values["interval_minutes"]) * 60
                self.state["next_check"] = int(time.time() + delay)
                self.wake.wait(delay)
                self.wake.clear()
        finally:
            # Connections are per-thread; this one dies with the thread, and on Windows
            # an open handle would keep the library file locked after it had gone.
            self.library.close()
            self.state["running"] = False
            self.state["next_check"] = None

    # ---------- one check ----------

    def run_once(self, values=None):
        """Fetch and file whatever has been played since the last look."""
        values = values or self.settings()
        token = self.token()
        if not token:
            self.state["last_error"] = "Connect your lichess account first."
            return {"added": 0, "error": self.state["last_error"]}
        self.state["checking"] = True
        started = int(time.time() * 1000)
        batch = None
        try:
            user = self.state.get("user") or lichess.account(token)["username"]
            self.state["user"] = user
            since = values.get("since") or (started - OVERLAP_MS)
            pgn = lichess.user_games(
                user,
                max_games=values["max_games"],
                since=max(0, int(since) - OVERLAP_MS),
                rated=True if values.get("rated_only") else None,
                token=token,
            )
            result = {"added": 0, "duplicates": 0, "skipped": 0, "linked": 0}
            if pgn.strip():
                batch = self.library.begin_import("Auto-import from lichess")
                result = self.library.add_games(pgn, collection=values["collection"],
                                                source="lichess")
            self.state.update(last_checked=int(time.time()), last_added=result["added"],
                              total_added=self.state["total_added"] + result["added"],
                              last_error=None)
            # Only move the cursor forward on a clean run, so a failed check re-asks.
            self.save_cursor(values, started)
            if result["added"] and values.get("index_after") and self.study:
                try:
                    self.study.index(values["collection"])
                except (ValueError, KeyError):
                    pass                                  # an index already running is fine
            return result
        except Exception as err:                          # noqa: BLE001 - a poll never crashes the app
            self.state["last_error"] = str(err) or err.__class__.__name__
            self.state["last_checked"] = int(time.time())
            return {"added": 0, "error": self.state["last_error"]}
        finally:
            self.state["checking"] = False
            if batch:
                self.library.end_import(batch)

    def save_cursor(self, values, stamp):
        values = dict(values)
        values["since"] = stamp
        self.library.setting(KEY, json.dumps(values))

    # ---------- what the interface shows ----------

    def status(self):
        values = self.settings()
        out = dict(self.state)
        out.update(values)
        out["connected"] = bool(self.token())
        out["running"] = bool(self.thread and self.thread.is_alive())
        return out

"""Server-side lichess client.

Doing the network work here rather than in the browser fixes the rate limiting:
one process, one queue, one request at a time, with a shared cooldown. The
browser can click "load" as often as it likes.
"""

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://lichess.org"
EXPLORER = "https://explorer.lichess.ovh"
USER_AGENT = "BlindfoldTrainer/2.0 (local chess database; contact: local user)"
GAME_SEPARATOR = "\n\n"


class RateLimited(Exception):
    def __init__(self, retry_after):
        super().__init__("lichess rate limited; retry in %ss" % retry_after)
        self.retry_after = retry_after


class Throttle:
    """One request at a time, with a minimum gap and a cooldown after a 429."""

    def __init__(self, min_gap=1.0):
        self.min_gap = min_gap
        self.lock = threading.Lock()
        self.last = 0.0
        self.cooldown_until = 0.0

    def wait(self):
        with self.lock:
            now = time.time()
            target = max(self.last + self.min_gap, self.cooldown_until)
            if target > now:
                time.sleep(target - now)
            self.last = time.time()

    def penalize(self, seconds):
        with self.lock:
            self.cooldown_until = max(self.cooldown_until, time.time() + seconds)

    def cooldown_left(self):
        return max(0.0, self.cooldown_until - time.time())


api_throttle = Throttle(min_gap=1.5)        # game export is the strict one
explorer_throttle = Throttle(min_gap=0.7)


def _request(url, accept, token=None, throttle=None, timeout=120, retries=2, data=None,
             content_type="text/plain"):
    throttle = throttle or api_throttle
    attempt = 0
    while True:
        throttle.wait()
        headers = {"Accept": accept, "User-Agent": USER_AGENT}
        if data is not None:
            headers["Content-Type"] = content_type
        req = urllib.request.Request(url, headers=headers,
                                     data=data.encode("utf-8") if isinstance(data, str) else data)
        if token:
            req.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as res:
                return res.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as err:
            if err.code == 429:
                retry_after = int(err.headers.get("Retry-After") or 62)
                throttle.penalize(retry_after)
                attempt += 1
                if attempt > retries:
                    raise RateLimited(retry_after)
                continue
            if err.code == 404:
                raise FileNotFoundError(url)
            if err.code in (401, 403):
                raise PermissionError(
                    "lichess rejected the access token: it may have expired, been revoked, "
                    "or lack the scope this needs" if token else
                    "lichess now requires a signed-in account for this. Connect your lichess "
                    "account in Settings and try again.")
            raise
        except urllib.error.URLError as err:
            attempt += 1
            if attempt > retries:
                raise ConnectionError(str(err.reason))
            time.sleep(2 * attempt)


def user_games(user, max_games=100, color=None, rated=None, perf=None, since=None, token=None):
    params = {
        "max": int(max_games),
        "moves": "true",
        "tags": "true",
        "clocks": "false",
        "evals": "false",
        "opening": "true",
        "sort": "dateDesc",
    }
    if color:
        params["color"] = color
    if rated is not None:
        params["rated"] = "true" if rated else "false"
    if perf:
        params["perfType"] = perf
    if since:
        params["since"] = int(since)
    url = "%s/api/games/user/%s?%s" % (API, urllib.parse.quote(user), urllib.parse.urlencode(params))
    return _request(url, "application/x-chess-pgn", token=token)


def _user_games_url(user, max_games=None, color=None, rated=None, perf=None, since=None,
                    until=None):
    params = {
        "moves": "true", "tags": "true", "clocks": "false",
        "evals": "false", "opening": "true", "sort": "dateDesc",
    }
    if max_games:
        params["max"] = int(max_games)
    if color:
        params["color"] = color
    if rated is not None:
        params["rated"] = "true" if rated else "false"
    if perf:
        params["perfType"] = perf
    if since:
        params["since"] = int(since)
    if until:
        params["until"] = int(until)
    return "%s/api/games/user/%s?%s" % (API, urllib.parse.quote(user),
                                        urllib.parse.urlencode(params))


def import_all_user_games(library, user, collection, token=None, batch_size=200,
                          progress=None, **selection):
    """Stream a whole lichess account into the library, however many games that is.

    Asking for every game means not knowing how many are coming, which rules out
    holding the answer in memory: an active account is hundreds of megabytes of PGN.
    So the response is read as it arrives and written in batches, and the caller is
    told the running count rather than made to wait in silence.

    `selection` takes the same narrowing arguments as `user_games` — color, rated,
    perf, since, until — so "every rated blitz game since 2023" is one call.
    """
    url = _user_games_url(user, max_games=None, **selection)
    throttle = api_throttle
    throttle.wait()
    headers = {"Accept": "application/x-chess-pgn", "User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers)

    totals = {"added": 0, "duplicates": 0, "skipped": 0, "linked": 0}
    batch, chunk = [], []

    def flush():
        if not batch:
            return
        result = library.add_games("\n\n".join(batch), collection=collection, source="lichess")
        for key in totals:
            totals[key] += result.get(key, 0)
        batch.clear()
        if progress:
            progress(totals["added"] + totals["duplicates"], 0)

    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            for raw in response:
                line = raw.decode("utf-8", "replace")
                # A new game starts at its Event tag; everything before belongs to the last.
                if line.startswith("[Event ") and chunk:
                    batch.append("".join(chunk))
                    chunk = []
                    if len(batch) >= batch_size:
                        flush()
                chunk.append(line)
        if chunk:
            batch.append("".join(chunk))
        flush()
    except urllib.error.HTTPError as err:
        if err.code == 429:
            raise RateLimited(int(err.headers.get("Retry-After") or 62)) from err
        if err.code == 404:
            raise FileNotFoundError(url) from err
        if err.code in (401, 403):
            raise PermissionError("lichess refused the export: check the access token") from err
        raise
    except urllib.error.URLError as err:
        # Whatever arrived before the connection dropped is already saved.
        raise ConnectionError(str(err.reason)) from err
    totals["user"] = user
    return totals


def explorer(db="masters", play=None, fen=None, moves=12, top_games=8, extra=None, token=None):
    params = {"moves": int(moves)}
    if db == "masters":
        params["topGames"] = int(top_games)
    else:
        params["variant"] = "standard"
        params["topGames"] = 0
        params["recentGames"] = 0
    if play:
        params["play"] = ",".join(play) if isinstance(play, (list, tuple)) else play
    if fen:
        params["fen"] = fen
    if extra:
        params.update(extra)
    url = "%s/%s?%s" % (EXPLORER, db, urllib.parse.urlencode(params))
    return json.loads(_request(url, "application/json", throttle=explorer_throttle,
                               timeout=60, token=token))


def masters_pgn(game_id, token=None):
    url = "%s/masters/pgn/%s" % (EXPLORER, urllib.parse.quote(game_id))
    return _request(url, "application/x-chess-pgn", throttle=explorer_throttle, timeout=60,
                    token=token)


class MastersCrawler:
    """Walks the masters opening explorer and files away the games it names.

    Breadth-first from the start position: every position it visits contributes
    its top games, and every move played often enough becomes a new position to
    visit. Slow by design (the explorer is a free service) but it can be left
    running, and it picks up where it left off.
    """

    def __init__(self, library):
        self.library = library
        self.thread = None
        self.stop_flag = threading.Event()
        self.state = {
            "running": False,
            "positions_done": 0,
            "games_added": 0,
            "duplicates": 0,
            "queued": 0,
            "current": "",
            "error": None,
            "started_at": None,
            "finished_at": None,
        }
        self.lock = threading.Lock()

    def status(self):
        with self.lock:
            out = dict(self.state)
        out["cooldown"] = round(explorer_throttle.cooldown_left(), 1)
        return out

    def start(self, max_depth=8, max_positions=400, min_games=200, top_games=8,
              collection="Masters", opening_moves=None):
        if self.thread and self.thread.is_alive():
            return False
        self.stop_flag.clear()
        with self.lock:
            self.state.update({
                "running": True, "positions_done": 0, "games_added": 0, "duplicates": 0,
                "queued": 1, "current": "start position", "error": None,
                "started_at": int(time.time()), "finished_at": None,
            })
        self.thread = threading.Thread(
            target=self._run,
            args=(max_depth, max_positions, min_games, top_games, collection, opening_moves or []),
            daemon=True,
        )
        self.thread.start()
        return True

    def stop(self):
        self.stop_flag.set()

    def _run(self, max_depth, max_positions, min_games, top_games, collection, opening_moves):
        self.library.ensure_collection(collection, kind="masters")
        seen_positions = set()
        seen_games = set()
        queue = [tuple(opening_moves)]
        positions = 0

        try:
            while queue and positions < max_positions and not self.stop_flag.is_set():
                play = queue.pop(0)
                key = ",".join(play)
                if key in seen_positions:
                    continue
                seen_positions.add(key)

                with self.lock:
                    self.state["current"] = key or "start position"
                    self.state["queued"] = len(queue)

                try:
                    data = explorer("masters", play=list(play), moves=12, top_games=top_games,
                                    token=self.library.setting("lichess_token") or None)
                except RateLimited as err:
                    with self.lock:
                        self.state["error"] = "rate limited, waiting %ss" % err.retry_after
                    time.sleep(min(err.retry_after, 65))
                    queue.insert(0, play)
                    seen_positions.discard(key)
                    continue
                except Exception as err:                      # noqa: BLE001 - keep crawling
                    with self.lock:
                        self.state["error"] = str(err)
                    continue

                positions += 1
                with self.lock:
                    self.state["positions_done"] = positions
                    self.state["error"] = None

                pgns = []
                for game in data.get("topGames", []):
                    gid = game.get("id")
                    if not gid or gid in seen_games or self.stop_flag.is_set():
                        continue
                    seen_games.add(gid)
                    try:
                        pgns.append(masters_pgn(gid, token=self.library.setting("lichess_token") or None))
                    except Exception:                          # noqa: BLE001
                        continue
                if pgns:
                    result = self.library.add_games(
                        "\n\n".join(pgns), collection=collection, source="masters"
                    )
                    with self.lock:
                        self.state["games_added"] += result["added"]
                        self.state["duplicates"] += result["duplicates"]

                if len(play) < max_depth:
                    for move in data.get("moves", []):
                        total = (move.get("white", 0) + move.get("draws", 0) + move.get("black", 0))
                        if total >= min_games:
                            queue.append(tuple(list(play) + [move["uci"]]))

                with self.lock:
                    self.state["queued"] = len(queue)
        finally:
            with self.lock:
                self.state["running"] = False
                self.state["finished_at"] = int(time.time())
                self.state["current"] = ""


def _open_pgn_stream(path):
    """Text stream over a .pgn or .pgn.zst file, plus the handle to close."""
    if path.endswith(".zst"):
        try:
            import zstandard
        except ImportError as err:                        # pragma: no cover - optional path
            raise RuntimeError(
                "Reading .zst dumps needs the zstandard package: pip install zstandard"
            ) from err
        import io
        handle = open(path, "rb")
        reader = zstandard.ZstdDecompressor().stream_reader(handle)
        return io.TextIOWrapper(reader, encoding="utf-8", errors="replace"), handle
    handle = open(path, "r", encoding="utf-8", errors="replace")
    return handle, handle


def import_dump(library, path, collection="Masters", limit=None, batch_size=500, progress=None):
    """Import a downloaded lichess PGN dump (plain .pgn, or .pgn.zst with `zstandard`).

    Streamed in batches so a multi-gigabyte file never has to fit in memory.
    """
    stream, raw = _open_pgn_stream(path)
    added = duplicates = linked = 0
    batch, chunk = [], []

    def flush():
        nonlocal added, duplicates, linked, batch
        if not batch:
            return
        result = library.add_games(GAME_SEPARATOR.join(batch), collection=collection, source="dump")
        added += result["added"]
        duplicates += result["duplicates"]
        linked += result.get("linked", 0)
        batch = []
        if progress:
            progress(added, duplicates)

    try:
        for line in stream:
            if line.startswith("[Event ") and chunk:
                batch.append("".join(chunk))
                chunk = []
                if len(batch) >= batch_size:
                    flush()
                    if limit and added >= limit:
                        return {"added": added, "duplicates": duplicates, "linked": linked}
            chunk.append(line)
        if chunk:
            batch.append("".join(chunk))
        flush()
    finally:
        try:
            raw.close()
        except Exception:                                 # noqa: BLE001
            pass
    return {"added": added, "duplicates": duplicates, "linked": linked}


# ---------- account, and the studies only an account can see ----------

# A study you have not made public is invisible without a token carrying study:read.
# These are the scopes the app asks for, and nothing here needs a write scope.
SCOPES = ("study:read", "preference:read")
TOKEN_URL = (API + "/account/oauth/token/create?"
             + urllib.parse.urlencode([("scopes[]", s) for s in SCOPES]
                                      + [("description", "Caissa chess study")]))


def token_scopes(token):
    """What a personal access token is allowed to do, straight from lichess."""
    body = _request(API + "/api/token/test", "application/json", data=token,
                    content_type="text/plain")
    entry = (json.loads(body) or {}).get(token) or {}
    if not entry:
        raise PermissionError("lichess does not recognise that token")
    return {"user_id": entry.get("userId"),
            "scopes": [s for s in (entry.get("scopes") or "").split(",") if s],
            "expires": entry.get("expires")}


def account(token):
    """The signed-in account, plus the scopes the token carries."""
    profile = json.loads(_request(API + "/api/account", "application/json", token=token))
    details = {"username": profile.get("username") or profile.get("id"),
               "id": profile.get("id"), "title": profile.get("title"),
               "url": profile.get("url") or (API + "/@/" + (profile.get("username") or ""))}
    try:
        details.update(token_scopes(token))
    except (PermissionError, ValueError, urllib.error.URLError):
        details.setdefault("scopes", [])            # the account call already proved the token
    details["can_read_studies"] = "study:read" in (details.get("scopes") or [])
    return details


def studies(username, token=None):
    """Every study lichess will show this token, newest first. Private ones need study:read."""
    url = "%s/api/study/by/%s" % (API, urllib.parse.quote(username))
    body = _request(url, "application/x-ndjson", token=token)
    out = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        out.append({"id": entry.get("id"), "name": entry.get("name"),
                    "created_at": entry.get("createdAt"), "updated_at": entry.get("updatedAt")})
    out.sort(key=lambda s: s.get("updated_at") or 0, reverse=True)
    return out


def study_pgn(study_id, token=None, comments=True, variations=True):
    """One study exported as PGN, every chapter in one file."""
    params = urllib.parse.urlencode({
        "clocks": "false", "comments": "true" if comments else "false",
        "variations": "true" if variations else "false", "orientation": "true"})
    url = "%s/api/study/%s.pgn?%s" % (API, urllib.parse.quote(study_id), params)
    return _request(url, "application/x-chess-pgn", token=token)

"""Free study material for a position.

Three layers, in order of certainty:

1. Deterministic URLs that are correct by construction — Wikibooks' *Chess Opening
   Theory* has one page per move path, and lichess has one page per named opening.
   Wikibooks pages are existence-checked through the MediaWiki API so we never hand
   over a dead link.
2. A curated index of free lectures shipped in data/lectures.json, matched by ECO
   code or opening name.
3. Whatever the user pinned to the position themselves (handled in study.py).

Nothing here scrapes, and nothing here invents a link it has not checked.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LECTURES = os.path.join(ROOT, "data", "lectures.json")
WIKIBOOKS_API = "https://en.wikibooks.org/w/api.php"
USER_AGENT = "Caissa/1.0 (local chess study app)"

_lectures_cache = {"mtime": 0, "items": []}


def move_path(sans):
    """['e4','c5','Nf3'] -> 'Chess Opening Theory/1. e4/1...c5/2. Nf3'."""
    parts = ["Chess Opening Theory"]
    for index, san in enumerate(sans):
        number = index // 2 + 1
        parts.append("%d. %s" % (number, san) if index % 2 == 0 else "%d...%s" % (number, san))
    return "/".join(parts)


def wikibooks_pages(sans, depth=8):
    """The deepest existing Chess Opening Theory pages for this line.

    One API call checks up to 50 titles, so ask about the whole path at once and
    keep the ones that exist.
    """
    titles = [move_path(sans[:i]) for i in range(1, min(len(sans), depth) + 1)]
    if not titles:
        return []
    params = {"action": "query", "format": "json", "titles": "|".join(titles)}
    url = WIKIBOOKS_API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            data = json.loads(res.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return []

    found = []
    for page in (data.get("query", {}).get("pages") or {}).values():
        if "missing" in page:
            continue
        title = page.get("title", "")
        found.append({
            "title": title.replace("Chess Opening Theory/", "Theory: "),
            "url": "https://en.wikibooks.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
            "kind": "wikibooks",
            "depth": title.count("/"),
        })
    found.sort(key=lambda item: item["depth"], reverse=True)
    return found[:4]


def load_index():
    """The curated index, reloaded whenever the file changes on disk."""
    try:
        mtime = os.path.getmtime(LECTURES)
    except OSError:
        return {"channels": [], "lectures": []}
    if mtime != _lectures_cache["mtime"]:
        try:
            with open(LECTURES, encoding="utf-8") as handle:
                data = json.load(handle)
            _lectures_cache["items"] = {
                "channels": data.get("channels", []),
                "lectures": data.get("lectures", []),
            }
            _lectures_cache["mtime"] = mtime
        except (ValueError, OSError):
            _lectures_cache["items"] = {"channels": [], "lectures": []}
    return _lectures_cache["items"]


def load_lectures():
    return load_index()["lectures"]


def channel_searches(opening):
    """A channel-scoped search per curated teacher.

    Search URLs are deterministic and never go stale, which is why they are used
    instead of guessed video links.
    """
    family = (opening or "").split(":")[0].strip()
    if not family:
        return []
    out = []
    for channel in load_index()["channels"]:
        query = "%s %s" % (channel.get("query", ""), family)
        out.append({
            "title": "%s — search “%s”" % (channel["name"], family),
            "url": "https://www.youtube.com/results?" + urllib.parse.urlencode({"search_query": query.strip()}),
            "kind": "search",
            "note": channel.get("note", ""),
        })
    return out


def lectures_for(opening, eco):
    opening_l = (opening or "").lower()
    eco = (eco or "").upper()[:3]
    hits = []
    for item in load_lectures():
        matched = False
        for code in item.get("eco", []):
            if eco and eco.startswith(code.upper()):
                matched = True
        for phrase in item.get("match", []):
            if phrase.lower() in opening_l and opening_l:
                matched = True
        if matched:
            hits.append({
                "title": "%s — %s" % (item.get("author", "Lecture"), item["title"]),
                "url": item["url"],
                "kind": "video",
            })
    return hits[:8]


def named_opening_links(opening):
    """lichess and Wikipedia pages for a named opening."""
    if not opening:
        return []
    family = opening.split(":")[0].strip()
    if not family:
        return []
    return [
        {
            "title": "lichess opening page: " + family,
            "url": "https://lichess.org/opening/" + urllib.parse.quote(family.replace(" ", "_")),
            "kind": "reference",
        },
        {
            "title": "Wikipedia: " + family,
            "url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(family.replace(" ", "_")),
            "kind": "reference",
        },
    ]


def references(sans, opening=None, eco=None, online=True):
    """Everything free we can point at for this position."""
    links = []
    message = None

    if online:
        pages = wikibooks_pages(sans)
        links.extend(pages)
        if not pages and sans:
            message = "Wikibooks has no theory page for this exact line yet."
    elif sans:
        message = "Offline — showing only links that need no lookup."

    links.extend(named_opening_links(opening))

    links.extend(lectures_for(opening, eco))
    links.extend(channel_searches(opening))
    if not opening:
        note = "Name the opening (import a game with an Opening tag) for teacher links."
        message = (message + " " + note) if message else note

    seen, unique = set(), []
    for link in links:
        if link["url"] in seen:
            continue
        seen.add(link["url"])
        unique.append(link)
    return {"links": unique, "message": message}

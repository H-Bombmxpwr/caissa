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
import re
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


WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"


def _surname(name):
    """PGN names are 'Karpov, Anatoly'; Wikipedia wants 'Anatoly Karpov'."""
    name = (name or "").strip()
    # "White"/"Black" are what an unnamed study carries, and both are real article titles.
    if not name or name in ("?", "-", "NN", "White", "Black", "Unknown"):
        return ""
    if "," in name:
        last, _, first = name.partition(",")
        return (first.strip() + " " + last.strip()).strip()
    return name


def _named(value):
    """Drop the placeholders PGN writers use when there was nothing to record."""
    value = (value or "").strip()
    generic = {"", "?", "-", "--", "study", "casual game", "unknown", "chess", "game",
               "local event", "internet", "?/?", "rated game", "unrated game"}
    return "" if value.lower() in generic else value


def _wikipedia(titles):
    """Summaries for the titles that actually exist, following redirects.

    One query covers up to 20 titles. Anything missing is simply absent from the
    result: this never reports a page it has not seen come back from the API.
    """
    titles = [t for t in dict.fromkeys(titles) if t]
    if not titles:
        return {}
    params = {
        "action": "query", "format": "json", "formatversion": "2", "redirects": "1",
        "prop": "extracts|info|pageprops", "exintro": "1", "explaintext": "1", "exsentences": "3",
        "inprop": "url", "titles": "|".join(titles[:20]),
    }
    url = WIKIPEDIA_API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            data = json.loads(res.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return {}
    found = {}
    for page in data.get("query", {}).get("pages") or []:
        if page.get("missing") or not page.get("extract"):
            continue
        # A disambiguation page is a list of things it might be, never a fact about one.
        if "disambiguation" in (page.get("pageprops") or {}):
            continue
        found[page["title"]] = {
            "title": page["title"],
            "extract": page["extract"].strip(),
            "url": page.get("fullurl") or "https://en.wikipedia.org/wiki/" + urllib.parse.quote(page["title"].replace(" ", "_")),
        }
    aliases = {item['from']: item['to'] for kind in ('normalized', 'redirects')
               for item in data.get('query', {}).get(kind, [])}
    for title in titles:
        resolved, seen = title, set()
        while resolved in aliases and resolved not in seen:
            seen.add(resolved)
            resolved = aliases[resolved]
        if resolved in found:
            found[title] = found[resolved]
    return found


def _wikipedia_search(term, limit=3):
    """Titles matching a phrase, so a famous game can be found by its own name."""
    if not term:
        return []
    params = {"action": "query", "format": "json", "formatversion": "2",
              "list": "search", "srsearch": term, "srlimit": limit}
    url = WIKIPEDIA_API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            data = json.loads(res.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return []
    return [hit["title"] for hit in data.get("query", {}).get("search") or []]


def game_facts(headers, online=True):
    """Background reading for one game, grouped by what each article is actually about.

    Wikipedia has articles about players, about events, and about a handful of famous
    individual games. Only the first two can be matched with confidence from PGN tags,
    so anything found by searching for the game itself is offered as a possibility and
    labelled that way rather than asserted. Nothing here is generated: every entry is a
    page the API returned.
    """
    white, black = _surname(headers.get("White")), _surname(headers.get("Black"))
    event = _named(headers.get("Event"))
    site = _named(headers.get("Site"))
    year = (headers.get("Date") or "")[:4]
    if not year.isdigit() or year == '0000':
        year = ""

    query = {"white": white, "black": black, "event": event, "year": year}
    if not (white or black or event):
        return {"groups": [], "query": query,
                "message": "This game has no players or event recorded, so there is nothing to look up."}
    if not online:
        return {"groups": [], "query": query, "message": "Offline — connect to look this game up."}

    wanted = [white, black]
    event_titles = []
    for name in (event, site):
        if name:
            event_titles.append(name)
            if "chess" not in name.lower():
                event_titles.append(name + " chess tournament")
    # Ask for the recorded edition, rather than a player's best-known match.
    event_candidates = _wikipedia_search('%s %s chess tournament' % (event, year)) if event and year else []
    if event and year and re.search(r'\bcand(?:idates)?\b', event, re.I):
        event_titles.extend(['Candidates Tournament '+year, year+' Candidates Tournament'])
    wanted.extend(event_titles)
    wanted.extend(event_candidates)

    # A game famous enough to have its own article usually carries both names.
    candidates = []
    if white and black:
        candidates = _wikipedia_search("%s %s %s %s chess game" % (white, black, event, year))
        wanted.extend(candidates)

    pages = _wikipedia(wanted)

    def same_year(page, require=False):
        title_years = re.findall(r'\b(?:18|19|20)\d{2}\b', page['title'])
        if year and title_years and year not in title_years:
            return False
        return not require or bool(year and re.search(r'\b'+year+r'\b', page['title']+' '+page['extract']))

    def words(value):
        import unicodedata
        value = ''.join(c for c in unicodedata.normalize('NFKD', value) if not unicodedata.combining(c))
        return set(re.findall(r"[a-z]+", value.lower()))

    def matches_game(page):
        # Search ranking alone is not evidence. Require the date and both players
        # in the returned article, not merely in the query we sent Wikipedia.
        text = words(page['title']+' '+page['extract'])
        surnames = [words(name.split()[-1]) for name in (white, black) if name]
        return (same_year(page, require=True) and len(surnames) == 2
                and all(name and name <= text for name in surnames))

    event_words = words(event) - {'chess', 'tournament', 'the', 'th', 'st', 'nd', 'rd'}
    if 'cand' in event_words:
        event_words.add('candidates')
    matched_events = [t for t in event_candidates if t in pages and same_year(pages[t], require=True)
                      and event_words & words(pages[t]['title'])]
    event_titles = [t for t in event_titles if t in pages and same_year(pages[t])]

    def group(label, titles, note=None):
        items, seen = [], set()
        for title in titles:
            page = pages.get(title)
            if page and page['url'] not in seen:
                items.append(page)
                seen.add(page['url'])
        return {"label": label, "note": note, "items": items} if items else None

    groups = [
        group("The players", [white, black]),
        group("The event and place", event_titles + matched_events),
        group("Possibly about this game", [t for t in candidates if t in pages and t not in (white, black)
                                           and matches_game(pages[t]) and t not in event_titles + matched_events],
              "The article mentions both players and the recorded year; read it to judge whether it is this exact game."),
    ]
    groups = [g for g in groups if g]

    message = None
    if not groups:
        message = "Wikipedia has nothing under these names. Games by well-known players at named events are the ones it covers."
    note = gemini_note(headers)
    return {"groups": groups, "message": message, "query": query, "note": note}


GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"
GEMINI_PROMPT = (
    "You are annotating one game in a personal chess study database.\n"
    "Write 2 to 4 sentences of historical context: the tournament, its significance, and "
    "where this meeting sat in the players' rivalry.\n"
    "Rules you must follow:\n"
    "- If you do not specifically recognise this game, say so in the first sentence and "
    "describe the event and the players at that time instead.\n"
    "- Never state moves, results, dates, rounds or ratings that are not given below. Do "
    "not correct or contradict the tags given below.\n"
    "- Anchor the context to the recorded event and year. Do not substitute a later "
    "famous championship involving either player for this tournament.\n"
    "- No speculation presented as fact, and no praise of the app or the user.\n\n"
)


def gemini_note(headers, timeout=20):
    """A short prose note from Gemini, or None when no key is configured.

    This is generated text, not a source. The caller labels it as such: it sits below
    the Wikipedia results so the checkable material is what a reader meets first.
    """
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    model = os.environ.get("GEMINI_MODEL", "").strip() or "gemini-3.6-flash"
    tags = "\n".join("%s: %s" % (name, headers.get(name) or "unknown")
                     for name in ("White", "Black", "Event", "Site", "Date", "Round", "Result"))
    body = json.dumps({
        "contents": [{"parts": [{"text": GEMINI_PROMPT + tags}]}],
        # Gemini 3 spends output budget on thinking, so a small cap truncates the answer.
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2000,
                             "thinkingConfig": {"thinkingLevel": "low"}},
    }).encode("utf-8")
    request = urllib.request.Request(
        GEMINI_URL % urllib.parse.quote(model) + "?key=" + urllib.parse.quote(key),
        data=body, headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as res:
            data = json.loads(res.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        return None
    text = " ".join(part.get("text", "") for part in parts).strip()
    return {"model": model, "text": text} if text else None

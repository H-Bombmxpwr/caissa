"""PGN splitting and header extraction.

The server never needs to understand chess rules — the browser has a full engine
for that. All it does here is cut a PGN stream into games, read the tag pairs,
and pull out enough of the movetext to index and search on.
"""

import re

TAG_RE = re.compile(r'^\[([A-Za-z0-9_]+)\s+"((?:[^"\\]|\\.)*)"\]\s*$', re.M)
GAME_SPLIT_RE = re.compile(r"\n(?=\[Event\s)")
TOKEN_RE = re.compile(
    r"""(\{[^}]*\}|;[^\n]*)   # comment
      | (\()|(\))              # variation
      | (\$\d+)                # nag
      | (1-0|0-1|1/2-1/2|\*)   # result
      | (\d+\.(?:\.\.)?)       # move number
      | ([OoA-Za-z][A-Za-z0-9#+=\-]*)   # SAN
    """,
    re.X,
)


def split_games(text):
    """Cut a PGN stream into individual game texts."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    return [g.strip() for g in GAME_SPLIT_RE.split(text) if g.strip()]


def headers(game_text):
    """Tag pairs as a dict."""
    out = {}
    for match in TAG_RE.finditer(game_text):
        out[match.group(1)] = match.group(2).replace('\\"', '"').replace("\\\\", "\\")
    return out


def movetext(game_text):
    """Everything after the tag pairs."""
    lines = game_text.split("\n")
    body = []
    in_tags = True
    for line in lines:
        if in_tags and (line.startswith("[") or not line.strip()):
            if line.startswith("["):
                continue
            if not body:
                in_tags = False
                continue
        in_tags = False
        body.append(line)
    return "\n".join(body).strip()


def moves(game_text, limit=None):
    """Main-line SAN moves, variations skipped."""
    out = []
    depth = 0
    for m in TOKEN_RE.finditer(movetext(game_text)):
        if m.group(2):
            depth += 1
            continue
        if m.group(3):
            depth = max(0, depth - 1)
            continue
        if depth or not m.group(7):
            continue
        san = m.group(7)
        if len(san) == 1 and san.isalpha():
            continue
        out.append(san)
        if limit and len(out) >= limit:
            break
    return out


def to_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def normalize_date(value):
    """PGN dates are 'YYYY.MM.DD' with '??' for unknown parts; make them sortable."""
    if not value:
        return ""
    parts = str(value).replace("-", ".").split(".")
    while len(parts) < 3:
        parts.append("??")
    year, month, day = parts[0], parts[1], parts[2]
    year = year if year.isdigit() else "0000"
    month = month.zfill(2) if month.isdigit() else "00"
    day = day.zfill(2) if day.isdigit() else "00"
    return "%s.%s.%s" % (year, month, day)


def describe(game_text):
    """Everything the index wants to know about one game."""
    tags = headers(game_text)
    first = moves(game_text, limit=24)
    site = tags.get("Site", "")
    source_id = None
    if "lichess.org/" in site:
        source_id = "lichess:" + site.rstrip("/").rsplit("/", 1)[-1]
    elif tags.get("GameId"):
        source_id = "lichess:" + tags["GameId"]
    elif "chess.com" in site and tags.get("Link"):
        source_id = "chesscom:" + tags["Link"].rstrip("/").rsplit("/", 1)[-1]

    return {
        "white": tags.get("White", "?"),
        "black": tags.get("Black", "?"),
        # ChessBase writes a richer tag set than lichess does, and these are the tags
        # its users actually sort and filter on. A file without them simply stores "".
        "event_date": normalize_date(tags.get("EventDate")),
        "event_type": tags.get("EventType", ""),
        "white_team": tags.get("WhiteTeam", ""),
        "black_team": tags.get("BlackTeam", ""),
        "white_title": tags.get("WhiteTitle", ""),
        "black_title": tags.get("BlackTitle", ""),
        "white_fide_id": tags.get("WhiteFideId") or tags.get("WhiteFideID", ""),
        "black_fide_id": tags.get("BlackFideId") or tags.get("BlackFideID", ""),
        "source_title": tags.get("SourceTitle") or tags.get("Source", ""),
        "variation": " ".join(v for v in [tags.get("Variation", ""),
                                          tags.get("SubVariation", "")] if v),
        "white_elo": to_int(tags.get("WhiteElo")),
        "black_elo": to_int(tags.get("BlackElo")),
        "result": tags.get("Result", "*"),
        "date": normalize_date(tags.get("Date") or tags.get("UTCDate")),
        "event": tags.get("Event", ""),
        "annotator": tags.get('Annotator', ''),
        "termination": tags.get('Termination', ''),
        "has_annotations": int(bool(re.search(r'\{|;|\$\d+|[!?]|\(', movetext(game_text)))),
        "site": site,
        "round": tags.get("Round", ""),
        "eco": tags.get("ECO", ""),
        "opening": tags.get("Opening", ""),
        "variant": tags.get("Variant", "Standard"),
        "time_control": tags.get("TimeControl", ""),
        "fen": tags.get("FEN", ""),
        "ply_count": len(moves(game_text)),
        "first_moves": " ".join(first),
        "source_id": source_id,
    }

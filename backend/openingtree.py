"""Your openings, judged by how they actually went.

A reference database answers "what do strong players play here". This answers a
different and more useful question: *when you played this, what happened to you*.
Every number here is from the chosen player's side of the board, so a 38% score is
38% for them, not for White.

It reads the position index, so a collection has to be indexed before it has
anything to say. Two things fall out of that design:

* **Transpositions come for free.** Positions are stored under a transposition key,
  so a line reached by a different move order is the same node.
* **Depth costs nothing at query time.** The index already holds every position of
  every game, so walking twenty moves deep is the same query as walking one.

The weakest-line scan is the part worth explaining. Ranking by score alone surfaces
a 0% line played twice; ranking by volume surfaces your main line, which is fine.
What a reader wants is where the points actually went, so lines are ranked by
*points dropped* — games multiplied by the shortfall against an even score — and a
line has to clear a minimum number of games before it is listed at all.
"""

from .chess import Chess
from . import pgnutil

MAX_SCAN_PLY = 24                  # twelve moves; deeper than this is not an opening
DEFAULT_MIN_GAMES = 3


class Filters:
    """The set of games a report is about, and the SQL to select them."""

    def __init__(self, player=None, color=None, collection=None, speed=None,
                 since=None, until=None, min_opponent_elo=None, max_opponent_elo=None,
                 rated=None, kind=None):
        self.player = (player or "").strip()
        self.color = color if color in ("w", "b") else None
        self.collection = collection
        self.speed = (speed or "").strip()
        self.since = (since or "").strip()
        self.until = (until or "").strip()
        self.min_opponent_elo = min_opponent_elo
        self.max_opponent_elo = max_opponent_elo
        self.rated = rated
        self.kind = kind

    @property
    def perspective(self):
        return "player" if self.player else "white"

    def side_sql(self):
        """An expression naming the side the report is written from, and its params."""
        if not self.player:
            return "'w'", []
        like = "%" + self.player + "%"
        return ("CASE WHEN g.white LIKE ? THEN 'w' WHEN g.black LIKE ? THEN 'b' END",
                [like, like])

    def opponent_elo_sql(self):
        if not self.player:
            return "g.black_elo", []
        like = "%" + self.player + "%"
        return ("CASE WHEN g.white LIKE ? THEN g.black_elo ELSE g.white_elo END", [like])

    def where(self):
        """Clauses and params common to every query in this module."""
        clauses, params = ["p.next_san IS NOT NULL"], []
        if self.player:
            like = "%" + self.player + "%"
            if self.color == "w":
                clauses.append("g.white LIKE ?")
                params.append(like)
            elif self.color == "b":
                clauses.append("g.black LIKE ?")
                params.append(like)
            else:
                clauses.append("(g.white LIKE ? OR g.black LIKE ?)")
                params.extend([like, like])
        if self.collection:
            clauses.append("(g.collection_id = ? OR g.id IN "
                           "(SELECT game_id FROM game_collections WHERE collection_id = ?))")
            params.extend([int(self.collection), int(self.collection)])
        if self.kind:
            clauses.append("g.collection_id IN (SELECT id FROM collections WHERE kind = ?)")
            params.append(self.kind)
        if self.speed:
            marks = ",".join("?" * len(self.speed.split(",")))
            clauses.append("g.speed IN (" + marks + ")")
            params.extend(s.strip() for s in self.speed.split(","))
        if self.rated in (0, 1, "0", "1"):
            clauses.append("COALESCE(g.rated, 0) = ?")
            params.append(int(self.rated))
        for value, operator in ((self.since, ">="), (self.until, "<=")):
            if value:
                clauses.append("g.date " + operator + " ?")
                params.append(_as_pgn_date(value, end=operator == "<="))
        opponent, opponent_params = self.opponent_elo_sql()
        for value, operator in ((self.min_opponent_elo, ">="), (self.max_opponent_elo, "<=")):
            if value not in (None, ""):
                clauses.append("(" + opponent + ") " + operator + " ?")
                params.extend(opponent_params + [int(value)])
        return " AND ".join(clauses), params


def _as_pgn_date(value, end=False):
    """Accept 2021, 2021-06 or 2021-06-15 and return a comparable PGN date."""
    parts = str(value).replace("/", "-").split("-")
    year = parts[0].zfill(4)
    month = parts[1].zfill(2) if len(parts) > 1 else ("12" if end else "01")
    day = parts[2].zfill(2) if len(parts) > 2 else ("31" if end else "01")
    return "%s.%s.%s" % (year, month, day)


# The score of one game from the report's side. Everything else is built on this.
SCORE_SQL = ("CASE WHEN result='1/2-1/2' THEN 0.5 "
             "WHEN side='w' AND result='1-0' THEN 1.0 "
             "WHEN side='b' AND result='0-1' THEN 1.0 "
             "WHEN result IN ('1-0','0-1') THEN 0.0 END")


def _rows_sql(filters, extra_clause="", extra_params=()):
    """One row per (game, continuation), carrying the side, the score and the opponent.

    This is the inner query everything else groups over. Aggregation happens in SQL
    rather than in Python because a collection can be enormous: the opening position
    of a hundred-thousand-game database is a hundred thousand rows, and nobody should
    wait for those to cross into Python to be counted.
    """
    side, side_params = filters.side_sql()
    opponent, opponent_params = filters.opponent_elo_sql()
    where, where_params = filters.where()
    clause = where + ((" AND " + extra_clause) if extra_clause else "")
    sql = ("SELECT DISTINCT p.game_id, p.hash, p.ply, p.next_san, g.result, g.date, "
           + side + " AS side, (" + opponent + ") AS opponent_elo "
           "FROM positions p JOIN games g ON g.id = p.game_id WHERE " + clause)
    return sql, side_params + opponent_params + where_params + list(extra_params)


# Only decided games by a player who is actually in them can be scored.
COUNTABLE = "side IS NOT NULL AND result IN ('1-0','0-1','1/2-1/2')"

TALLY_SQL = ("COUNT(*) AS games, "
             "SUM(CASE WHEN score = 1.0 THEN 1 ELSE 0 END) AS wins, "
             "SUM(CASE WHEN score = 0.5 THEN 1 ELSE 0 END) AS draws, "
             "SUM(CASE WHEN score = 0.0 THEN 1 ELSE 0 END) AS losses, "
             "AVG(score) AS score, AVG(opponent_elo) AS opponent_elo")


def _scored(inner):
    """Wrap the row query so each row carries its score."""
    return "SELECT *, " + SCORE_SQL + " AS score FROM (" + inner + ")"


def _tally_row(row):
    return {
        "games": row["games"] or 0,
        "wins": row["wins"] or 0,
        "draws": row["draws"] or 0,
        "losses": row["losses"] or 0,
        "score_pct": round(100.0 * row["score"], 1) if row["score"] is not None else None,
        "avg_opponent_elo": round(row["opponent_elo"]) if row["opponent_elo"] else None,
    }


def _tally(rows):
    """The same tally over rows already in memory. Used by the trend helper."""
    wins = draws = losses = 0
    elos = []
    for row in rows:
        side, result = row["side"], row["result"]
        if side is None:
            continue
        if result == "1/2-1/2":
            draws += 1
        elif result == "1-0":
            wins, losses = (wins + 1, losses) if side == "w" else (wins, losses + 1)
        elif result == "0-1":
            wins, losses = (wins + 1, losses) if side == "b" else (wins, losses + 1)
        else:
            continue
        if row["opponent_elo"]:
            elos.append(row["opponent_elo"])
    games = wins + draws + losses
    return {
        "games": games, "wins": wins, "draws": draws, "losses": losses,
        "score_pct": round(100.0 * (wins + 0.5 * draws) / games, 1) if games else None,
        "avg_opponent_elo": round(sum(elos) / len(elos)) if elos else None,
    }


def position(library, fen, filters):
    """What happened from this position, move by move, from the report's side."""
    key = Chess(fen).key()
    inner, params = _rows_sql(filters, "p.hash = ?", [key])
    scored = _scored(inner)
    db = library.connect()

    # Totals count games, not continuations: a game that repeats a position still
    # reached it once.
    totals = _tally_row(db.execute(
        "SELECT " + TALLY_SQL + " FROM (SELECT game_id, side, result, score, opponent_elo "
        "FROM (" + scored + ") WHERE " + COUNTABLE + " GROUP BY game_id)", params).fetchone())

    moves = []
    for row in db.execute(
            "SELECT next_san AS san, MAX(date) AS last_played, " + TALLY_SQL +
            " FROM (" + scored + ") WHERE " + COUNTABLE +
            " GROUP BY next_san ORDER BY games DESC, san", params):
        entry = _tally_row(row)
        entry["san"] = row["san"]
        entry["last_played"] = row["last_played"]
        entry["share_pct"] = (round(100.0 * entry["games"] / totals["games"], 1)
                              if totals["games"] else 0)
        moves.append(entry)

    trend = []
    for row in db.execute(
            "SELECT substr(date,1,4) AS period, " + TALLY_SQL +
            " FROM (SELECT game_id, date, side, result, score, opponent_elo FROM (" + scored + ")"
            "  WHERE " + COUNTABLE + " GROUP BY game_id)"
            " WHERE period GLOB '[0-9][0-9][0-9][0-9]' AND period <> '0000'"
            " GROUP BY period ORDER BY period", params):
        entry = _tally_row(row)
        entry["period"] = row["period"]
        trend.append(entry)

    return {
        "fen": fen, "hash": key,
        "player": filters.player or None,
        "perspective": filters.perspective,
        "color": filters.color,
        "totals": totals,
        "moves": moves,
        "trend": trend[-12:],
    }


def trend(rows, buckets=None):
    """Score by year over rows already read. Kept for callers working in memory."""
    by_year = {}
    for row in rows:
        if row["side"] is None or not row["date"]:
            continue
        year = str(row["date"])[:4]
        if not year.isdigit() or year == "0000":
            continue
        by_year.setdefault(year, []).append(row)
    out = []
    for year in sorted(by_year):
        entry = _tally(by_year[year])
        if entry["games"]:
            out.append({"period": year, **entry})
    return out[-(buckets or 12):]


def weakest(library, filters, min_games=DEFAULT_MIN_GAMES, limit=15, max_ply=MAX_SCAN_PLY):
    """The lines that cost the most points, ranked by points dropped rather than by score.

    A single 0% game is noise; twelve games at 25% is a hole in the repertoire. Each
    entry names the line by replaying the game that reached it, so the answer reads as
    moves rather than as a hash.
    """
    inner, params = _rows_sql(filters, "p.ply <= ?", [int(max_ply)])
    # More candidates than asked for, because collapsing chains below discards most
    # of them: every position along a losing line scores the same and is one entry.
    rows = library.connect().execute(
        "SELECT hash, next_san AS san, MIN(game_id) AS game_id, MIN(ply) AS ply, " + TALLY_SQL +
        ", COUNT(*) * (0.5 - AVG(score)) AS dropped"
        " FROM (" + _scored(inner) + ") WHERE " + COUNTABLE +
        " GROUP BY hash, next_san"
        " HAVING games >= ? AND dropped > 0"
        " ORDER BY dropped DESC, games DESC LIMIT ?",
        params + [int(min_games), int(limit) * 8]).fetchall()

    lines = {}
    candidates = []
    for row in rows:
        entry = _tally_row(row)
        entry.update(san=row["san"], hash=row["hash"], ply=row["ply"], game_id=row["game_id"],
                     points_dropped=round(row["dropped"], 2))
        entry.update(_line_to(library, row["game_id"], row["ply"], row["san"], lines))
        candidates.append(entry)

    return _collapse(candidates)[:limit]


def _extends(longer, shorter):
    return len(longer) > len(shorter) and longer[:len(shorter)] == shorter


def _collapse(entries):
    """Reduce a ranked list of nodes to the lines actually worth reading.

    Two kinds of entry say nothing of their own:

    * **Pass-through nodes.** Every position along a line that lost seven games
      reports those same seven games, so an uncollapsed list is one answer printed
      five times at increasing depth. Only the deepest of such a chain is kept,
      because that is the one that names the line rather than gesturing at it.
    * **Pure aggregates.** "1.e4 cost you 3.5 points" is just its children added up.
      A node is dropped when the lines kept beneath it account for all of its games;
      if some of its games are not explained further down, it stays.
    """
    kept = []
    for entry in sorted(entries, key=lambda e: -len(e.get("moves") or [])):
        moves = entry.get("moves") or []
        if any(other["games"] == entry["games"] and _extends(other.get("moves") or [], moves)
               for other in kept):
            continue                                  # a deeper node already says this
        kept.append(entry)

    final = []
    for entry in kept:
        moves = entry.get("moves") or []
        below = [other for other in kept if _extends(other.get("moves") or [], moves)]
        # Only the nearest descendants count, or a chain would be added up twice.
        nearest = [b for b in below
                   if not any(_extends(b.get("moves") or [], c.get("moves") or []) for c in below)]
        if nearest and sum(b["games"] for b in nearest) >= entry["games"]:
            continue                                  # nothing here the lines below do not say
        final.append(entry)

    final.sort(key=lambda e: (-e["points_dropped"], -e["games"]))
    return final


def _line_to(library, game_id, ply, san, cache=None):
    """The moves that reach a node, read back out of the game that got there.

    Returns the moves themselves as well as the numbered text, so the interface can
    put the line on a board rather than only print it. `cache` keeps one game's moves
    across the many nodes that game reached.
    """
    if cache is not None and game_id in cache:
        played = cache[game_id]
    else:
        text = library.game_pgn(game_id)
        played = pgnutil.moves(text) if text else None
        if cache is not None:
            cache[game_id] = played
    if played is None:
        return {"line": None, "moves": []}
    moves = played[:int(ply)] + [san]
    numbered = []
    for index, move in enumerate(moves):
        numbered.append(("%d.%s" % (index // 2 + 1, move)) if index % 2 == 0 else move)
    return {"line": " ".join(numbered), "moves": moves}


def players(library, collection=None, limit=40):
    """Who appears most often in a collection, so the report can be pointed at someone."""
    clauses, params = [], []
    if collection:
        clauses.append("(collection_id = ? OR id IN "
                       "(SELECT game_id FROM game_collections WHERE collection_id = ?))")
        params.extend([int(collection), int(collection)])
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = library.connect().execute(
        "SELECT name, COUNT(*) AS games FROM ("
        "  SELECT white AS name FROM games" + where +
        "  UNION ALL SELECT black AS name FROM games" + where +
        ") WHERE name IS NOT NULL AND name <> '' AND name <> '?' "
        "GROUP BY name ORDER BY games DESC, name LIMIT ?",
        params + params + [int(limit)]).fetchall()
    return [dict(r) for r in rows]

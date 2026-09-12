"""Turn an opening PGN — a lichess study export, or anything with variations — into
repertoire lines.

A lichess repertoire study is a tree: one main line with alternatives branching off
it, often many levels deep. The repertoire trainer stores flat lines instead, so
this walks the tree and writes down every root-to-leaf path through it.

Two decisions are worth stating plainly. A line is trimmed so it ends on a move by
the side the repertoire is for: finishing a drill on the opponent's reply teaches
nothing. And a line that is only the opening part of a longer line is dropped,
because drilling it would be drilling the same moves twice.
"""

from . import pgnutil
from .chess import Chess

MAX_PLIES = 40                      # twenty moves is already deep preparation
MAX_LINES = 5000                    # a guard against a study that fans out forever


def _walk(game_text, start_fen, max_plies):
    """Every root-to-leaf path through one game's move tree, as SAN lists.

    Raises ValueError through Chess if the movetext does not describe legal chess;
    the caller decides whether one bad chapter should fail the whole import.
    """
    lines = []
    board = Chess(start_fen)
    line = []
    before = (board.fen(), [])          # the position before the most recent move
    stack = []                          # where a ')' returns to
    truncated = False

    for token in pgnutil.TOKEN_RE.finditer(pgnutil.movetext(game_text)):
        if token.group(2):                                  # '(' — an alternative
            stack.append((board.fen(), list(line), before))
            board, line = Chess(before[0]), list(before[1])
            continue
        if token.group(3):                                  # ')' — that branch ends
            if line:
                lines.append(list(line))
            if not stack:
                break
            fen, line, before = stack.pop()
            board = Chess(fen)
            continue
        if token.group(5):                                  # a result ends the game
            break
        san = token.group(7)
        if not san or (len(san) == 1 and san.isalpha()):
            continue
        if len(line) >= max_plies:
            truncated = True
            continue
        before = (board.fen(), list(line))
        board.move(san)                                     # ValueError if illegal
        line.append(san)
        if len(lines) + len(stack) > MAX_LINES:
            truncated = True
            break

    if line:
        lines.append(line)
    return lines, truncated


def _trim_to_owner(line, owner_is_white, white_moves_first):
    """Drop trailing opponent moves so the line ends on a move you have to find."""
    while line:
        ply_is_white = (len(line) - 1) % 2 == 0 if white_moves_first else (len(line) - 1) % 2 == 1
        if ply_is_white == owner_is_white:
            return line
        line = line[:-1]
    return line


def from_pgn(pgn_text, color="w", max_plies=MAX_PLIES):
    """Repertoire lines for one side, plus a report on what was read and skipped."""
    color = "b" if str(color).lower().startswith("b") else "w"
    games = pgnutil.split_games(pgn_text)
    if not games:
        raise ValueError("That file holds no PGN games.")

    out = []
    seen = set()
    chapters, skipped, truncated = 0, 0, False
    for game_text in games:
        headers = pgnutil.headers(game_text)
        start_fen = headers.get("FEN") or Chess().fen()
        try:
            Chess(start_fen)
            paths, cut = _walk(game_text, start_fen, max_plies)
        except (ValueError, KeyError, IndexError):
            skipped += 1                                    # a chapter we cannot replay
            continue
        truncated = truncated or cut
        chapters += 1
        white_first = start_fen.split()[1] == "w"
        for path in paths:
            path = _trim_to_owner(path, color == "w", white_first)
            if not path:
                continue
            key = (start_fen, " ".join(path))
            if key in seen:
                continue
            seen.add(key)
            out.append({"moves": path, "fen": start_fen})

    # A line that is merely the start of a longer one is already covered by it.
    by_start = {}
    for entry in out:
        by_start.setdefault(entry["fen"], []).append(entry)
    kept = []
    for fen, entries in by_start.items():
        entries.sort(key=lambda e: len(e["moves"]), reverse=True)
        longest = []
        for entry in entries:
            prefix = entry["moves"]
            if any(other[:len(prefix)] == prefix for other in longest):
                continue
            longest.append(prefix)
            kept.append(entry)
    kept.sort(key=lambda e: (len(e["moves"]), e["moves"]))

    lines = [{"moves": e["moves"], "fen": e["fen"], "due": 0, "interval": 0, "successes": 0}
             for e in kept[:MAX_LINES]]
    return {"lines": lines, "chapters": chapters, "skipped": skipped,
            "truncated": truncated or len(kept) > MAX_LINES}


def merge(existing, incoming):
    """Add only the lines a repertoire does not already hold, keeping review history."""
    known = {(line.get("fen"), " ".join(line.get("moves") or [])) for line in existing}
    added = [line for line in incoming if (line["fen"], " ".join(line["moves"])) not in known]
    return existing + added, len(added)

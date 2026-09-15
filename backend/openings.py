"""Name the opening a game actually played.

An ECO code on its own is not an opening name, and it is not even unique: E87 covers
three different Saemisch variations. The index built by tools/fetch_openings.py keys
lichess's CC0 opening data on the position after each line's moves, so a game is named
as precisely as its moves allow and still lands correctly when it transposes.
"""
import json
import os

from .chess import Chess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_PATH = os.path.join(ROOT, "data", "openings.eco.json")
MAX_PLIES = 36                       # the deepest line the data set carries

_index = None


def index():
    """The position index, loaded once. A missing file just means no naming."""
    global _index
    if _index is None:
        try:
            with open(INDEX_PATH, encoding="utf-8") as handle:
                _index = json.load(handle)
        except (OSError, ValueError):
            _index = {}
    return _index


def classify(sans, start_fen=None, depth=MAX_PLIES):
    """The most specific named opening these moves reach, or None.

    `sans` is the game's moves in order. Deeper matches win, so a game that continues
    into a named variation is named for the variation rather than its parent line.
    """
    table = index()
    if not table or not sans:
        return None
    try:
        game = Chess(start_fen) if start_fen else Chess()
    except (ValueError, KeyError, IndexError):
        return None
    best = None
    for san in sans[:depth]:
        if not game.move(san):
            break
        found = table.get(game.key())
        if found and (best is None or found[2] >= best[2]):
            best = found
    return {"eco": best[0], "opening": best[1]} if best else None


def progression(sans, start_fen=None, depth=MAX_PLIES):
    """Each point along `sans` where the opening's name changes.

    `classify` answers "what is this line called" for a finished game. A drill needs the
    answer at every stage, because the name the player is standing in changes as the line
    is played. Returning only the plies where it changes keeps the list short and lets the
    caller name any position by taking the last entry at or before its ply.
    """
    table = index()
    if not table or not sans:
        return []
    try:
        game = Chess(start_fen) if start_fen else Chess()
    except (ValueError, KeyError, IndexError):
        return []
    found, best = [], None
    for ply, san in enumerate(sans[:depth], 1):
        try:                       # a caller-supplied line stops at its first bad move
            if not game.move(san):
                break
        except (ValueError, KeyError, IndexError):
            break
        named = table.get(game.key())
        if named and (best is None or named[2] >= best[2]):
            best = named
            if found and found[-1]["opening"] == named[1]:
                continue           # two positions, one name: the player learns nothing new
            found.append({"ply": ply, "eco": named[0], "opening": named[1]})
    return found


def name_for(meta, sans):
    """What a game's ECO and Opening tags should say, without overwriting the file's own.

    A PGN that already names its opening is left alone; the common case this fixes is a
    file carrying only an ECO code, which the database would otherwise show as nothing
    more specific than the volume it belongs to.
    """
    if meta.get("opening"):
        return None
    if meta.get("fen"):                # a game set up from a position has no opening line
        return None
    found = classify(sans)
    if not found:
        return None
    return {"eco": meta.get("eco") or found["eco"], "opening": found["opening"]}

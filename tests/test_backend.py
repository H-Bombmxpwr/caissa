"""Backend tests: PGN indexing, the library, and the API dispatch.

    py -m unittest discover -s tests -p "test_*.py"

Nothing here touches the network.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import pgnutil                      # noqa: E402
from backend.api import Api, ApiError            # noqa: E402
from backend.store import Library, slugify       # noqa: E402

GAME_ONE = """[Event "Rated blitz game"]
[Site "https://lichess.org/abcd1234"]
[Date "2026.01.04"]
[White "testplayer"]
[Black "opponent1"]
[Result "1-0"]
[WhiteElo "1620"]
[BlackElo "1605"]
[ECO "C50"]
[Opening "Italian Game: Giuoco Pianissimo"]

1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 (3... Nf6 4. d3) 4. c3 {solid} Nf6 1-0"""

GAME_TWO = """[Event "Casual game"]
[Site "https://lichess.org/efgh5678"]
[Date "2026.02.10"]
[White "opponent2"]
[Black "testplayer"]
[Result "0-1"]
[ECO "B01"]
[Opening "Scandinavian Defense"]

1. e4 d5 2. exd5 Qxd5 3. Nc3 Qa5 0-1"""

TWO_GAMES = GAME_ONE + "\n\n" + GAME_TWO


class PgnUtilTests(unittest.TestCase):
    def test_split(self):
        self.assertEqual(len(pgnutil.split_games(TWO_GAMES)), 2)
        self.assertEqual(len(pgnutil.split_games("")), 0)

    def test_headers(self):
        tags = pgnutil.headers(GAME_ONE)
        self.assertEqual(tags["White"], "testplayer")
        self.assertEqual(tags["ECO"], "C50")

    def test_mainline_skips_variations_and_comments(self):
        moves = pgnutil.moves(GAME_ONE)
        self.assertEqual(moves[:4], ["e4", "e5", "Nf3", "Nc6"])
        self.assertNotIn("d3", moves)          # that move lives in a variation
        self.assertEqual(len(moves), 8)

    def test_describe(self):
        meta = pgnutil.describe(GAME_ONE)
        self.assertEqual(meta["source_id"], "lichess:abcd1234")
        self.assertEqual(meta["white_elo"], 1620)
        self.assertEqual(meta["date"], "2026.01.04")
        self.assertEqual(meta["ply_count"], 8)
        self.assertTrue(meta["first_moves"].startswith("e4 e5 Nf3"))

    def test_date_normalising(self):
        self.assertEqual(pgnutil.normalize_date("2026.1.4"), "2026.01.04")
        self.assertEqual(pgnutil.normalize_date("2026.??.??"), "2026.00.00")
        self.assertEqual(pgnutil.normalize_date(""), "")

    def test_slugify(self):
        self.assertEqual(slugify("My Games!"), "my-games")
        self.assertEqual(slugify("  Kasparov / Karpov  "), "kasparov-karpov")
        self.assertEqual(slugify("!!!"), "collection")
        self.assertEqual(slugify(""), "collection")


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="chesslib-test-")
        self.lib = Library(self.dir)

    def tearDown(self):
        self.lib.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_import_and_read_back(self):
        result = self.lib.add_games(TWO_GAMES, collection="My games")
        self.assertEqual(result["added"], 2)

        found = self.lib.search()
        self.assertEqual(found["total"], 2)

        newest = found["games"][0]
        self.assertEqual(newest["white"], "opponent2")          # sorted by date desc

        pgn = self.lib.game_pgn(newest["id"])
        self.assertIn("[Site ", pgn)
        self.assertIn("Qa5", pgn)
        self.assertNotIn("Giuoco", pgn)                         # exactly one game came back

    def test_games_are_real_files_on_disk(self):
        self.lib.add_games(TWO_GAMES, collection="My games")
        path = os.path.join(self.dir, "collections", "my-games", "games.pgn")
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        self.assertEqual(len(pgnutil.split_games(text)), 2)

    def test_duplicates_are_skipped(self):
        self.lib.add_games(TWO_GAMES)
        again = self.lib.add_games(TWO_GAMES)
        self.assertEqual(again["added"], 0)
        self.assertEqual(again["duplicates"], 2)
        self.assertEqual(self.lib.search()["total"], 2)

    def test_search_filters(self):
        self.lib.add_games(TWO_GAMES)
        self.assertEqual(self.lib.search(player="testplayer")["total"], 2)
        self.assertEqual(self.lib.search(white="testplayer")["total"], 1)
        self.assertEqual(self.lib.search(eco="C5")["total"], 1)
        self.assertEqual(self.lib.search(result="0-1")["total"], 1)
        self.assertEqual(self.lib.search(year=2026)["total"], 2)
        self.assertEqual(self.lib.search(query="Scandinavian")["total"], 1)
        self.assertEqual(self.lib.search(min_elo=1600)["total"], 1)

    def test_collections_are_separate(self):
        self.lib.add_games(GAME_ONE, collection="Mine")
        self.lib.add_games(GAME_TWO, collection="Masters")
        self.assertEqual(self.lib.search(collection="Mine")["total"], 1)
        self.assertEqual(self.lib.search(collection="Masters")["total"], 1)
        names = [c["name"] for c in self.lib.collections()]
        self.assertIn("Mine", names)
        self.assertIn("Masters", names)

    def test_delete_and_replace(self):
        self.lib.add_games(TWO_GAMES)
        game_id = self.lib.search()["games"][0]["id"]
        annotated = GAME_TWO.replace("0-1", "0-1").replace("3. Nc3", "3. Nc3 {my note}")
        self.assertTrue(self.lib.replace_game(game_id, annotated))
        self.assertIn("my note", self.lib.game_pgn(game_id))
        self.assertTrue(self.lib.delete_game(game_id))
        self.assertEqual(self.lib.search()["total"], 1)

    def test_repertoires_and_settings(self):
        rep_id = self.lib.save_repertoire("White e4", "w", '{"moves": ["e4"]}')
        self.assertEqual(len(self.lib.repertoires()), 1)
        self.lib.save_repertoire("White e4 v2", "w", '{"moves": ["e4", "d4"]}', rep_id)
        self.assertEqual(self.lib.repertoire(rep_id)["name"], "White e4 v2")
        self.assertTrue(self.lib.delete_repertoire(rep_id))

        self.assertIsNone(self.lib.setting("nope"))
        self.lib.setting("lichess_token", "abc")
        self.assertEqual(self.lib.setting("lichess_token"), "abc")

    def test_stats(self):
        self.lib.add_games(TWO_GAMES)
        stats = self.lib.stats()
        self.assertEqual(stats["games"], 2)
        # The rankings cost two rows a game to compute, so they are opt-in and the
        # page that does not show them does not pay for them.
        self.assertNotIn("top_players", stats)
        full = self.lib.stats(full=True)
        self.assertTrue(any(p["name"] == "testplayer" and p["n"] == 2 for p in full["top_players"]))


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="chessapi-test-")
        self.api = Api(self.dir)

    def tearDown(self):
        self.api.library.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def call(self, method, path, query=None, body=None):
        return self.api.handle(method, path, query or {}, body)

    def test_health_and_stats(self):
        status, payload = self.call("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        status, payload = self.call("GET", "/api/stats")
        self.assertEqual(payload["games"], 0)

    def test_import_list_fetch_delete(self):
        status, payload = self.call("POST", "/api/games", body={"pgn": TWO_GAMES, "collection": "Mine"})
        self.assertEqual(payload["added"], 2)

        status, payload = self.call("GET", "/api/games", query={"collection": "Mine"})
        self.assertEqual(payload["total"], 2)
        game_id = payload["games"][0]["id"]

        status, payload = self.call("GET", "/api/games/%d" % game_id)
        self.assertIn("pgn", payload["game"])

        status, payload = self.call("PUT", "/api/games/%d" % game_id, body={"pgn": GAME_ONE})
        self.assertTrue(payload["saved"])

        status, payload = self.call("DELETE", "/api/games/%d" % game_id)
        self.assertTrue(payload["deleted"])
        status, payload = self.call("GET", "/api/games")
        self.assertEqual(payload["total"], 1)

    def test_collection_export(self):
        self.call("POST", "/api/games", body={"pgn": TWO_GAMES, "collection": "Mine"})
        status, payload = self.call("GET", "/api/collections/Mine/pgn")
        self.assertEqual(status, 200)
        data, ctype = payload
        self.assertEqual(ctype, "application/x-chess-pgn")
        self.assertEqual(len(pgnutil.split_games(data.decode("utf-8"))), 2)

    def test_errors(self):
        with self.assertRaises(ApiError):
            self.call("GET", "/api/nope")
        with self.assertRaises(ApiError):
            self.call("POST", "/api/games", body={"pgn": "   "})
        with self.assertRaises(ApiError):
            self.call("GET", "/api/games/9999")
        with self.assertRaises(ApiError):
            self.call("POST", "/api/import/lichess", body={"user": ""})

    def test_repertoire_roundtrip(self):
        status, payload = self.call("POST", "/api/repertoires",
                                    body={"name": "My e4", "color": "w", "data": {"moves": ["e4"]}})
        rep_id = payload["id"]
        status, payload = self.call("GET", "/api/repertoires")
        self.assertEqual(len(payload["repertoires"]), 1)
        status, payload = self.call("GET", "/api/repertoires/%d" % rep_id)
        self.assertIn("moves", payload["repertoire"]["data"])
        status, payload = self.call("DELETE", "/api/repertoires/%d" % rep_id)
        self.assertTrue(payload["deleted"])

    def test_masters_status_without_network(self):
        status, payload = self.call("GET", "/api/masters/status")
        self.assertFalse(payload["running"])


if __name__ == "__main__":
    unittest.main()

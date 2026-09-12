"""Every API route the desktop workspace calls, exercised without a browser.

    py -m unittest tests.test_workspace

Network-dependent routes are checked for shape and error handling only.
"""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import literature                      # noqa: E402
from backend.api import Api, ApiError               # noqa: E402
from backend.chess import Chess                     # noqa: E402

GAMES = """[Event "Rated blitz game"]
[Site "https://lichess.org/abcd1234"]
[Date "2026.01.04"]
[White "testplayer"]
[Black "opponent1"]
[Result "1-0"]
[ECO "C50"]
[Opening "Italian Game: Giuoco Pianissimo"]

1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. c3 Nf6 1-0

[Event "Casual game"]
[Site "https://lichess.org/efgh5678"]
[Date "1926.02.10"]
[White "opponent2"]
[Black "testplayer"]
[Result "0-1"]
[ECO "B01"]
[Opening "Scandinavian Defense"]

1. e4 d5 2. exd5 Qxd5 3. Nc3 Qa5 0-1"""


class WorkspaceApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="caissa-workspace-")
        cls.api = Api(cls.dir)
        cls.api.handle("POST", "/api/games", {}, {"pgn": GAMES, "collection": "My games"})

    @classmethod
    def tearDownClass(cls):
        cls.api.library.close()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def call(self, method, path, query=None, body=None):
        return self.api.handle(method, path, query or {}, body)

    def game_ids(self):
        return [g["id"] for g in self.call("GET", "/api/games")[1]["games"]]

    # ---------- the calls the workspace makes on load ----------

    def test_boot_sequence(self):
        """What workspace.js fetches before it can draw anything."""
        for path in ("/api/health", "/api/collections", "/api/study/folders", "/api/stats"):
            status, payload = self.call("GET", path)
            self.assertEqual(status, 200, path)
            self.assertIsInstance(payload, dict, path)
        status, payload = self.call("GET", "/api/study/folders")
        self.assertIn("folders", payload)
        self.assertIn("assignments", payload)
        self.assertIn("root", payload)

    def test_appearance_settings_roundtrip(self):
        prefs = json.dumps({"theme": "Sage", "pieces": "cburnett"})
        self.call("PUT", "/api/settings/appearance", body={"value": prefs})
        status, payload = self.call("GET", "/api/settings/appearance")
        self.assertEqual(json.loads(payload["value"])["theme"], "Sage")

    # ---------- database and analysis ----------

    def test_game_listing_and_opening(self):
        status, payload = self.call("GET", "/api/games", query={"limit": "30", "offset": "0"})
        self.assertEqual(payload["total"], 2)
        game_id = payload["games"][0]["id"]
        status, payload = self.call("GET", "/api/games/%d" % game_id)
        self.assertIn("[Event ", payload["game"]["pgn"])

    def test_annotating_a_game_keeps_identity(self):
        """Saving annotations must not collide with another game's source id."""
        first, second = self.game_ids()[0], self.game_ids()[1]
        original = self.call("GET", "/api/games/%d" % second)[1]["game"]["pgn"]
        annotated = original.replace("1. e4", "1. e4 {my note}")
        status, payload = self.call("PUT", "/api/games/%d" % second, body={"pgn": annotated})
        self.assertTrue(payload["saved"])
        self.assertIn("my note", self.call("GET", "/api/games/%d" % second)[1]["game"]["pgn"])
        # the other game is untouched and still has its own identity
        self.assertIsNotNone(self.call("GET", "/api/games/%d" % first)[1]["game"]["source_id"])

    def test_tags_roundtrip(self):
        game_id = self.game_ids()[0]
        self.call("PUT", "/api/study/tags", body={"game_id": game_id, "tags": ["model game", " prep "]})
        status, payload = self.call("GET", "/api/study/tags", query={"game_id": str(game_id)})
        self.assertEqual(sorted(payload["tags"]), ["model game", "prep"])

    # ---------- position study ----------

    def test_position_index_and_lookup(self):
        collection = self.api.library.collection("My games")
        self.call("POST", "/api/study/index", body={"collection": collection["id"]})
        for _ in range(100):
            if not self.call("GET", "/api/study/index")[1]["running"]:
                break
            time.sleep(0.05)
        state = self.call("GET", "/api/study/index")[1]
        self.assertFalse(state["running"])
        self.assertEqual(state["errors"], 0, "every stored game should index cleanly")

        after_1e4 = Chess()
        after_1e4.move("e4")
        status, payload = self.call("GET", "/api/study/position", query={"fen": after_1e4.fen()})
        self.assertEqual(len(payload["games"]), 2, "both games pass through 1.e4")
        sans = {m["san"] for m in payload["moves"]}
        self.assertEqual(sans, {"e5", "d5"})
        self.assertEqual(payload["decades"][0]["decade"], 1920, "oldest game first")

    def test_position_lookup_needs_a_position(self):
        with self.assertRaises(ApiError):
            self.call("GET", "/api/study/position")

    def test_pins_roundtrip(self):
        fen = Chess().fen()
        status, payload = self.call("POST", "/api/study/pins",
                                    body={"fen": fen, "title": "Start here", "url": "https://lichess.org",
                                          "note": "kickoff"})
        pin_id = payload["id"]
        found = self.call("GET", "/api/study/position", query={"fen": fen})[1]["pins"]
        self.assertTrue(any(p["id"] == pin_id for p in found))
        self.call("DELETE", "/api/study/pins/%d" % pin_id)
        found = self.call("GET", "/api/study/position", query={"fen": fen})[1]["pins"]
        self.assertFalse(any(p["id"] == pin_id for p in found))

    def test_pin_rejects_a_bad_link(self):
        with self.assertRaises(ApiError):
            self.call("POST", "/api/study/pins", body={"fen": Chess().fen(), "title": "x", "url": "javascript:alert(1)"})

    # ---------- study folders ----------

    def test_folders_create_real_directories(self):
        status, payload = self.call("POST", "/api/study/folders", body={"name": "Tournament prep"})
        folder_id = payload["id"]
        self.assertTrue(os.path.isdir(payload["path"]))

        status, child = self.call("POST", "/api/study/folders",
                                  body={"name": "White repertoire", "parent_id": folder_id})
        self.assertTrue(os.path.isdir(child["path"]))

        collection = self.api.library.collection("My games")
        self.call("POST", "/api/study/assign",
                  body={"folder_id": folder_id, "collection_id": collection["id"]})
        manifest = os.path.join(payload["path"], "study.json")
        self.assertTrue(os.path.exists(manifest), "assigning a collection writes the manifest")
        with open(manifest, encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertEqual(data["collections"][0]["name"], "My games")
        pgn_path = os.path.normpath(os.path.join(payload["path"], data["collections"][0]["pgn"]))
        self.assertTrue(os.path.exists(pgn_path), "the manifest points at the real PGN file")

    def test_duplicate_folder_is_refused(self):
        self.call("POST", "/api/study/folders", body={"name": "Endgames"})
        with self.assertRaises(ApiError):
            self.call("POST", "/api/study/folders", body={"name": "Endgames"})

    def test_folder_needs_a_name(self):
        with self.assertRaises(ApiError):
            self.call("POST", "/api/study/folders", body={"name": "   "})

    def test_deleting_a_folder_takes_its_subfolders_and_frees_the_collections(self):
        status, parent = self.call("POST", "/api/study/folders", body={"name": "Autumn prep"})
        status, child = self.call("POST", "/api/study/folders",
                                  body={"name": "Sidelines", "parent_id": parent["id"]})
        collection = self.api.library.collection("My games")
        self.call("POST", "/api/study/assign",
                  body={"folder_id": child["id"], "collection_id": collection["id"]})

        status, result = self.call("DELETE", "/api/study/folders/%d" % parent["id"])
        self.assertEqual(result["deleted"], 2)
        self.assertEqual(result["kept"], [])
        self.assertFalse(os.path.exists(parent["path"]))

        folders = self.call("GET", "/api/study/folders")[1]
        self.assertNotIn("Autumn prep", [f["name"] for f in folders["folders"]])
        self.assertNotIn(child["id"], [a["folder_id"] for a in folders["assignments"]])
        self.assertIsNotNone(self.api.library.collection("My games"), "the collection itself survives")

    def test_deleting_a_folder_keeps_a_directory_holding_your_own_files(self):
        status, folder = self.call("POST", "/api/study/folders", body={"name": "Loose notes"})
        note = os.path.join(folder["path"], "notes.txt")
        with open(note, "w", encoding="utf-8") as handle:
            handle.write("mine")

        status, result = self.call("DELETE", "/api/study/folders/%d" % folder["id"])
        self.assertEqual(result["kept"], [os.path.realpath(folder["path"])])
        self.assertTrue(os.path.exists(note), "a file the user put there is never removed")
        self.assertFalse(os.path.exists(os.path.join(folder["path"], "study.json")))

    def test_deleting_a_folder_leaves_a_sibling_sharing_its_name(self):
        status, short = self.call("POST", "/api/study/folders", body={"name": "Open"})
        self.call("POST", "/api/study/folders", body={"name": "Open files"})
        status, result = self.call("DELETE", "/api/study/folders/%d" % short["id"])
        self.assertEqual(result["deleted"], 1)
        names = [f["name"] for f in self.call("GET", "/api/study/folders")[1]["folders"]]
        self.assertIn("Open files", names)

    def test_deleting_an_unknown_folder_is_refused(self):
        with self.assertRaises(ApiError):
            self.call("DELETE", "/api/study/folders/424242")

    # ---------- repertoires ----------

    def test_repertoire_roundtrip(self):
        status, payload = self.call("POST", "/api/repertoires", body={
            "name": "My White repertoire", "color": "w",
            "data": {"lines": [{"moves": ["e4", "e5", "Nf3"], "fen": Chess().fen(), "due": 0}]},
        })
        rep_id = payload["id"]
        status, payload = self.call("GET", "/api/repertoires/%d" % rep_id)
        data = json.loads(payload["repertoire"]["data"])
        self.assertEqual(data["lines"][0]["moves"], ["e4", "e5", "Nf3"])
        self.call("PUT", "/api/repertoires/%d" % rep_id,
                  body={"name": "Renamed", "color": "w", "data": data})
        self.assertEqual(self.call("GET", "/api/repertoires/%d" % rep_id)[1]["repertoire"]["name"], "Renamed")
        self.call("DELETE", "/api/repertoires/%d" % rep_id)

    # ---------- literature ----------

    def test_literature_offline_still_answers(self):
        status, payload = self.call("GET", "/api/literature", query={
            "moves": json.dumps(["e4", "c5"]),
            "opening": "Sicilian Defense: Najdorf Variation",
            "eco": "B90",
            "offline": "1",
        })
        kinds = {link["kind"] for link in payload["links"]}
        self.assertIn("reference", kinds, "lichess/Wikipedia links need no network")
        self.assertIn("search", kinds, "curated teacher searches need no network")
        for link in payload["links"]:
            self.assertTrue(link["url"].startswith("https://"), link["url"])

    def test_literature_accepts_space_separated_moves(self):
        status, payload = self.call("GET", "/api/literature",
                                    query={"moves": "e4 e5", "opening": "", "offline": "1"})
        self.assertIsInstance(payload["links"], list)

    def test_wikibooks_path_format(self):
        self.assertEqual(
            literature.move_path(["e4", "c5", "Nf3"]),
            "Chess Opening Theory/1. e4/1...c5/2. Nf3",
        )

    # ---------- engine ----------

    def test_engine_info(self):
        status, payload = self.call("GET", "/api/engine/info")
        self.assertIn("available", payload)

    def test_engine_analyze_needs_a_position(self):
        with self.assertRaises(ApiError):
            self.call("POST", "/api/engine/analyze", body={})

    @unittest.skipUnless(os.environ.get("CAISSA_ENGINE_TESTS"), "set CAISSA_ENGINE_TESTS=1 to run")
    def test_engine_finds_mate(self):
        status, payload = self.call("POST", "/api/engine/analyze",
                                    body={"fen": "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "movetime": 400})
        self.assertEqual(payload["bestmove"], "a1a8")

    # ---------- import ----------

    def test_import_source_rejects_nonsense(self):
        with self.assertRaises(ApiError):
            self.call("POST", "/api/import/source", body={"path": ""})

    def test_import_local_pgn_file(self):
        path = os.path.join(self.dir, "extra.pgn")
        different = (GAMES
                     .replace("abcd1234", "zzzz9999").replace("efgh5678", "yyyy8888")
                     .replace("testplayer", "someone-else")
                     .replace("2026.01.04", "2024.05.05").replace("1926.02.10", "1994.02.10"))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(different)
        status, payload = self.call("POST", "/api/import/source",
                                    body={"path": path, "collection": "Imported"})
        self.assertEqual(payload["added"], 2)

    def test_the_same_game_twice_is_a_duplicate(self):
        """Re-importing is safe: same players, same moves, even from a different URL."""
        path = os.path.join(self.dir, "again.pgn")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(GAMES.replace("abcd1234", "different-url").replace("efgh5678", "other-url"))
        status, payload = self.call("POST", "/api/import/source",
                                    body={"path": path, "collection": "Imported"})
        self.assertEqual(payload["added"], 0)
        self.assertEqual(payload["duplicates"], 2)

    def test_unknown_route_is_a_clean_404(self):
        with self.assertRaises(ApiError) as caught:
            self.call("GET", "/api/nope")
        self.assertEqual(caught.exception.status, 404)


if __name__ == "__main__":
    unittest.main()

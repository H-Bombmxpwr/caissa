"""The Python rules engine, held to the same standard as the browser one.

The position index, transposition detection and opening history all rest on this,
so it gets the same five perft positions as js/engine.js.

    py -m unittest tests.test_chess
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.chess import Chess                      # noqa: E402

PERFT = [
    ("startpos", "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", [20, 400, 8902]),
    ("kiwipete", "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1", [48, 2039, 97862]),
    ("ep/promo", "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1", [14, 191, 2812]),
    ("pos4", "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1", [6, 264, 9467]),
    ("pos5", "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8", [44, 1486, 62379]),
]


class PerftTests(unittest.TestCase):
    def test_move_generation(self):
        for name, fen, expected in PERFT:
            for depth, want in enumerate(expected, 1):
                with self.subTest(position=name, depth=depth):
                    self.assertEqual(Chess(fen).perft(depth), want)


class MoveTests(unittest.TestCase):
    def test_san_round_trip(self):
        game = Chess()
        line = "e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7 Re1 b5 Bb3 d6 c3 O-O".split()
        for san in line:
            self.assertEqual(game.move(san), san, "move %s should round-trip" % san)
        self.assertIn("r1bq1rk1", game.fen())

    def test_illegal_move_is_refused(self):
        game = Chess()
        with self.assertRaises((ValueError, TypeError)):
            game.move("e5")

    def test_en_passant_and_castling(self):
        game = Chess("k7/8/8/3pP3/8/8/8/K6R w K d6 0 2")
        self.assertEqual(game.move("exd6"), "exd6")
        self.assertIn("3P4", game.fen())

        castle = Chess("4k3/8/8/8/8/8/8/4K2R w K - 0 1")
        self.assertEqual(castle.move("O-O"), "O-O")
        self.assertIn("5RK1", castle.fen())

    def test_promotion(self):
        game = Chess("8/P6k/8/8/8/8/8/K7 w - - 0 1")
        self.assertEqual(game.move("a8=Q"), "a8=Q")
        self.assertTrue(game.fen().startswith("Q7/"))


class PositionKeyTests(unittest.TestCase):
    """The key is what links games through transpositions."""

    def test_same_position_by_different_move_orders(self):
        one = Chess()
        for san in ["d4", "Nf6", "c4", "e6", "Nc3"]:
            one.move(san)

        other = Chess()
        for san in ["c4", "Nf6", "Nc3", "e6", "d4"]:
            other.move(san)

        self.assertEqual(one.key(), other.key(), "transpositions must share a key")

    def test_different_positions_differ(self):
        one, other = Chess(), Chess()
        one.move("e4")
        other.move("d4")
        self.assertNotEqual(one.key(), other.key())

    def test_key_ignores_clocks_but_not_rights(self):
        """Move counters are irrelevant to a position; castling rights are not."""
        a = Chess("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
        b = Chess("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 9 17")
        self.assertEqual(a.key(), b.key())

        no_rights = Chess("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1")
        self.assertNotEqual(a.key(), no_rights.key())

    def test_side_to_move_matters(self):
        white = Chess("4k3/8/8/8/8/8/8/4K3 w - - 0 1")
        black = Chess("4k3/8/8/8/8/8/8/4K3 b - - 0 1")
        self.assertNotEqual(white.key(), black.key())


if __name__ == "__main__":
    unittest.main()

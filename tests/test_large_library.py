"""What changes when a library is too big to read end to end.

Every query here has an indexed answer and a scanning one. The scanning answers are
correct and were fine for a few thousand games; at ten million they take between
thirty-seven seconds and a minute each, which is what these tests exist to prevent
coming back.
"""
import tempfile
import unittest

from backend.api import Api


def pgn(white='Carlsen, Magnus', black='Nakamura, Hikaru', result='1-0',
        date='2019.06.01', eco='B90', opening='Sicilian Defense: Najdorf Variation',
        event='Norway Chess', white_elo='2875', black_elo='2775'):
    return '\n'.join([
        '[Event "%s"]' % event, '[Site "Stavanger"]', '[Date "%s"]' % date, '[Round "1"]',
        '[White "%s"]' % white, '[Black "%s"]' % black, '[Result "%s"]' % result,
        '[WhiteElo "%s"]' % white_elo, '[BlackElo "%s"]' % black_elo,
        '[ECO "%s"]' % eco, '[Opening "%s"]' % opening, '',
        '1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6 ' + result])


class LargeLibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.api = Api(self.tmp.name)
        self.lib = self.api.library
        self.lib.add_games('\n\n'.join([
            pgn(),
            pgn(black='Caruana, Fabiano', date='2020.01.02', white_elo='2863', black_elo='2835'),
            pgn(white='Kramnik, Vladimir', black='Anand, Viswanathan', eco='D13',
                opening='Slav Defense: Exchange Variation', event='Tata Steel Masters',
                date='2008.10.14', white_elo='2772', black_elo='2783'),
            pgn(white='Fischer, Robert James', black='Spassky, Boris', eco='E04',
                opening='Catalan Opening: Open Defense', event='World Championship',
                date='1972.07.23', white_elo='2785', black_elo='2660'),
        ]), 'Tests')

    def tearDown(self):
        self.lib.close()
        self.tmp.cleanup()

    def pretend_large(self):
        """Take the path a ten-million-game library takes, without ten million games."""
        self.lib.LARGE_LIBRARY = 0
        self.lib._local.is_large = None
        self.assertTrue(self.lib.is_large())

    # ---- the opening picker ----------------------------------------------------

    def test_the_opening_picker_reads_a_summary_not_every_game(self):
        rows, never_built = self.lib.openings()
        self.assertFalse(never_built)                 # importing built it
        names = {r['name']: r for r in rows}
        self.assertEqual(names['Sicilian Defense: Najdorf Variation']['games'], 2)
        self.assertEqual(names['Sicilian Defense: Najdorf Variation']['eco_from'], 'B90')
        self.assertEqual(len(self.lib.openings('Slav')[0]), 1)
        self.assertEqual(self.lib.openings('Nothing')[0], [])

    def test_the_summary_follows_the_games(self):
        self.lib.add_games(pgn(eco='C42', opening='Russian Game', event='Wijk'), 'Tests')
        names = {r['name'] for r in self.lib.openings()[0]}
        self.assertIn('Russian Game', names)

    def test_an_extended_eco_code_still_reports_its_three_letter_span(self):
        # A different date, or it is the same game as the first and skipped as one.
        self.lib.add_games(pgn(eco='B90a', opening='Najdorf, English attack',
                               date='2021.03.04'), 'Tests')
        span = {r['name']: r for r in self.lib.openings()[0]}['Najdorf, English attack']
        self.assertEqual((span['eco_from'], span['eco_to']), ('B90', 'B90'))

    # ---- sorting by rating -----------------------------------------------------

    def test_rating_sort_reads_a_stored_column_so_an_index_can_serve_it(self):
        order = [g['white'] for g in self.lib.search(sort='elo', limit=10)['games']]
        self.assertEqual(order[0], 'Carlsen, Magnus')          # 2875 is the highest
        plan = ' '.join(r[-1] for r in self.lib.connect().execute(
            'EXPLAIN QUERY PLAN SELECT id FROM games ORDER BY top_elo DESC LIMIT 30'))
        self.assertIn('games_top_elo', plan)
        self.assertNotIn('TEMP B-TREE', plan)

    def test_the_stored_rating_is_generated_and_cannot_drift(self):
        rows = self.lib.connect().execute(
            'SELECT white_elo, black_elo, top_elo FROM games').fetchall()
        for row in rows:
            self.assertEqual(row['top_elo'], max(row['white_elo'] or 0, row['black_elo'] or 0))
        # A game with no ratings at all still sorts, at the bottom.
        self.lib.add_games(pgn(white_elo='', black_elo='', event='Casual'), 'Tests')
        self.assertEqual(self.lib.connect().execute(
            "SELECT top_elo FROM games WHERE event='Casual'").fetchone()[0], 0)

    # ---- the free-text box -----------------------------------------------------

    def test_a_small_library_still_matches_anywhere_in_a_name(self):
        self.assertFalse(self.lib.is_large())
        self.assertEqual(self.lib.search(query='Magnus')['total'], 2)     # a forename
        self.assertEqual(self.lib.search(query='Steel')['total'], 1)      # mid-event

    def test_a_large_library_answers_the_same_box_from_indexes(self):
        self.pretend_large()
        self.assertEqual(self.lib.search(query='Carlsen')['total'], 2)
        self.assertEqual(self.lib.search(query='carlsen')['total'], 2)    # case forgiven
        self.assertEqual(self.lib.search(query='Kramnik')['total'], 1)
        self.assertEqual(self.lib.search(query='Tata')['total'], 1)       # event prefix
        self.assertEqual(self.lib.search(query='B90')['total'], 2)        # ECO
        self.assertEqual(self.lib.search(query='Nothing')['total'], 0)

    def test_an_opening_still_matches_a_word_from_the_middle_of_its_name(self):
        """"Najdorf" sits in the middle of what that opening is called."""
        self.pretend_large()
        self.assertEqual(self.lib.search(query='Najdorf')['total'], 2)
        self.assertEqual(self.lib.search(query='Catalan')['total'], 1)
        self.assertEqual(self.lib.search(query='Exchange')['total'], 1)

    def test_two_words_narrow_rather_than_widen(self):
        self.pretend_large()
        self.assertEqual(self.lib.search(query='Carlsen Najdorf')['total'], 2)
        self.assertEqual(self.lib.search(query='Kramnik Najdorf')['total'], 0)

    def test_the_indexed_path_never_falls_back_to_reading_every_row(self):
        self.pretend_large()
        params = []
        clause = self.lib._fast_text_clause('Carlsen', params)
        plan = ' '.join(r[-1] for r in self.lib.connect().execute(
            'EXPLAIN QUERY PLAN SELECT id FROM games WHERE ' + clause, params))
        self.assertNotIn('SCAN games', plan)
        for index in ('games_white', 'games_black', 'games_event', 'games_opening'):
            self.assertIn(index, plan)


if __name__ == '__main__':
    unittest.main()

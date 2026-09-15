"""chess.com imports: the narrowing the Player Lab asks for, without the network."""
import json
import tempfile
import unittest

from backend import importers, lichess
from backend.api import Api, _epoch_ms

MOVES = '1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 1-0'
ARCHIVES = ['https://api.chess.com/pub/player/zoe/games/2025/11',
            'https://api.chess.com/pub/player/zoe/games/2026/01',
            'https://api.chess.com/pub/player/zoe/games/2026/03']
# Each month offers one game of every kind, so a filter that keeps the wrong one shows.
# The site's own bracket is deliberately wrong on the half-hour game: chess.com calls
# thirty minutes rapid, and the library, following lichess, calls it classical.
KINDS = [('Blitz', '300', 'blitz'), ('Rapid', '900', 'rapid'),
         ('HalfHour', '1800', 'rapid'), ('Daily', '1/259200', 'daily')]


def pgn(black, date, time_control='300'):
    return '\n'.join(['[Event "Live Chess"]', '[White "Zoe"]', '[Black "%s"]' % black,
                      '[Result "1-0"]', '[Date "%s"]' % date,
                      '[TimeControl "%s"]' % time_control, '', MOVES])


class ChessComImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.api = Api(self.tmp.name)
        self.fetched = []
        self.original = lichess._request
        lichess._request = self.fake

    def tearDown(self):
        lichess._request = self.original
        self.api.library.close()
        self.tmp.cleanup()

    def fake(self, url, accept, **kwargs):
        self.fetched.append(url)
        if url.endswith('/archives'):
            return json.dumps({'archives': ARCHIVES})
        year, month = url.rsplit('/', 2)[-2:]
        stamp = '%s.%s' % (year, month)
        games = [{'pgn': pgn(name + month, '%s.0%d' % (stamp, n + 1), control),
                  'rules': 'chess', 'time_class': bracket}
                 for n, (name, control, bracket) in enumerate(KINDS)]
        games.append({'pgn': pgn('Chess960' + month, stamp + '.09'),
                      'rules': 'chess960', 'time_class': 'blitz'})
        return json.dumps({'games': games})

    def months(self):
        return [u.rsplit('/', 2)[-2:] for u in self.fetched if not u.endswith('/archives')]

    def blacks(self):
        return [r[0] for r in self.api.library.connect().execute('SELECT black FROM games')]

    def speeds(self):
        return sorted(r[0] for r in self.api.library.connect().execute('SELECT speed FROM games'))

    def test_a_time_control_keeps_only_that_bracket(self):
        result = importers.chesscom(self.api.library, 'zoe', 'Prep: zoe', 100, perf='blitz')
        self.assertEqual(result['added'], 3)               # one blitz game per archive
        self.assertEqual(len(self.months()), 3)
        self.assertTrue(all(n.startswith('Blitz') for n in self.blacks()), self.blacks())

    def test_the_time_control_is_read_from_the_pgn_not_the_site_bracket(self):
        """chess.com calls a half-hour game rapid; this library calls it classical."""
        importers.chesscom(self.api.library, 'zoe', 'Prep: zoe', 0, perf='rapid')
        self.assertTrue(all(n.startswith('Rapid') for n in self.blacks()), self.blacks())
        self.assertEqual(self.speeds(), ['rapid'] * 3)
        importers.chesscom(self.api.library, 'zoe', 'Prep: classical', 0, perf='classical')
        self.assertEqual(self.speeds(), ['classical'] * 3 + ['rapid'] * 3)
        self.assertTrue(all(n.startswith(('Rapid', 'HalfHour')) for n in self.blacks()), self.blacks())

    def test_correspondence_reaches_the_daily_games(self):
        importers.chesscom(self.api.library, 'zoe', 'Prep: zoe', 0, perf='correspondence')
        self.assertEqual(self.speeds(), ['correspondence'] * 3)

    def test_variants_are_never_imported(self):
        importers.chesscom(self.api.library, 'zoe', 'Prep: zoe', 0)
        self.assertFalse([n for n in self.blacks() if n.startswith('Chess960')])

    def test_dates_skip_whole_months_without_fetching_them(self):
        result = importers.chesscom(self.api.library, 'zoe', 'Prep: zoe', 0,
                                    since='2026-01-01', until='2026-01-31')
        self.assertEqual(self.months(), [['2026', '01']])
        self.assertEqual(result['added'], len(KINDS))      # everything but the variant

    def test_a_count_stops_the_walk_early(self):
        result = importers.chesscom(self.api.library, 'zoe', 'Prep: zoe', 2)
        self.assertEqual(self.months(), [['2026', '03']])  # newest archive first, then stop
        self.assertEqual(result['added'], 2)

    def test_zero_means_every_game_and_the_collection_comes_back(self):
        result = importers.chesscom(self.api.library, 'zoe', 'Prep: zoe', 0)
        self.assertEqual(result['added'], 3 * len(KINDS))
        self.assertEqual(result['collection'], 'Prep: zoe')
        self.assertEqual(self.api.library.collection(result['collection_id'])['name'], 'Prep: zoe')

    def test_route_accepts_all_and_passes_the_narrowing_through(self):
        status, payload = self.api.handle('POST', '/api/import/chesscom', {},
                                          {'user': 'zoe', 'max': 'all', 'perf': 'rapid',
                                           'collection': 'Prep: route'})
        self.assertEqual(status, 200)
        self.assertEqual(payload['added'], 3)
        self.assertTrue(payload['collection_id'])

    def test_a_bad_handle_is_refused_before_any_request(self):
        with self.assertRaisesRegex(ValueError, 'valid chess.com username'):
            importers.chesscom(self.api.library, 'no spaces allowed', 'Prep: zoe')
        self.assertEqual(self.fetched, [])


class EpochTests(unittest.TestCase):
    def test_dates_become_milliseconds_and_upper_bounds_include_their_day(self):
        self.assertEqual(_epoch_ms('2026-01-01'), 1767225600000)
        self.assertEqual(_epoch_ms('2026.01.01'), 1767225600000)
        self.assertEqual(_epoch_ms('2026-01-31', end_of_day=True) - _epoch_ms('2026-01-31'),
                         86400000 - 1)
        self.assertIsNone(_epoch_ms(''))
        self.assertIsNone(_epoch_ms('not a date'))
        self.assertEqual(_epoch_ms('1700000000000'), 1700000000000)


if __name__ == '__main__':
    unittest.main()

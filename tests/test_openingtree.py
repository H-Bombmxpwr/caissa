"""Your openings, scored from your own side of the board."""
import tempfile
import unittest
from unittest.mock import patch

from backend.api import Api, ApiError
from backend import openingtree, pgnutil

START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
AFTER_E4 = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1'


def game(white, black, result, moves, date='2024.01.01', tc='300+0', event='Rated blitz game',
         welo=1800, belo=1800):
    return ('[Event "%s"]\n[White "%s"]\n[Black "%s"]\n[Result "%s"]\n[Date "%s"]\n'
            '[TimeControl "%s"]\n[WhiteElo "%d"]\n[BlackElo "%d"]\n\n%s %s'
            % (event, white, black, result, date, tc, welo, belo, moves, result))


class SpeedTests(unittest.TestCase):
    def test_time_controls_become_the_buckets_people_filter_on(self):
        self.assertEqual(pgnutil.speed_of('60+0'), 'bullet')
        self.assertEqual(pgnutil.speed_of('179+0'), 'bullet')
        self.assertEqual(pgnutil.speed_of('180+0'), 'blitz')
        self.assertEqual(pgnutil.speed_of('300+3'), 'blitz')
        self.assertEqual(pgnutil.speed_of('600+0'), 'rapid')
        self.assertEqual(pgnutil.speed_of('1800+0'), 'classical')
        self.assertEqual(pgnutil.speed_of('1/86400'), 'correspondence')

    def test_an_unreadable_time_control_is_blank_rather_than_guessed(self):
        for value in ('', '-', '?', 'nonsense', None):
            self.assertEqual(pgnutil.speed_of(value), '')


class TreeTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.api = Api(self.temp.name)

    def tearDown(self):
        self.api.autoimport.stop()
        self.api.library.close()
        self.temp.cleanup()

    def call(self, method, path, body=None, query=None):
        return self.api.handle(method, path, query or {}, body)[1]

    def load(self, pgns, collection='Mine'):
        self.call('POST', '/api/games', {'pgn': '\n\n'.join(pgns), 'collection': collection})
        self.api.study._index(self.api.library.collection(collection)['id'])

    def report(self, **query):
        return self.call('GET', '/api/tree/position', query=dict(query))


class PerspectiveTests(TreeTestCase):
    def setUp(self):
        super().setUp()
        self.load([
            # Ada as White with 1.e4: one win, one loss.
            game('Ada', 'Bob', '1-0', '1. e4 e5 2. Nf3'),
            game('Ada', 'Cy', '0-1', '1. e4 e5 2. Nf3'),
            # Ada as Black, where 1.e4 is her opponent's move and she wins.
            game('Dee', 'Ada', '0-1', '1. e4 c5 2. Nf3'),
            # A game Ada is not in at all.
            game('Eve', 'Fay', '1-0', '1. e4 e5 2. Bc4'),
        ])

    def test_the_score_is_the_players_not_whites(self):
        data = self.report(player='Ada', fen=START)
        # Three of Ada's games; she won two of them.
        self.assertEqual(data['totals']['games'], 3)
        self.assertEqual(data['totals']['wins'], 2)
        self.assertEqual(data['totals']['losses'], 1)
        self.assertAlmostEqual(data['totals']['score_pct'], 66.7, places=1)
        self.assertEqual(data['perspective'], 'player')

    def test_a_win_as_black_counts_as_a_win(self):
        data = self.report(player='Ada', color='b', fen=START)
        self.assertEqual(data['totals']['games'], 1)
        self.assertEqual(data['totals']['wins'], 1)
        self.assertEqual(data['totals']['score_pct'], 100.0)

    def test_games_the_player_is_not_in_are_left_out(self):
        everyone = self.report(fen=START)['totals']['games']
        ada = self.report(player='Ada', fen=START)['totals']['games']
        self.assertEqual(everyone, 4)
        self.assertEqual(ada, 3)

    def test_moves_are_broken_out_with_their_own_scores(self):
        data = self.report(player='Ada', color='w', fen=AFTER_E4)
        moves = {m['san']: m for m in data['moves']}
        self.assertEqual(moves['e5']['games'], 2)
        self.assertEqual(moves['e5']['wins'], 1)
        self.assertEqual(moves['e5']['losses'], 1)
        self.assertEqual(moves['e5']['score_pct'], 50.0)
        self.assertEqual(moves['e5']['share_pct'], 100.0)

    def test_without_a_player_it_reads_from_whites_side(self):
        data = self.report(fen=START)
        self.assertEqual(data['perspective'], 'white')
        # Two White wins, two Black wins across the four games.
        self.assertEqual(data['totals']['wins'], 2)
        self.assertEqual(data['totals']['losses'], 2)

    def test_a_position_nobody_reached_is_empty_rather_than_an_error(self):
        data = self.report(player='Ada', fen='8/8/8/8/8/5k2/8/7K w - - 0 1')
        self.assertEqual(data['totals']['games'], 0)
        self.assertEqual(data['moves'], [])


class FilterTests(TreeTestCase):
    def setUp(self):
        super().setUp()
        self.load([
            game('Ada', 'Bob', '1-0', '1. e4 e5', date='2023.05.01', tc='300+0', welo=1800, belo=1500),
            game('Ada', 'Cy', '0-1', '1. e4 e5', date='2024.05.01', tc='600+0', welo=1800, belo=2200),
            game('Ada', 'Dee', '1/2-1/2', '1. e4 e5', date='2025.05.01', tc='60+0',
                 event='Casual bullet game', welo=1800, belo=1900),
        ])

    def test_time_control_narrows_the_report(self):
        self.assertEqual(self.report(player='Ada', speed='blitz', fen=START)['totals']['games'], 1)
        self.assertEqual(self.report(player='Ada', speed='rapid', fen=START)['totals']['games'], 1)
        self.assertEqual(self.report(player='Ada', speed='blitz,rapid', fen=START)['totals']['games'], 2)

    def test_dates_accept_a_year_a_month_or_a_day(self):
        self.assertEqual(self.report(player='Ada', since='2024', fen=START)['totals']['games'], 2)
        self.assertEqual(self.report(player='Ada', since='2024-06', fen=START)['totals']['games'], 1)
        self.assertEqual(self.report(player='Ada', until='2023-12-31', fen=START)['totals']['games'], 1)

    def test_opponent_rating_is_the_opponents_not_the_players(self):
        self.assertEqual(self.report(player='Ada', min_opponent_elo=2000, fen=START)['totals']['games'], 1)
        self.assertEqual(self.report(player='Ada', max_opponent_elo=1600, fen=START)['totals']['games'], 1)

    def test_rated_and_casual_can_be_separated(self):
        self.assertEqual(self.report(player='Ada', rated='1', fen=START)['totals']['games'], 2)
        self.assertEqual(self.report(player='Ada', rated='0', fen=START)['totals']['games'], 1)

    def test_the_trend_reports_a_score_for_each_year(self):
        trend = self.report(player='Ada', fen=START)['trend']
        self.assertEqual([t['period'] for t in trend], ['2023', '2024', '2025'])
        self.assertEqual([t['score_pct'] for t in trend], [100.0, 0.0, 50.0])

    def test_a_collection_limits_the_report(self):
        self.load([game('Ada', 'Zed', '1-0', '1. d4 d5')], collection='Other')
        mine = self.api.library.collection('Mine')['id']
        self.assertEqual(self.report(player='Ada', collection=mine, fen=START)['totals']['games'], 3)
        self.assertEqual(self.report(player='Ada', fen=START)['totals']['games'], 4)


class WeakestTests(TreeTestCase):
    def test_lines_are_ranked_by_points_dropped_not_by_score(self):
        # Four losses in one line, and a single loss in another. The first cost more.
        losses = [game('Ada', 'Bob%d' % n, '0-1', '1. e4 c5 2. Nf3 d6 3. Bb5+') for n in range(4)]
        once = [game('Ada', 'Zed', '0-1', '1. d4 f5 2. e4')]
        wins = [game('Ada', 'Cy%d' % n, '1-0', '1. e4 e5 2. Nf3 Nc6') for n in range(6)]
        self.load(losses + once + wins)
        weakest = self.call('GET', '/api/tree/weakest',
                            query={'player': 'Ada', 'min_games': '3'})['weakest']
        self.assertTrue(weakest)
        worst = weakest[0]
        self.assertEqual(worst['score_pct'], 0.0)
        self.assertEqual(worst['games'], 4)
        # The one-off loss never reaches the list: it is below the game threshold.
        self.assertTrue(all(entry['games'] >= 3 for entry in weakest))
        # Winning lines are not in a list of where points went.
        self.assertTrue(all(entry['score_pct'] < 50 for entry in weakest))

    def test_each_weak_line_names_itself_in_moves(self):
        self.load([game('Ada', 'Bob%d' % n, '0-1', '1. e4 c5 2. Nf3 d6') for n in range(3)])
        worst = self.call('GET', '/api/tree/weakest',
                          query={'player': 'Ada', 'min_games': '3'})['weakest'][0]
        self.assertIn('1.e4', worst['line'])
        self.assertTrue(worst['moves'])
        self.assertEqual(worst['moves'][0], 'e4')

    def test_a_losing_line_is_reported_once_not_at_every_depth(self):
        # Every position along a line that lost seven games reports the same seven
        # games; listing all of them is one answer printed six times.
        self.load([game('Ada', 'Bob%d' % n, '0-1', '1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4')
                   for n in range(7)]
                  + [game('Ada', 'Zed%d' % n, '0-1', '1. d4 f5 2. e4') for n in range(4)])
        weakest = self.call('GET', '/api/tree/weakest',
                            query={'player': 'Ada', 'min_games': '3', 'limit': '12'})['weakest']
        lines = [entry['line'] for entry in weakest]
        self.assertEqual(len(lines), 2, lines)
        self.assertTrue(lines[0].startswith('1.e4 c5'), lines)
        self.assertTrue(lines[1].startswith('1.d4 f5'), lines)
        # The deepest node of the chain is the one kept, because it names the line.
        self.assertIn('Nxd4', lines[0])

    def test_collapsing_keeps_lines_that_genuinely_differ(self):
        # Same first move, different continuations: both are real answers.
        self.load([game('Ada', 'Bob%d' % n, '0-1', '1. e4 c5 2. Nf3 d6') for n in range(4)]
                  + [game('Ada', 'Cy%d' % n, '0-1', '1. e4 e6 2. d4 d5') for n in range(3)])
        lines = [e['line'] for e in self.call('GET', '/api/tree/weakest',
                 query={'player': 'Ada', 'min_games': '3'})['weakest']]
        self.assertEqual(len(lines), 2, lines)
        self.assertTrue(any('c5' in l for l in lines), lines)
        self.assertTrue(any('e6' in l for l in lines), lines)

    def test_the_game_threshold_is_honoured(self):
        self.load([game('Ada', 'Bob%d' % n, '0-1', '1. e4 c5 2. Nf3') for n in range(3)])
        self.assertTrue(self.call('GET', '/api/tree/weakest',
                                  query={'player': 'Ada', 'min_games': '3'})['weakest'])
        self.assertFalse(self.call('GET', '/api/tree/weakest',
                                   query={'player': 'Ada', 'min_games': '10'})['weakest'])


class PlayersRouteTests(TreeTestCase):
    def test_it_lists_who_actually_appears_most(self):
        self.load([game('Ada', 'Bob', '1-0', '1. e4 e5'),
                   game('Cy', 'Ada', '0-1', '1. d4 d5'),
                   game('Bob', 'Cy', '1-0', '1. c4 e5')])
        names = {p['name']: p['games'] for p in self.call('GET', '/api/tree/players')['players']}
        self.assertEqual(names['Ada'], 2)
        self.assertEqual(names['Bob'], 2)
        self.assertEqual(names['Cy'], 2)

    def test_an_unnamed_player_is_not_offered(self):
        self.load([game('?', '?', '*', '1. e4 e5')])
        names = [p['name'] for p in self.call('GET', '/api/tree/players')['players']]
        self.assertNotIn('?', names)


class TreeRouteTests(TreeTestCase):
    def test_an_unknown_action_is_a_clean_404(self):
        with self.assertRaises(ApiError) as caught:
            self.call('GET', '/api/tree/nonsense')
        self.assertEqual(caught.exception.status, 404)

    def test_only_get_is_allowed(self):
        with self.assertRaises(ApiError) as caught:
            self.call('POST', '/api/tree/position', {})
        self.assertEqual(caught.exception.status, 405)


if __name__ == '__main__':
    unittest.main()

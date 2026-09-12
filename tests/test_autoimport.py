"""Auto-importing games from the linked lichess account as they are played."""
import json
import tempfile
import time
import unittest
from unittest.mock import patch

from backend.api import Api, ApiError
from backend import autoimport

ACCOUNT = {'username': 'Ada', 'id': 'ada', 'title': None, 'url': 'https://lichess.org/@/Ada',
           'scopes': ['study:read'], 'can_read_studies': True}

GAME = ('[Event "rated blitz game"]\n[Site "https://lichess.org/abcd1234"]\n'
        '[White "Ada"]\n[Black "Bob"]\n[Result "1-0"]\n[UTCDate "2026.09.12"]\n\n1. e4 e5 1-0')
LATER = ('[Event "rated blitz game"]\n[Site "https://lichess.org/efgh5678"]\n'
         '[White "Bob"]\n[Black "Ada"]\n[Result "0-1"]\n[UTCDate "2026.09.12"]\n\n1. d4 d5 0-1')


class AutoImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.api = Api(self.temp.name)

    def tearDown(self):
        self.api.autoimport.stop()
        self.api.library.close()
        self.temp.cleanup()

    def call(self, method, path, body=None, query=None):
        return self.api.handle(method, path, query or {}, body)[1]

    def connect(self):
        with patch('backend.lichess.account', return_value=dict(ACCOUNT)):
            self.call('PUT', '/api/lichess/account', {'token': 'lip_good'})

    # ---------- settings ----------

    def test_it_is_off_until_switched_on(self):
        state = self.call('GET', '/api/lichess/autoimport')
        self.assertFalse(state['enabled'])
        self.assertFalse(state['running'])
        self.assertEqual(state['collection'], 'My lichess games')

    def test_it_cannot_be_switched_on_without_an_account(self):
        with self.assertRaises(ApiError) as caught:
            self.call('PUT', '/api/lichess/autoimport', {'enabled': True})
        self.assertEqual(caught.exception.status, 401)

    def test_switching_it_on_starts_from_now_rather_than_backfilling(self):
        self.connect()
        before = int(time.time() * 1000)
        state = self.call('PUT', '/api/lichess/autoimport', {'enabled': True})
        self.assertTrue(state['enabled'])
        self.assertGreaterEqual(state['since'], before)

    def test_the_interval_is_clamped_to_something_lichess_will_tolerate(self):
        self.connect()
        self.assertEqual(self.call('PUT', '/api/lichess/autoimport',
                                   {'interval_minutes': 1})['interval_minutes'],
                         autoimport.MIN_INTERVAL)
        self.assertEqual(self.call('PUT', '/api/lichess/autoimport',
                                   {'interval_minutes': 99999})['interval_minutes'],
                         autoimport.MAX_INTERVAL)

    def test_nonsense_settings_are_refused_rather_than_stored(self):
        self.connect()
        for bad in ({'interval_minutes': 'often'}, {'max_games': 'lots'}, {'collection': '   '}):
            with self.assertRaises(ApiError, msg=bad):
                self.call('PUT', '/api/lichess/autoimport', bad)

    def test_settings_survive_a_restart(self):
        self.connect()
        self.call('PUT', '/api/lichess/autoimport',
                  {'collection': 'Blitz', 'interval_minutes': 60, 'rated_only': True})
        self.api.autoimport.stop()
        self.api.library.close()
        reopened = Api(self.temp.name)
        try:
            state = reopened.handle('GET', '/api/lichess/autoimport', {}, None)[1]
            self.assertEqual(state['collection'], 'Blitz')
            self.assertEqual(state['interval_minutes'], 60)
            self.assertTrue(state['rated_only'])
        finally:
            reopened.autoimport.stop()
            reopened.library.close()
            self.api = reopened

    # ---------- one check ----------

    def test_a_check_files_what_lichess_returns(self):
        self.connect()
        with patch('backend.lichess.user_games', return_value=GAME + '\n\n' + LATER):
            out = self.call('POST', '/api/lichess/autoimport', {})
        self.assertEqual(out['added'], 2)
        found = self.call('GET', '/api/games', query={'collection': 'My lichess games'})
        self.assertEqual(found['total'], 2)

    def test_the_same_games_arriving_twice_are_not_imported_twice(self):
        self.connect()
        with patch('backend.lichess.user_games', return_value=GAME):
            self.call('POST', '/api/lichess/autoimport', {})
            second = self.call('POST', '/api/lichess/autoimport', {})
        self.assertEqual(second['added'], 0)
        self.assertEqual(self.call('GET', '/api/games', query={})['total'], 1)

    def test_each_check_asks_only_for_what_is_new_with_an_overlap(self):
        self.connect()
        self.call('PUT', '/api/lichess/autoimport', {'enabled': True})
        seen = {}

        def record(user, **kwargs):
            seen.update(kwargs)
            return ''

        with patch('backend.lichess.user_games', side_effect=record):
            self.call('POST', '/api/lichess/autoimport', {})
        since = self.call('GET', '/api/lichess/autoimport')['since']
        # The window starts before the cursor, so a game that ended in the gap is caught.
        self.assertLess(seen['since'], since)
        self.assertGreaterEqual(seen['since'], since - 2 * autoimport.OVERLAP_MS)

    def test_a_check_that_finds_nothing_is_not_an_error(self):
        self.connect()
        with patch('backend.lichess.user_games', return_value='   '):
            out = self.call('POST', '/api/lichess/autoimport', {})
        self.assertEqual(out['added'], 0)
        self.assertIsNone(self.call('GET', '/api/lichess/autoimport')['last_error'])

    def test_a_failed_check_is_reported_and_does_not_move_the_cursor(self):
        self.connect()
        self.call('PUT', '/api/lichess/autoimport', {'enabled': True})
        before = self.call('GET', '/api/lichess/autoimport')['since']
        with patch('backend.lichess.user_games', side_effect=ConnectionError('offline')):
            with self.assertRaises(ApiError):
                self.call('POST', '/api/lichess/autoimport', {})
        state = self.call('GET', '/api/lichess/autoimport')
        self.assertIn('offline', state['last_error'])
        # The window is unchanged, so the next check re-asks for the same games.
        self.assertEqual(state['since'], before)

    def test_a_later_success_clears_the_earlier_error(self):
        self.connect()
        with patch('backend.lichess.user_games', side_effect=ConnectionError('offline')):
            with self.assertRaises(ApiError):
                self.call('POST', '/api/lichess/autoimport', {})
        with patch('backend.lichess.user_games', return_value=GAME):
            self.call('POST', '/api/lichess/autoimport', {})
        self.assertIsNone(self.call('GET', '/api/lichess/autoimport')['last_error'])

    def test_rated_only_is_passed_through(self):
        self.connect()
        self.call('PUT', '/api/lichess/autoimport', {'rated_only': True})
        seen = {}
        with patch('backend.lichess.user_games',
                   side_effect=lambda user, **kw: (seen.update(kw), '')[1]):
            self.call('POST', '/api/lichess/autoimport', {})
        self.assertIs(seen['rated'], True)

    def test_an_auto_import_is_undoable_like_any_other(self):
        self.connect()
        with patch('backend.lichess.user_games', return_value=GAME):
            self.call('POST', '/api/lichess/autoimport', {})
        batches = self.call('GET', '/api/import/history')['batches']
        self.assertEqual(batches[0]['label'], 'Auto-import from lichess')
        self.call('POST', '/api/import/undo', {'batch_id': batches[0]['id']})
        self.assertEqual(self.call('GET', '/api/games', query={})['total'], 0)

    def test_a_check_without_a_token_says_so_instead_of_calling_lichess(self):
        with patch('backend.lichess.user_games') as called:
            with self.assertRaises(ApiError):
                self.call('POST', '/api/lichess/autoimport', {})
        called.assert_not_called()

    def test_forgetting_the_token_stops_the_watcher(self):
        self.connect()
        self.call('PUT', '/api/lichess/autoimport', {'enabled': True})
        self.assertTrue(self.call('GET', '/api/lichess/autoimport')['running'])
        self.call('DELETE', '/api/lichess/account')
        time.sleep(0.2)
        self.assertFalse(self.call('GET', '/api/lichess/autoimport')['running'])

    def test_switching_it_off_stops_the_thread(self):
        self.connect()
        self.call('PUT', '/api/lichess/autoimport', {'enabled': True})
        self.assertTrue(self.call('GET', '/api/lichess/autoimport')['running'])
        self.call('PUT', '/api/lichess/autoimport', {'enabled': False})
        time.sleep(0.2)
        self.assertFalse(self.call('GET', '/api/lichess/autoimport')['running'])

    def test_indexing_after_an_import_is_optional_and_only_runs_on_new_games(self):
        self.connect()
        self.call('PUT', '/api/lichess/autoimport', {'index_after': True})
        with patch('backend.lichess.user_games', return_value=GAME), \
             patch.object(self.api.study, 'index') as indexed:
            self.call('POST', '/api/lichess/autoimport', {})
            self.assertEqual(indexed.call_count, 1)
            indexed.reset_mock()
            self.call('POST', '/api/lichess/autoimport', {})   # nothing new this time
            indexed.assert_not_called()

    def test_an_indexing_clash_does_not_sink_the_import(self):
        self.connect()
        self.call('PUT', '/api/lichess/autoimport', {'index_after': True})
        with patch('backend.lichess.user_games', return_value=GAME), \
             patch.object(self.api.study, 'index',
                          side_effect=ValueError('Position indexing is already running')):
            out = self.call('POST', '/api/lichess/autoimport', {})
        self.assertEqual(out['added'], 1)

    def test_the_watcher_survives_a_poll_that_raises(self):
        # The loop must never take the process down, whatever lichess does.
        self.connect()
        watcher = self.api.autoimport
        with patch('backend.lichess.user_games', side_effect=RuntimeError('boom')):
            result = watcher.run_once()
        self.assertIn('boom', result['error'])
        self.assertFalse(watcher.state['checking'])


if __name__ == '__main__':
    unittest.main()

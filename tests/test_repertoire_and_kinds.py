"""Opening-repertoire import, collection kinds, the lichess account and engine stats."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.api import Api, ApiError
from backend import hardware, repertoire
from backend.engine import Engine, LiveAnalysis

STUDY_PGN = '''[Event "White repertoire: Italian"]
[Site "https://lichess.org/study/abcd1234/wxyz"]
[Result "*"]
[ECO "C50"]
[Opening "Italian Game"]

1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 (3... Nf6 4. d3 Be7 5. O-O O-O) 4. c3 Nf6 5. d3 *

[Event "White repertoire: Sicilian"]
[Result "*"]

1. e4 c5 2. Nf3 d6 (2... Nc6 3. Bb5) 3. d4 cxd4 4. Nxd4 *
'''


class RepertoireParsingTests(unittest.TestCase):
    def test_variations_become_their_own_lines(self):
        out = repertoire.from_pgn(STUDY_PGN, 'w')
        moves = {' '.join(line['moves']) for line in out['lines']}
        self.assertEqual(out['chapters'], 2)
        self.assertEqual(out['skipped'], 0)
        self.assertIn('e4 e5 Nf3 Nc6 Bc4 Nf6 d3 Be7 O-O', moves)
        self.assertIn('e4 c5 Nf3 Nc6 Bb5', moves)

    def test_lines_end_on_a_move_the_owner_has_to_find(self):
        for color, owner_is_white in (('w', True), ('b', False)):
            for line in repertoire.from_pgn(STUDY_PGN, color)['lines']:
                last_ply_white = (len(line['moves']) - 1) % 2 == 0
                self.assertEqual(last_ply_white, owner_is_white, line['moves'])

    def test_a_line_that_only_starts_a_longer_one_is_dropped(self):
        # 3...Nf6 4.d3 is a prefix of the 5.O-O line, so only the longer one survives.
        moves = [' '.join(l['moves']) for l in repertoire.from_pgn(STUDY_PGN, 'w')['lines']]
        self.assertNotIn('e4 e5 Nf3 Nc6 Bc4 Nf6 d3', moves)
        self.assertEqual(len(moves), len(set(moves)))

    def test_depth_limit_is_honoured(self):
        out = repertoire.from_pgn(STUDY_PGN, 'w', max_plies=6)
        self.assertTrue(out['truncated'])
        self.assertTrue(all(len(l['moves']) <= 6 for l in out['lines']))

    def test_illegal_movetext_skips_only_that_chapter(self):
        broken = STUDY_PGN + '\n[Event "Nonsense"]\n[Result "*"]\n\n1. e4 Qxh8 *\n'
        out = repertoire.from_pgn(broken, 'w')
        self.assertEqual(out['skipped'], 1)
        self.assertEqual(out['chapters'], 2)

    def test_empty_pgn_is_rejected(self):
        with self.assertRaises(ValueError):
            repertoire.from_pgn('   ', 'w')

    def test_merge_adds_only_what_is_missing(self):
        first = repertoire.from_pgn(STUDY_PGN, 'w')['lines']
        merged, added = repertoire.merge(list(first), first)
        self.assertEqual(added, 0)
        self.assertEqual(len(merged), len(first))


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.api = Api(self.temp.name)

    def tearDown(self):
        self.api.library.close()
        self.temp.cleanup()

    def call(self, method, path, body=None, query=None):
        return self.api.handle(method, path, query or {}, body)[1]


class CollectionKindTests(ApiTestCase):
    GAME = '[Event "Played"]\n[White "A"]\n[Black "B"]\n[Result "1-0"]\n\n1. e4 e5 1-0'
    STUDY = '[Event "Idea"]\n[White "Study"]\n[Black "Position"]\n[Result "*"]\n\n1. d4 *'

    def test_the_database_lists_games_and_keeps_studies_aside(self):
        self.call('POST', '/api/games', {'pgn': self.GAME, 'collection': 'Played games'})
        self.call('POST', '/api/games', {'pgn': self.STUDY, 'collection': 'My studies', 'kind': 'studies'})

        games = self.call('GET', '/api/games', query={'kind': 'games'})
        self.assertEqual([g['event'] for g in games['games']], ['Played'])

        studies = self.call('GET', '/api/games', query={'kind': 'studies'})
        self.assertEqual([g['event'] for g in studies['games']], ['Idea'])

        everything = self.call('GET', '/api/games', query={})
        self.assertEqual(everything['total'], 2)

    def test_studies_stay_searchable_by_every_other_filter(self):
        self.call('POST', '/api/games', {'pgn': self.STUDY, 'collection': 'My studies', 'kind': 'studies'})
        found = self.call('GET', '/api/games', query={'kind': 'studies', 'q': 'Idea'})
        self.assertEqual(found['total'], 1)

    def test_an_unknown_kind_is_refused(self):
        with self.assertRaises(ApiError):
            self.call('POST', '/api/games', {'pgn': self.GAME, 'collection': 'x', 'kind': 'nonsense'})

    def test_importing_into_an_existing_collection_never_changes_its_kind(self):
        self.call('POST', '/api/games', {'pgn': self.GAME, 'collection': 'Mine'})
        self.call('POST', '/api/games', {'pgn': self.STUDY, 'collection': 'Mine', 'kind': 'studies'})
        kinds = {c['name']: c['kind'] for c in self.call('GET', '/api/collections')['collections']}
        self.assertEqual(kinds['Mine'], 'games')


class RepertoireImportRouteTests(ApiTestCase):
    def test_import_creates_a_repertoire_and_files_the_pgn_aside(self):
        out = self.call('POST', '/api/repertoires/import',
                        {'pgn': STUDY_PGN, 'name': 'Italian prep', 'color': 'w'})
        self.assertEqual(out['chapters'], 2)
        self.assertGreater(out['lines'], 0)
        self.assertEqual(out['collection'], 'Opening trees')

        kinds = {c['name']: c['kind'] for c in self.call('GET', '/api/collections')['collections']}
        self.assertEqual(kinds['Opening trees'], 'openings')
        # ...and therefore not in the game database.
        self.assertEqual(self.call('GET', '/api/games', query={'kind': 'games'})['total'], 0)
        self.assertEqual(self.call('GET', '/api/games', query={'kind': 'openings'})['total'], 2)

    def test_importing_the_same_study_twice_adds_no_duplicate_lines(self):
        first = self.call('POST', '/api/repertoires/import',
                          {'pgn': STUDY_PGN, 'name': 'Italian prep', 'color': 'w'})
        again = self.call('POST', '/api/repertoires/import',
                          {'pgn': STUDY_PGN, 'id': first['id'], 'name': 'Italian prep', 'color': 'w'})
        self.assertEqual(again['added'], 0)
        self.assertEqual(again['lines'], first['lines'])

    def test_a_repertoire_needs_a_name_and_a_pgn(self):
        with self.assertRaises(ApiError):
            self.call('POST', '/api/repertoires/import', {'pgn': STUDY_PGN})
        with self.assertRaises(ApiError):
            self.call('POST', '/api/repertoires/import', {'pgn': '', 'name': 'x'})

    def test_keep_pgn_can_be_declined(self):
        out = self.call('POST', '/api/repertoires/import',
                        {'pgn': STUDY_PGN, 'name': 'Lines only', 'color': 'w', 'keep_pgn': False})
        self.assertIsNone(out['collection'])
        self.assertEqual(self.call('GET', '/api/games', query={})['total'], 0)


class LichessAccountTests(ApiTestCase):
    ACCOUNT = {'username': 'Ada', 'id': 'ada', 'title': None,
               'url': 'https://lichess.org/@/Ada',
               'scopes': ['study:read'], 'can_read_studies': True}

    def test_no_token_reports_how_to_make_one(self):
        out = self.call('GET', '/api/lichess/account')
        self.assertFalse(out['connected'])
        self.assertIn('study%3Aread', out['token_url'])
        self.assertIn('study:read', out['scopes_needed'])

    def test_connecting_verifies_before_storing(self):
        with patch('backend.lichess.account', side_effect=PermissionError('bad token')):
            with self.assertRaises(ApiError):
                self.call('PUT', '/api/lichess/account', {'token': 'lip_wrong'})
        self.assertEqual(self.api.library.setting('lichess_token'), None)

        with patch('backend.lichess.account', return_value=dict(self.ACCOUNT)):
            out = self.call('PUT', '/api/lichess/account', {'token': 'lip_good'})
        self.assertEqual(out['username'], 'Ada')
        self.assertEqual(self.api.library.setting('lichess_token'), 'lip_good')

    def test_the_token_never_leaves_through_the_settings_route(self):
        with patch('backend.lichess.account', return_value=dict(self.ACCOUNT)):
            self.call('PUT', '/api/lichess/account', {'token': 'lip_secret'})
        with self.assertRaises(ApiError) as caught:
            self.call('GET', '/api/settings/lichess_token')
        self.assertEqual(caught.exception.status, 403)

    def test_forgetting_the_token_disconnects(self):
        with patch('backend.lichess.account', return_value=dict(self.ACCOUNT)):
            self.call('PUT', '/api/lichess/account', {'token': 'lip_good'})
        self.call('DELETE', '/api/lichess/account')
        self.assertFalse(self.call('GET', '/api/lichess/account')['connected'])

    def test_a_revoked_token_reads_as_disconnected_rather_than_failing(self):
        with patch('backend.lichess.account', return_value=dict(self.ACCOUNT)):
            self.call('PUT', '/api/lichess/account', {'token': 'lip_good'})
        with patch('backend.lichess.account', side_effect=PermissionError('revoked')):
            out = self.call('GET', '/api/lichess/account')
        self.assertFalse(out['connected'])
        self.assertTrue(out['stored'])
        self.assertIn('revoked', out['error'])

    def test_studies_import_as_their_own_kind_and_can_seed_a_repertoire(self):
        with patch('backend.lichess.account', return_value=dict(self.ACCOUNT)):
            self.call('PUT', '/api/lichess/account', {'token': 'lip_good'})
        with patch('backend.lichess.study_pgn', return_value=STUDY_PGN):
            out = self.call('POST', '/api/lichess/studies',
                            {'ids': ['abcd1234'], 'as_repertoire': True,
                             'name': 'From lichess', 'color': 'w'})
        self.assertEqual(out['studies'], 1)
        self.assertEqual(out['added'], 2)
        self.assertGreater(out['repertoire_lines'], 0)
        self.assertEqual(self.call('GET', '/api/games', query={'kind': 'games'})['total'], 0)
        self.assertEqual(self.call('GET', '/api/games', query={'kind': 'studies'})['total'], 2)

    def test_listing_studies_without_a_token_or_a_user_is_refused(self):
        with self.assertRaises(ApiError) as caught:
            self.call('GET', '/api/lichess/studies')
        self.assertEqual(caught.exception.status, 401)

    def test_one_unreadable_study_does_not_sink_the_others(self):
        with patch('backend.lichess.account', return_value=dict(self.ACCOUNT)):
            self.call('PUT', '/api/lichess/account', {'token': 'lip_good'})
        answers = [PermissionError('private'), STUDY_PGN]

        def reply(study_id, token=None, **kwargs):
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer

        with patch('backend.lichess.study_pgn', side_effect=reply):
            out = self.call('POST', '/api/lichess/studies', {'ids': ['locked', 'open']})
        self.assertEqual(out['studies'], 1)
        self.assertEqual(len(out['failures']), 1)
        self.assertEqual(out['failures'][0]['id'], 'locked')


class _times:
    """A stand-in for psutil's scputimes: summable, with an idle field."""

    def __init__(self, idle, busy):
        self.idle = idle
        self._values = (busy, idle)

    def __iter__(self):
        return iter(self._values)


class EngineStatisticsTests(unittest.TestCase):
    def test_search_statistics_are_parsed_from_a_uci_info_line(self):
        parsed = Engine._parse_info(
            'info depth 22 seldepth 31 multipv 1 score cp 34 nodes 1234567 nps 2500000 '
            'hashfull 412 tbhits 7 time 494 pv e2e4 e7e5')
        self.assertEqual(parsed['depth'], 22)
        self.assertEqual(parsed['seldepth'], 31)
        self.assertEqual(parsed['nodes'], 1234567)
        self.assertEqual(parsed['nps'], 2500000)
        self.assertEqual(parsed['hashfull'], 412)
        self.assertEqual(parsed['tbhits'], 7)
        self.assertEqual(parsed['time'], 494)
        self.assertEqual(parsed['pv'], ['e2e4', 'e7e5'])

    def test_engine_info_reports_core_counts(self):
        info = Engine().info()
        self.assertIn('cores', info)
        self.assertGreaterEqual(info['cores']['logical'] or 0, 1)
        self.assertGreaterEqual(info['threads'], 1)

    def test_live_status_carries_the_deepest_line_and_the_machine(self):
        live = LiveAnalysis()
        live.state = {'running': True, 'id': 'x', 'lines': [
            {'depth': 12, 'nodes': 100, 'nps': 50, 'hashfull': 1},
            {'depth': 20, 'nodes': 900, 'nps': 400, 'hashfull': 8, 'tbhits': 2, 'time': 30}]}
        status = live.status()
        self.assertEqual(status['depth'], 20)
        self.assertEqual(status['nodes'], 900)
        self.assertEqual(status['tbhits'], 2)
        self.assertIn('machine', status)
        self.assertIn('cores', status['machine'])

    def test_a_machine_that_publishes_no_sensor_reports_none_rather_than_a_guess(self):
        with patch('backend.hardware._windows_probe', return_value={}), \
             patch('backend.hardware._linux_temperature', return_value=(None, None)):
            sample = hardware.Telemetry()._sample()
        self.assertIsNone(sample['temperature_c'])
        self.assertIsNone(sample['power_w'])

    def test_a_hardware_monitor_reading_is_used_when_one_is_running(self):
        probe = {'monitor': 'root/LibreHardwareMonitor', 'monitor_temp_c': 61.5,
                 'monitor_name': 'CPU Package', 'monitor_power_w': 42.25}
        with patch('backend.hardware.WINDOWS', True), \
             patch('backend.hardware._windows_probe', return_value=probe), \
             patch('backend.hardware._linux_temperature', return_value=(None, None)):
            sample = hardware.Telemetry()._sample()
        self.assertEqual(sample['temperature_c'], 61.5)
        self.assertIn('LibreHardwareMonitor', sample['temperature_source'])
        self.assertEqual(sample['power_w'], 42.2)

    def test_cpu_load_is_measured_between_our_own_two_samples(self):
        # Deliberately not psutil.cpu_percent(): its "since the last call" state is
        # shared process-wide, and the live panel polls it from many server threads.
        sampler = hardware.CpuLoad()
        times = [_times(idle=100.0, busy=100.0), _times(idle=101.0, busy=104.0)]
        with patch.object(hardware.CpuLoad, '_times', staticmethod(lambda: times.pop(0))):
            self.assertIsNone(sampler.read())           # first sample has nothing to compare to
            sampler.sampled_at = 0                      # let the next read past the cache
            self.assertEqual(sampler.read(), 80.0)      # 4 busy ticks out of 5

    def test_rapid_polling_reuses_the_last_reading_instead_of_resampling(self):
        sampler = hardware.CpuLoad()
        times = [_times(idle=100.0, busy=100.0), _times(idle=101.0, busy=104.0)]
        with patch.object(hardware.CpuLoad, '_times', staticmethod(lambda: times.pop(0))):
            sampler.read()
            sampler.sampled_at = 0
            self.assertEqual(sampler.read(), 80.0)
            # No samples left: a third call must come from the cache, not raise.
            self.assertEqual(sampler.read(), 80.0)

    def test_counters_that_have_not_moved_keep_the_previous_reading(self):
        sampler = hardware.CpuLoad()
        frozen = _times(idle=5.0, busy=5.0)
        with patch.object(hardware.CpuLoad, '_times', staticmethod(lambda: frozen)):
            sampler.read()
            sampler.sampled_at = 0
            self.assertIsNone(sampler.read())           # zero-length window reports nothing
        sampler.percent = 42.0
        with patch.object(hardware.CpuLoad, '_times', staticmethod(lambda: frozen)):
            sampler.sampled_at = 0
            self.assertEqual(sampler.read(), 42.0)      # ...and never overwrites a real one

    def test_cpu_load_without_psutil_is_simply_absent(self):
        sampler = hardware.CpuLoad()
        with patch('backend.hardware.psutil', None):
            self.assertIsNone(sampler.read())

    def test_a_nonsense_thermal_zone_is_discarded(self):
        with patch('backend.hardware.WINDOWS', True), \
             patch('backend.hardware._windows_probe', return_value={'thermal_zone_decikelvin': 10}), \
             patch('backend.hardware._linux_temperature', return_value=(None, None)):
            sample = hardware.Telemetry()._sample()
        self.assertIsNone(sample['temperature_c'])


if __name__ == '__main__':
    unittest.main()

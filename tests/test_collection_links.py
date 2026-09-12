"""A game can sit on more than one shelf, and the library records which.

Before this, importing a game that was already in the library counted it as a
duplicate and dropped it — losing the fact that it belonged in both collections.
"""
import tempfile
import unittest
from unittest.mock import patch

from backend.api import Api, ApiError

GAME = ('[Event "Linares"]\n[White "Karpov, A"]\n[Black "Kasparov, G"]\n'
        '[Result "1-0"]\n[Date "1993.05.01"]\n\n1. e4 c5 2. Nf3 d6 1-0')
OTHER = ('[Event "Wijk"]\n[White "Anand, V"]\n[Black "Carlsen, M"]\n'
         '[Result "1/2-1/2"]\n[Date "2013.01.01"]\n\n1. d4 Nf6 1/2-1/2')

STUDY_PGN = '''[Event "John Games: Kasparov v Ivanchuk"]
[Result "*"]

1. e4 e5 2. Nf3 Nc6 *

[Event "John Games: Rubinstein"]
[Result "*"]

1. d4 d5 2. c4 *
'''


class LinkTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.api = Api(self.temp.name)

    def tearDown(self):
        self.api.library.close()
        self.temp.cleanup()

    def call(self, method, path, body=None, query=None):
        return self.api.handle(method, path, query or {}, body)[1]

    def add(self, pgn, collection, kind='games'):
        return self.call('POST', '/api/games',
                         {'pgn': pgn, 'collection': collection, 'kind': kind})

    def only_game(self, **query):
        found = self.call('GET', '/api/games', query=query)
        return found['games'][0] if found['games'] else None


class ImportLinkingTests(LinkTestCase):
    def test_the_same_game_imported_elsewhere_is_linked_not_dropped(self):
        self.assertEqual(self.add(GAME, 'Alpha')['added'], 1)
        second = self.add(GAME, 'Beta')
        self.assertEqual(second['added'], 0)
        self.assertEqual(second['duplicates'], 0)
        self.assertEqual(second['linked'], 1)

    def test_re_importing_into_the_same_collection_is_still_a_duplicate(self):
        self.add(GAME, 'Alpha')
        again = self.add(GAME, 'Alpha')
        self.assertEqual(again['duplicates'], 1)
        self.assertEqual(again['linked'], 0)

    def test_both_collections_list_the_one_game(self):
        self.add(GAME, 'Alpha')
        self.add(GAME, 'Beta')
        for name in ('Alpha', 'Beta'):
            found = self.call('GET', '/api/games', query={'collection': name})
            self.assertEqual(found['total'], 1, name)
        # ...and there is still only one row of PGN behind them.
        self.assertEqual(self.call('GET', '/api/games', query={})['total'], 1)

    def test_every_listed_game_says_which_shelves_hold_it(self):
        self.add(GAME, 'Alpha')
        self.add(GAME, 'Beta')
        game = self.only_game()
        names = [c['name'] for c in game['collections']]
        self.assertEqual(names, ['Alpha', 'Beta'])
        self.assertEqual([c['owner'] for c in game['collections']], [True, False])

    def test_a_single_collection_game_reports_just_the_one(self):
        self.add(OTHER, 'Alpha')
        self.assertEqual([c['name'] for c in self.only_game()['collections']], ['Alpha'])

    def test_collection_counts_include_linked_games(self):
        self.add(GAME, 'Alpha')
        self.add(OTHER, 'Alpha')
        self.add(GAME, 'Beta')
        counts = {c['name']: (c['games'], c['linked'])
                  for c in self.call('GET', '/api/collections')['collections']}
        self.assertEqual(counts['Alpha'], (2, 0))
        self.assertEqual(counts['Beta'], (1, 1))

    def test_a_game_linked_into_a_studies_collection_is_found_under_that_kind(self):
        self.add(GAME, 'Played games')
        self.add(GAME, 'My studies', kind='studies')
        self.assertEqual(self.call('GET', '/api/games', query={'kind': 'games'})['total'], 1)
        self.assertEqual(self.call('GET', '/api/games', query={'kind': 'studies'})['total'], 1)


class LinkRouteTests(LinkTestCase):
    def game_id(self):
        return self.only_game()['id']

    def test_a_game_can_be_added_to_a_collection_that_does_not_exist_yet(self):
        self.add(GAME, 'Alpha')
        out = self.call('POST', '/api/games/%d/collections' % self.game_id(),
                        {'collection': 'Tournament prep'})
        self.assertTrue(out['linked'])
        self.assertEqual([c['name'] for c in out['collections']], ['Alpha', 'Tournament prep'])
        self.assertEqual(self.call('GET', '/api/games', query={'collection': 'Tournament prep'})['total'], 1)

    def test_adding_it_twice_reports_that_it_is_already_there(self):
        self.add(GAME, 'Alpha')
        gid = self.game_id()
        self.call('POST', '/api/games/%d/collections' % gid, {'collection': 'Prep'})
        self.assertFalse(self.call('POST', '/api/games/%d/collections' % gid,
                                   {'collection': 'Prep'})['linked'])

    def test_a_link_can_be_removed_again(self):
        self.add(GAME, 'Alpha')
        gid = self.game_id()
        self.call('POST', '/api/games/%d/collections' % gid, {'collection': 'Prep'})
        out = self.call('DELETE', '/api/games/%d/collections/Prep' % gid)
        self.assertEqual([c['name'] for c in out['collections']], ['Alpha'])

    def test_a_games_own_collection_cannot_be_unlinked(self):
        self.add(GAME, 'Alpha')
        with self.assertRaises(ApiError):
            self.call('DELETE', '/api/games/%d/collections/Alpha' % self.game_id())

    def test_the_route_reports_the_shelves_for_one_game(self):
        self.add(GAME, 'Alpha')
        self.add(GAME, 'Beta')
        out = self.call('GET', '/api/games/%d/collections' % self.game_id())
        self.assertEqual([c['name'] for c in out['collections']], ['Alpha', 'Beta'])

    def test_adding_to_a_collection_needs_a_name_and_a_known_kind(self):
        self.add(GAME, 'Alpha')
        gid = self.game_id()
        with self.assertRaises(ApiError):
            self.call('POST', '/api/games/%d/collections' % gid, {'collection': '  '})
        with self.assertRaises(ApiError):
            self.call('POST', '/api/games/%d/collections' % gid,
                      {'collection': 'X', 'kind': 'nonsense'})


class CollectionDeletionTests(LinkTestCase):
    def test_deleting_a_collection_hands_shared_games_to_the_others(self):
        self.add(GAME, 'Alpha')
        self.add(GAME, 'Beta')
        alpha = [c for c in self.call('GET', '/api/collections')['collections']
                 if c['name'] == 'Alpha'][0]
        self.call('DELETE', '/api/collections/%d' % alpha['id'])
        # The game survives, now owned by the collection that still holds it.
        game = self.only_game()
        self.assertIsNotNone(game)
        self.assertEqual([c['name'] for c in game['collections']], ['Beta'])
        self.assertEqual([c['owner'] for c in game['collections']], [True])

    def test_deleting_a_collection_still_removes_games_only_it_held(self):
        self.add(GAME, 'Alpha')
        self.add(OTHER, 'Alpha')
        self.add(GAME, 'Beta')
        alpha = [c for c in self.call('GET', '/api/collections')['collections']
                 if c['name'] == 'Alpha'][0]
        self.call('DELETE', '/api/collections/%d' % alpha['id'])
        events = [g['event'] for g in self.call('GET', '/api/games', query={})['games']]
        self.assertEqual(events, ['Linares'])        # the shared game kept, the other gone


class LichessStudyNamingTests(LinkTestCase):
    ACCOUNT = {'username': 'Ada', 'id': 'ada', 'title': None,
               'url': 'https://lichess.org/@/Ada', 'scopes': ['study:read'],
               'can_read_studies': True}

    def connect(self):
        with patch('backend.lichess.account', return_value=dict(self.ACCOUNT)):
            self.call('PUT', '/api/lichess/account', {'token': 'lip_good'})

    def test_a_study_is_filed_under_its_own_name(self):
        self.connect()
        with patch('backend.lichess.study_pgn', return_value=STUDY_PGN):
            out = self.call('POST', '/api/lichess/studies',
                            {'studies': [{'id': 'abc123', 'name': 'john games'}]})
        self.assertEqual(out['collections'], ['john games'])
        self.assertEqual(out['added'], 2)
        names = {c['name']: c['kind'] for c in self.call('GET', '/api/collections')['collections']}
        self.assertEqual(names['john games'], 'studies')

    def test_each_study_gets_its_own_collection(self):
        self.connect()
        with patch('backend.lichess.study_pgn', return_value=STUDY_PGN):
            out = self.call('POST', '/api/lichess/studies',
                            {'studies': [{'id': 'a', 'name': 'john games'},
                                         {'id': 'b', 'name': 'endgames'}]})
        self.assertEqual(sorted(out['collections']), ['endgames', 'john games'])
        # The second study holds the same chapters, so they are linked, not duplicated.
        self.assertEqual(out['linked'], 2)
        self.assertEqual(self.call('GET', '/api/games', query={'collection': 'endgames'})['total'], 2)

    def test_one_shared_collection_is_still_available(self):
        self.connect()
        with patch('backend.lichess.study_pgn', return_value=STUDY_PGN):
            out = self.call('POST', '/api/lichess/studies',
                            {'studies': [{'id': 'a', 'name': 'john games'}],
                             'collection': 'Lichess studies'})
        self.assertEqual(out['collections'], ['Lichess studies'])

    def test_a_study_with_no_name_falls_back_to_its_id(self):
        self.connect()
        with patch('backend.lichess.study_pgn', return_value=STUDY_PGN):
            out = self.call('POST', '/api/lichess/studies', {'ids': ['xyz789']})
        self.assertEqual(out['collections'], ['Lichess study xyz789'])

    def test_a_failure_names_the_study_that_failed(self):
        self.connect()
        with patch('backend.lichess.study_pgn', side_effect=PermissionError('private')):
            out = self.call('POST', '/api/lichess/studies',
                            {'studies': [{'id': 'a', 'name': 'john games'}]})
        self.assertEqual(out['failures'][0]['name'], 'john games')
        self.assertEqual(out['studies'], 0)

    def test_the_response_says_which_kind_to_look_under(self):
        self.connect()
        with patch('backend.lichess.study_pgn', return_value=STUDY_PGN):
            out = self.call('POST', '/api/lichess/studies',
                            {'studies': [{'id': 'a', 'name': 'john games'}]})
        self.assertEqual(out['kind'], 'studies')


if __name__ == '__main__':
    unittest.main()

import tempfile
import unittest
from unittest.mock import patch
from backend.api import Api, ApiError
from backend.chess import Chess

PGN='[Event "Index test"]\n[White "A"]\n[Black "B"]\n[Result "*"]\n\n1. e4 e5 *'

class UiWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.api=Api(self.temp.name)
    def tearDown(self):
        self.api.library.close();self.temp.cleanup()
    def call(self,method,path,body=None):
        return self.api.handle(method,'/api/'+path,{},body)
    def test_linked_index_skips_complete_games_and_replays_edits(self):
        lib=self.api.library
        self.call('POST','games',{'pgn':PGN,'collection':'Source'})
        game_id=lib.search()['games'][0]['id']
        linked=lib.ensure_collection('Linked')
        lib.link_game(game_id,linked['id'])
        self.api.study._index(linked['id'])
        self.assertEqual(lib.search(position=Chess().fen())['total'],1)
        self.assertEqual([c['indexed_games'] for c in lib.collections() if c['name'] in ('Source','Linked')],[1,1])
        with patch.object(lib,'game_pgn',side_effect=AssertionError('Replayed an indexed game')):
            self.api.study._index(linked['id'])
        self.call('PUT','games/'+str(game_id),{'pgn':PGN.replace('e4 e5','d4 d5')})
        self.assertEqual([c['indexed_games'] for c in lib.collections() if c['name']=='Linked'],[0])
        self.api.study._index(linked['id'])
        game=Chess();game.move('d4');game.move('d5')
        self.assertEqual(lib.search(position=game.fen())['total'],1)
    def test_computer_levels_use_separate_engine_and_validate_range(self):
        for level,skill in [(1,0),(6,10),(11,20)]:
            with patch.object(self.api.opponent,'analyze',return_value={'bestmove':'e2e4'}) as analyze:
                status,_=self.call('POST','engine/play',{'fen':Chess().fen(),'level':level})
                self.assertEqual(status,200)
                self.assertEqual(analyze.call_args.kwargs['skill'],skill)
                self.assertLessEqual(analyze.call_args.kwargs['movetime'],1000)
        with self.assertRaises(ApiError) as error:
            self.call('POST','engine/play',{'fen':Chess().fen(),'level':12})
        self.assertEqual(error.exception.status,400)

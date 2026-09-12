import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.api import Api, ApiError
from backend.chess import Chess
from backend import pgnutil

PGN='''[Event "Linares"]
[White "Karpov, A"]
[Black "Kasparov, G"]
[WhiteElo "2725"]
[BlackElo "2805"]
[Date "1993.02.19"]
[Round "10"]
[Annotator "Knaak, R"]
[Termination "White resigned"]
[Result "0-1"]

{Introduction} 1. e4 {One note} {Another note} e5
; A whole-line comment mentioning bogus move Qh9
2. Nf3 Nc6 {White resigned} 0-1
'''


class LibraryToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.api=Api(self.temp.name)

    def tearDown(self):
        self.api.library.close()
        self.temp.cleanup()

    def call(self, method, endpoint, body=None, query=None):
        return self.api.handle(method,'/api/'+endpoint,query or {},body)[1]

    def test_deep_book_sources_filters_and_offline_cache(self):
        result={'white':40,'draws':30,'black':20,'moves':[{'san':'e4','white':40,'draws':30,'black':20,'averageRating':2501}],'topGames':[]}
        query={'source':'masters','fen':Chess().fen(),'since':'2000'}
        with patch('backend.api.lichess.explorer',return_value=result) as fetch:
            first=self.call('GET','book',query=query)
            self.assertEqual(first['moves'][0]['games'],90)
            self.assertEqual(first['total'],90)
            self.assertEqual(fetch.call_args.kwargs['extra'],{'since':'2000'})
            self.assertEqual(fetch.call_args.kwargs['moves'],50)
            self.assertTrue(self.call('GET','book',query=query)['cached'])
            self.assertEqual(fetch.call_count,1)
            self.call('GET','book',query=dict(query,since='2010'))
            self.assertEqual(fetch.call_count,2,'different filters must not share cached statistics')
            self.call('GET','book',query=dict(query,source='lichess',ratings='2200,2500',speeds='classical'))
            self.assertEqual(fetch.call_args.kwargs['extra']['ratings'],'2200,2500')
        with patch('backend.api.lichess.explorer',side_effect=ConnectionError('offline')):
            self.assertTrue(self.call('GET','book',query=query)['cached'])
            with self.api.library.connect() as db:
                db.execute('UPDATE explorer_cache SET fetched_at=0')
            fallback=self.call('GET','book',query=query)
            self.assertTrue(fallback['stale'])
            self.assertEqual(fallback['total'],90)

    def test_metadata_filters_and_deletion_preview(self):
        self.call('POST','games',{'pgn':PGN})
        filters={'event':'Linares','annotator':'Knaak','date_from':'1993-02-01','date_to':'1993-02-28',
                 'round':'10','annotated':'1','white_min_elo':'2700','black_max_elo':'2900','termination':'resigned'}
        data=self.call('GET','games',query=filters)
        self.assertEqual(data['total'],1)
        self.assertEqual(data['games'][0]['annotator'],'Knaak, R')
        self.assertEqual(data['games'][0]['ply_count'],4)
        self.assertEqual(self.call('POST','games/delete-preview',{'filters':filters})['total'],1)
        self.assertEqual(self.call('GET','games',query={'q':'Karpov Kasparov Linares Knaak'})['total'],1)
        self.assertEqual(self.call('GET','games',query={'annotated':'0'})['total'],0)
        self.assertIn('{Another note}',self.api.library.game(data['games'][0]['id'])['pgn'])

    def test_existing_game_metadata_backfill(self):
        self.call('POST','games',{'pgn':PGN})
        with self.api.library.connect() as db:
            db.execute('UPDATE games SET has_annotations=NULL,annotator=NULL')
        self.api.library.close()
        self.api=Api(self.temp.name)
        self.assertEqual(self.call('GET','games',query={'annotator':'Knaak'})['total'],1)

    def test_folder_category_and_manifest(self):
        result=self.call('POST','games',{'pgn':PGN})
        folder=self.call('POST','study/folders',{'name':'Examples','category':'Opening examples'})
        self.call('POST','study/assign',{'folder_id':folder['id'],'collection_id':result['collection_id']})
        self.assertEqual(self.call('GET','games',query={'category':'Opening examples'})['total'],1)
        self.call('PUT','study/folders/'+str(folder['id']),{'category':'Chess studies'})
        manifest=json.loads((Path(folder['path'])/'study.json').read_text())
        self.assertEqual(manifest['category'],'Chess studies')

    def test_opening_book_counts_games_not_repetitions(self):
        self.call('POST','games',{'pgn':'[Event "Repeat"]\n[Result "1-0"]\n\n1. Nf3 Nf6 2. Ng1 Ng8 3. Nf3 Nf6 1-0'})
        collection=self.api.library.collections()[0]['id']
        self.api.study._index(collection)
        data=self.call('GET','book',query={'fen':Chess().fen()})
        self.assertEqual(data['moves'][0]['san'],'Nf3')
        self.assertEqual(data['moves'][0]['games'],1)
        self.assertEqual(data['moves'][0]['white'],1)
        self.assertEqual(self.call('GET','book',query={'collection':'999'})['moves'],[])

    def test_pdf_copy_page_and_validation(self):
        pdf=b'%PDF-1.4\n%%EOF'
        result=self.call('POST','books',{'title':'My book','data':base64.b64encode(pdf).decode()})
        ident=result['id']
        self.assertEqual(Path(self.api.books.file(ident)).read_bytes(),pdf)
        self.call('PUT','books/'+str(ident),{'page':12})
        self.assertEqual(self.call('GET','books')['books'][0]['page'],12)
        with self.assertRaises(ApiError):
            self.call('POST','books',{'title':'Bad file','data':base64.b64encode(b'not pdf').decode()})
        with self.assertRaises(ValueError):self.api.books.file('../outside')

    def test_player_suggestions_offline_and_cached_catalog(self):
        self.assertTrue(any(p['name']=='Fischer' for p in self.call('GET','masters/players',query={'q':'Fisc'})['players']))
        self.api.library.setting('mentor_catalog',json.dumps([{'name':'Hou','url':'https://www.pgnmentor.com/players/Hou.zip'}]))
        self.assertEqual(self.call('GET','masters/players',query={'q':'Hou'})['players'][0]['source'],'PGN Mentor collection')

    def test_semicolon_comments_are_not_moves(self):
        self.assertEqual(pgnutil.moves(PGN),['e4','e5','Nf3','Nc6'])

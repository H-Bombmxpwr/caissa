"""Import isolation, exact deletion previews, combined filters and online cache."""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from backend.api import Api, ApiError
from backend.chess import Chess


def pgn(name, eco='E70'):
    return f'[Event "Test"]\n[White "{name}"]\n[Black "Fischer"]\n[ECO "{eco}"]\n[Result "*"]\n\n1. d4 Nf6 2. c4 g6 *'


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.api = Api(self.temp.name)

    def tearDown(self):
        self.api.library.close()
        self.temp.cleanup()

    def call(self, method, path, body=None, query=None):
        return self.api.handle(method, '/api/'+path, query or {}, body)[1]

    def rated(self, white, black, result, welo, belo, eco='B90', opening='Sicilian, Najdorf'):
        return (f'[Event "Rated"]\n[White "{white}"]\n[Black "{black}"]\n[Result "{result}"]\n'
                f'[WhiteElo "{welo}"]\n[BlackElo "{belo}"]\n[ECO "{eco}"]\n[Opening "{opening}"]\n\n1. e4 c5 {result}')

    def test_outcome_reads_from_the_named_player(self):
        self.call('POST','games',{'pgn':self.rated('Carlsen','Nepo','1-0',2850,2790)})
        self.call('POST','games',{'pgn':self.rated('Nepo','Carlsen','1-0',2790,2850)})
        self.call('POST','games',{'pgn':self.rated('Carlsen','Ding','1/2-1/2',2850,2780)})
        wins=self.call('GET','games',None,{'player':'Carlsen','outcome':'win'})
        self.assertEqual(wins['total'],1)
        self.assertEqual(wins['games'][0]['white'],'Carlsen')
        self.assertEqual(self.call('GET','games',None,{'player':'Carlsen','outcome':'loss'})['total'],1)
        self.assertEqual(self.call('GET','games',None,{'player':'Carlsen','outcome':'draw'})['total'],1)
        # As White only, the same player has one win and no losses.
        self.assertEqual(self.call('GET','games',None,{'white':'Carlsen','outcome':'win'})['total'],1)
        self.assertEqual(self.call('GET','games',None,{'white':'Carlsen','outcome':'loss'})['total'],0)

    def test_rating_range_has_a_floor_and_a_ceiling(self):
        self.call('POST','games',{'pgn':self.rated('Top','Also','1-0',2850,2790)})
        self.call('POST','games',{'pgn':self.rated('Club','Player','0-1',1600,1550,'C50','Italian Game')})
        self.assertEqual(self.call('GET','games',None,{'min_elo':'2000'})['total'],1)
        self.assertEqual(self.call('GET','games',None,{'max_elo':'2000'})['total'],1)
        self.assertEqual(self.call('GET','games',None,{'min_elo':'1000','max_elo':'3000'})['total'],2)

    def test_opening_names_come_with_the_eco_span_they_cover(self):
        self.call('POST','games',{'pgn':self.rated('A','B','1-0',2000,2000,'B90','Sicilian, Najdorf')})
        self.call('POST','games',{'pgn':self.rated('C','D','0-1',2000,2000,'B97','Sicilian, Najdorf')})
        self.call('POST','games',{'pgn':self.rated('E','F','1-0',2000,2000,'C50','Italian Game')})
        names={o['name']:o for o in self.call('GET','openings')['openings']}
        self.assertEqual(names['Sicilian, Najdorf']['eco_from'],'B90')
        self.assertEqual(names['Sicilian, Najdorf']['eco_to'],'B97')
        self.assertEqual(names['Sicilian, Najdorf']['games'],2)
        self.assertEqual([o['name'] for o in self.call('GET','openings',None,{'q':'Italian'})['openings']],['Italian Game'])

    def test_import_reports_progress_and_settles(self):
        self.assertFalse(self.call('GET','import/status')['running'])
        self.call('POST','games',{'pgn':pgn('Progress'),'collection':'Watched'})
        status=self.call('GET','import/status')
        self.assertFalse(status['running'])
        self.assertEqual(status['label'],'Watched')
        self.assertEqual(status['added'],1)
        self.assertEqual(status['total'],1)
        self.assertIsNone(status['error'])

    def test_a_deleted_collection_does_not_come_back(self):
        self.call('POST','games',{'pgn':pgn('Doomed'),'collection':'Scratch'})
        scratch=[c for c in self.call('GET','collections')['collections'] if c['name']=='Scratch'][0]
        self.call('DELETE','collections/%d'%scratch['id'])
        self.assertNotIn('Scratch',[c['name'] for c in self.call('GET','collections')['collections']])
        # A restart re-opens the same library; only an empty one gets a starter collection.
        from backend.api import Api
        self.api.library.close()
        self.api=Api(self.temp.name)
        self.assertNotIn('Scratch',[c['name'] for c in self.call('GET','collections')['collections']])

    def test_game_facts_group_what_wikipedia_actually_returned(self):
        from backend import literature
        pages = {'query': {'pages': [
            {'title': 'Anatoly Karpov', 'extract': 'A Russian chess grandmaster.',
             'fullurl': 'https://en.wikipedia.org/wiki/Anatoly_Karpov'},
            {'title': 'Garry Kasparov', 'extract': 'A Russian chess grandmaster.',
             'fullurl': 'https://en.wikipedia.org/wiki/Garry_Kasparov'},
            {'title': 'Linares', 'extract': 'A town in Spain.', 'pageprops': {'disambiguation': ''},
             'fullurl': 'https://en.wikipedia.org/wiki/Linares'},
            {'title': 'Game of the Century (chess)', 'extract': 'A 1956 game won by Bobby Fischer.',
             'fullurl': 'https://en.wikipedia.org/wiki/Game_of_the_Century_(chess)'},
            {'title': 'Nothing Here', 'missing': True},
        ]}}
        search = {'query': {'search': [{'title': 'Game of the Century (chess)'}]}}
        with patch.object(literature, 'gemini_note', return_value=None), \
             patch.object(literature, '_wikipedia_search', return_value=['Game of the Century (chess)']), \
             patch.object(literature, '_wikipedia', return_value={
                 p['title']: {'title': p['title'], 'extract': p['extract'], 'url': p['fullurl']}
                 for p in pages['query']['pages'] if not p.get('missing')
                 and 'disambiguation' not in (p.get('pageprops') or {})}):
            found = literature.game_facts({'White': 'Karpov, Anatoly', 'Black': 'Kasparov, Garry',
                                           'Event': 'Linares 11th', 'Site': 'Linares', 'Date': '1993.02.??'})
        labels = {g['label']: [i['title'] for i in g['items']] for g in found['groups']}
        self.assertEqual(labels['The players'], ['Anatoly Karpov', 'Garry Kasparov'])
        self.assertNotIn('The event and place', labels, 'a disambiguation page is not a fact')
        self.assertEqual(labels['Possibly about this game'], ['Game of the Century (chess)'])
        self.assertIn('judge whether it is this game',
                      [g for g in found['groups'] if g['label'].startswith('Possibly')][0]['note'])
        self.assertEqual(found['query']['white'], 'Anatoly Karpov')

    def test_game_facts_says_so_when_there_is_nothing_to_look_up(self):
        from backend import literature
        self.enterContext(patch.object(literature, 'gemini_note', return_value=None))
        blank = literature.game_facts({'White': 'White', 'Black': 'Black', 'Event': 'Study', 'Site': '', 'Date': ''})
        self.assertEqual(blank['groups'], [])
        self.assertIn('nothing to look up', blank['message'])
        offline = literature.game_facts({'White': 'Karpov, Anatoly', 'Black': 'Kasparov, Garry',
                                         'Event': 'Linares', 'Site': '', 'Date': '1993.??.??'}, online=False)
        self.assertEqual(offline['groups'], [])
        self.assertIn('Offline', offline['message'])

    def test_facts_route_caches_a_hit_and_never_caches_a_miss(self):
        from backend import literature
        hit = {'groups': [{'label': 'The players', 'note': None,
                           'items': [{'title': 'A', 'extract': 'B', 'url': 'https://example.org/A'}]}],
               'message': None, 'query': {}}
        calls = []
        def fake(headers, online=True):
            calls.append(headers)
            return hit
        with patch.object(literature, 'game_facts', fake):
            first = self.call('GET', 'facts', None, {'white': 'Karpov, Anatoly'})
            second = self.call('GET', 'facts', None, {'white': 'Karpov, Anatoly'})
        self.assertEqual(len(calls), 1, 'the second lookup is served from the library')
        self.assertNotIn('cached', first)
        self.assertTrue(second['cached'])

        miss = {'groups': [], 'message': 'Offline', 'query': {}}
        with patch.object(literature, 'game_facts', lambda headers, online=True: miss):
            self.call('GET', 'facts', None, {'white': 'Nobody At All'})
            self.call('GET', 'facts', None, {'white': 'Nobody At All'})
        with patch.object(literature, 'game_facts', fake):
            self.call('GET', 'facts', None, {'white': 'Nobody At All'})
        self.assertEqual(len(calls), 2, 'an offline miss must not be remembered as the answer')

    def test_the_ai_note_is_optional_and_labelled(self):
        from backend import literature
        with patch.dict(os.environ, {'GEMINI_API_KEY': ''}):
            self.assertIsNone(literature.gemini_note({'White': 'A', 'Black': 'B'}),
                              'no key configured means no note, not an error')
        with patch.object(literature, 'gemini_note', return_value={'model': 'test-model', 'text': 'Context.'}), \
             patch.object(literature, '_wikipedia', return_value={}), \
             patch.object(literature, '_wikipedia_search', return_value=[]):
            found = literature.game_facts({'White': 'Karpov, Anatoly', 'Black': 'Kasparov, Garry',
                                           'Event': 'Linares', 'Site': '', 'Date': '1993.??.??'})
        self.assertEqual(found['note'], {'model': 'test-model', 'text': 'Context.'})
        self.assertEqual(found['groups'], [], 'a note is not a source and never becomes one')

    def test_facts_route_needs_something_to_search_for(self):
        with self.assertRaises(ApiError):
            self.call('GET', 'facts', None, {})

    def test_requests_survive_a_windowed_build_with_no_stdout(self):
        """PyInstaller's console=False gives the process sys.stdout = None."""
        import threading
        from functools import partial
        from http.server import ThreadingHTTPServer
        import urllib.request
        import server

        httpd = ThreadingHTTPServer(('127.0.0.1', 0), partial(server.Handler, directory=os.getcwd()))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        url = 'http://127.0.0.1:%d/api/health' % httpd.server_port
        try:
            with patch.object(sys, 'stdout', None):
                with urllib.request.urlopen(url, timeout=10) as res:
                    payload = json.loads(res.read().decode('utf-8'))
            self.assertTrue(payload['ok'], 'health has to answer with no stdout to log to')
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_import_undo_survives_restart_and_preserves_duplicates(self):
        self.call('POST','games',{'pgn':pgn('Existing')})
        r=self.call('POST','games',{'pgn':pgn('Existing')+'\n\n'+pgn('New')})
        self.assertEqual(r['duplicates'],1)
        self.api.library.close()
        self.api=Api(self.temp.name)
        self.assertEqual(self.call('POST','import/undo',{'batch_id':r['batch_id']})['deleted'],1)
        self.assertEqual(self.api.library.search()['games'][0]['white'],'Existing')
        self.assertEqual(self.call('POST','import/undo',{'batch_id':r['batch_id']})['deleted'],0)

    def test_archive_batches_share_one_undo(self):
        path=os.path.join(self.temp.name,'many.pgn')
        with open(path,'w') as f:
            f.write('\n\n'.join(pgn('Player '+str(n)) for n in range(205)))
        r=self.call('POST','import/source',{'path':path})
        self.assertEqual(r['added'],205)
        self.assertEqual(self.call('POST','import/undo',{'batch_id':r['batch_id']})['deleted'],205)

    def test_failed_import_retains_undo_for_completed_batches(self):
        def partial_import(library,*args):
            library.add_games(pgn('Partial'))
            raise ValueError('Damaged archive')
        with patch('backend.importers.import_source',side_effect=partial_import):
            with self.assertRaises(ApiError):
                self.call('POST','import/source',{'path':'broken.zip'})
        batch=self.call('GET','import/history')['batches'][0]
        self.assertEqual(batch['games'],1)
        self.assertEqual(self.call('POST','import/undo',{'batch_id':batch['id']})['deleted'],1)

    def test_position_index_includes_late_positions(self):
        moves='Nf3 Nf6 Ng1 Ng8 '*7+'d4'
        result=self.call('POST','games',{'pgn':'[Event "Long"]\n[Result "*"]\n\n'+moves+' *'})
        self.api.study._index(result['collection_id'])
        game=Chess()
        for san in moves.split():
            game.move(san)
        self.assertEqual(self.api.library.search(position=game.fen())['total'],1)

    def test_delete_snapshot_does_not_delete_later_imports(self):
        self.call('POST','games',{'pgn':pgn('First')})
        preview=self.call('POST','games/delete-preview',{'filters':{'player':'Fischer'}})
        self.call('POST','games',{'pgn':pgn('Later')})
        self.assertEqual(self.call('POST','games/delete-confirm',{'token':preview['token']})['deleted'],1)
        self.assertEqual(self.api.library.search()['games'][0]['white'],'Later')
        with self.assertRaises(ApiError):
            self.call('POST','games/delete-confirm',{'token':preview['token']})

    def test_delete_snapshot_ignores_reused_game_id(self):
        self.call('POST','games',{'pgn':pgn('Same')})
        preview=self.call('POST','games/delete-preview',{'filters':{}})
        ident=self.api.library.search()['games'][0]['id']
        self.api.library.delete_game(ident)
        self.call('POST','games',{'pgn':pgn('Same')})
        self.assertEqual(self.call('POST','games/delete-confirm',{'token':preview['token']})['deleted'],0)

    def test_combined_filters_are_identical_for_search_and_delete(self):
        self.call('POST','games',{'pgn':pgn('A')+'\n\n'+pgn('B','B90')})
        ident=self.api.library.search(white='A')['games'][0]['id']
        with self.api.library.connect() as db:
            db.execute('UPDATE games SET added_at=1704110400')
            db.execute('INSERT INTO positions VALUES(?,?,?,?)',(Chess().key(),ident,0,'d4'))
            db.execute('INSERT INTO game_tags VALUES(?,?)',(ident,'model'))
        filters={'player':'Fischer','event':'Test','min_length':'4','max_length':'4','eco':'E60','eco_to':'E99','added_from':'2024-01-01','added_to':'2024-01-01','position':Chess().fen(),'tag':'model'}
        found=self.call('GET','games',query=filters)
        self.assertEqual(found['total'],1)
        self.assertEqual(self.call('POST','games/delete-preview',{'filters':filters})['total'],1)

    def test_tablebase_cache_and_piece_limit(self):
        fen='8/8/8/8/8/5k2/8/7K w - - 0 1'
        with patch('backend.lichess._request',return_value=json.dumps({'category':'draw','moves':[]})) as request:
            self.assertEqual(self.call('GET','tablebase',query={'fen':fen})['category'],'draw')
            self.call('GET','tablebase',query={'fen':fen})
            self.assertEqual(request.call_count,1)
        with self.assertRaises(ApiError):
            self.call('GET','tablebase',query={'fen':Chess().fen()})

    def test_library_migration_preserves_settings_and_source(self):
        from backend import paths
        from backend.store import Library
        source_root=os.path.join(self.temp.name,'source')
        old=Library(os.path.join(source_root,'library'))
        old.add_games(pgn('Migrated'))
        old.setting('appearance','{"darkMode":true}')
        old.close()
        appdata=os.path.join(self.temp.name,'appdata')
        with patch.dict(os.environ,{'APPDATA':appdata,'DATA_DIR':''}), patch.object(paths,'__file__',os.path.join(source_root,'backend','paths.py')):
            target=paths.default_data_dir()
            migrated=Library(target)
            self.assertEqual(migrated.search()['total'],1)
            self.assertEqual(json.loads(migrated.setting('appearance'))['darkMode'],True)
            migrated.close()
            self.assertTrue(os.path.exists(os.path.join(source_root,'library','library.db')))
            self.assertEqual(paths.default_data_dir(),target)
    def test_mentor_catalog_restricts_links_and_caches(self):
        html='<a href="players/Fischer.zip">PGN</a><a href="https://evil.test/x.pgn">bad</a>'
        with patch('backend.lichess._request',return_value=html) as request:
            data=self.call('GET','masters/catalog',query={'q':'fischer'})
            self.assertEqual(data['players'],[{'name':'Fischer','url':'https://www.pgnmentor.com/players/Fischer.zip'}])
            self.call('GET','masters/catalog',query={'q':'fischer'})
            self.assertEqual(request.call_count,1)


if __name__=='__main__':
    unittest.main()

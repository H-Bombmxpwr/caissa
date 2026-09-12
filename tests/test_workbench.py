"""Import isolation, exact deletion previews, combined filters and online cache."""
import json
import os
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

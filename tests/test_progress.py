import tempfile
import unittest
from unittest.mock import patch
from backend.api import Api


class ProgressTests(unittest.TestCase):
    def test_stream_batches_accumulate_without_fake_totals(self):
        with tempfile.TemporaryDirectory() as directory:
            api=Api(directory)
            samples=[]
            def stream(*args, **kwargs):
                # These are Library.add_games callbacks across two batches.
                for done,total in [(0,200),(100,200),(200,200),(0,50),(25,50),(50,50)]:
                    api.library.on_progress(done,total)
                    samples.append((api.import_status['done'],api.import_status['total']))
                return {'added':250,'duplicates':0,'skipped':0}
            try:
                with patch('backend.lichess.import_all_user_games',side_effect=stream):
                    api.handle('POST','/api/import/lichess',{},dict(user='Player',all=True))
                self.assertEqual(samples,[(0,0),(100,0),(200,0),(200,0),(225,0),(250,0)])
                self.assertFalse(api.import_status['running'])
                self.assertEqual(api.import_status['added'],250)
                # A subsequent finite import must reset the offset and expose its total.
                api.handle('POST','/api/games',{},dict(pgn='[Event "Test"]\n\n1. e4 e5 *'))
                self.assertEqual(api.import_status['done'],1)
                self.assertEqual(api.import_status['total'],1)
            finally:
                api.library.close()

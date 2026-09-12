import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from backend.chess import Chess
from backend.openingbook import lookup, BOOK
from desktop import DesktopSettings


class NativeExportTests(unittest.TestCase):
    def test_save_as_and_cancel(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge=DesktopSettings(folder,False)
            bridge._window=Mock()
            bridge._window.create_file_dialog.return_value=(str(Path(folder)/'study.pgn'),)
            pgn='[Event "Study"]\n\n1. e4 {Keep this} *\n'
            result=bridge.export_pgn(pgn)
            self.assertTrue(result['saved'])
            self.assertEqual(Path(result['path']).read_text(encoding='utf-8'),pgn)
            bridge._window.create_file_dialog.return_value=None
            self.assertEqual(bridge.export_pgn('replacement'),{'cancelled':True})
            self.assertEqual(Path(result['path']).read_text(encoding='utf-8'),pgn)


class IncludedBookTests(unittest.TestCase):
    def test_real_book_is_shipped_and_queryable_offline(self):
        self.assertTrue(BOOK.is_file(),'Build the shipped book before distributing the application')
        with patch('backend.lichess.explorer',side_effect=AssertionError('Offline book must not use the network')):
            data=lookup(Chess().fen())
            self.assertGreater(data['book']['games'],200000)
            self.assertGreater(data['book']['positions'],50000)
            self.assertTrue({'e4','d4','c4','Nf3'}.issubset({m['san'] for m in data['moves']}))
            board=Chess()
            for san in ['e4','e5','Nf3','Nc6','Bb5','a6','Ba4','Nf6','O-O','Be7','Re1','b5','Bb3','d6']:
                board.move(san)
            reply=lookup(board.fen())
            self.assertGreater(len(reply['moves']),0)
            for move in reply['moves']:
                self.assertEqual(move['games'],move['white']+move['draws']+move['black'])
                Chess(board.fen()).move(move['san'])
        metadata=json.loads(BOOK.with_suffix('.json').read_text(encoding='utf-8'))
        self.assertEqual(metadata['positions'],data['book']['positions'])

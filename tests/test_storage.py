"""Folder selection, restart persistence and safe library relocation."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from backend import paths
from backend.store import Library
from desktop import DesktopSettings


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        # macOS hands out /var/folders/… while the app realpaths to /private/var/…;
        # resolve here so both sides of every comparison spell the path the same way.
        self.root = Path(self.temp.name).resolve()
        self.env = patch.dict(os.environ, {'APPDATA':str(self.root/'appdata'), 'DATA_DIR':''})
        self.env.start()
        self.source = self.root/'original'
        self.target = self.root/'chosen'
        self.target.mkdir()
        library = Library(str(self.source))
        library.add_games('[Event "Stored"]\n[Result "*"]\n\n1. e4 e5 *')
        library.setting('appearance', '{"darkMode":true}')
        library.close()
        (self.source/'notes.txt').write_text('Keep my files')
        self.bridge = DesktopSettings(str(self.source))

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_native_picker_and_restart_copy(self):
        self.bridge._window = Mock()
        self.bridge._window.create_file_dialog.return_value = [str(self.target)]
        self.assertEqual(self.bridge.choose_storage_folder(), str(self.target))
        self.assertEqual(self.bridge.use_storage_folder()['pending'], str(self.target))
        self.assertEqual(list(self.target.iterdir()), [])
        # Changes made after choosing the folder must also be copied.
        library = Library(str(self.source))
        library.setting('trainer', 'latest progress')
        library.close()
        self.assertEqual(paths.default_data_dir(), str(self.target))
        self.assertEqual(paths.default_data_dir(), str(self.target))
        copied = Library(str(self.target))
        self.assertEqual(copied.search()['total'], 1)
        self.assertEqual(copied.setting('trainer'), 'latest progress')
        self.assertEqual(copied.setting('appearance'), '{"darkMode":true}')
        copied.close()
        self.assertEqual((self.target/'notes.txt').read_text(), 'Keep my files')
        self.assertTrue((self.source/'library.db').exists())

    def test_show_in_folder_opens_the_library(self):
        with patch('desktop.sys.platform', 'win32'), patch('desktop.os.startfile', create=True) as opened:
            self.assertEqual(self.bridge.reveal_storage_folder()['opened'], str(self.source))
        opened.assert_called_once_with(str(self.source))

    def test_show_in_folder_reports_a_missing_library(self):
        missing = DesktopSettings(str(self.root/'gone'))
        self.assertIn('not there any more', missing.reveal_storage_folder()['error'])

    def test_cancel_picker_and_pending_change(self):
        self.bridge._window = Mock()
        self.bridge._window.create_file_dialog.return_value = None
        self.assertIsNone(self.bridge.choose_storage_folder())
        self.assertIn('error', self.bridge.use_storage_folder())
        paths.schedule_storage_change(str(self.source), str(self.target))
        self.bridge.cancel_storage_change()
        self.assertNotIn('pending', paths.storage_preferences())

    def test_reject_existing_files_and_nested_paths(self):
        (self.target/'unrelated.txt').write_text('Do not overwrite')
        with self.assertRaises(ValueError):
            paths.schedule_storage_change(str(self.source), str(self.target))
        nested = self.source/'nested'
        nested.mkdir()
        with self.assertRaises(ValueError):
            paths.schedule_storage_change(str(self.source), str(nested))
        with self.assertRaises(ValueError):
            paths.schedule_storage_change(str(self.source), str(self.source))

    def test_failed_copy_keeps_original_active(self):
        paths.schedule_storage_change(str(self.source), str(self.target))
        with patch('backend.paths.shutil.copytree', side_effect=OSError('Disk full')):
            self.assertEqual(paths.default_data_dir(), str(self.source))
        self.assertIn('Disk full', paths.storage_preferences()['error'])
        self.assertTrue((self.source/'library.db').exists())
        self.assertEqual(list(self.target.iterdir()), [])
        self.assertEqual(paths.default_data_dir(), str(self.target))

    def test_override_and_missing_drive(self):
        bridge = DesktopSettings(str(self.source), overridden=True)
        bridge.selected_folder = str(self.target)
        self.assertIn('DATA_DIR', bridge.use_storage_folder()['error'])
        paths.save_storage_preferences({'library_dir':str(self.root/'unplugged')})
        with self.assertRaises(OSError):
            paths.default_data_dir()
        with patch.dict(os.environ, {'DATA_DIR':str(self.source)}):
            self.assertEqual(paths.default_data_dir(), str(self.source))

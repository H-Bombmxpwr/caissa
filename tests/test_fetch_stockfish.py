"""Choosing and unpacking the right Stockfish build for each platform.

Stockfish has renamed its release assets more than once. When it did, this script kept
matching on Windows and stopped matching on macOS and Linux — and because the build
workflow only ran on a tag, nobody found out until a release failed. These tests pin the
naming and the two archive formats so the next rename is a red test rather than a red
release.
"""
import io
import os
import sys
import tarfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import fetch_stockfish as sf


def assets(*names):
    return [{'name': n, 'size': 1, 'browser_download_url': 'https://example.test/' + n}
            for n in names]


# What Stockfish publishes today.
CURRENT = assets(
    'stockfish-android-arm64-universal.tar.gz',
    'stockfish-android-armv7-neon.tar.gz',
    'stockfish-linux-arm64-universal.tar.gz',
    'stockfish-linux-riscv64-universal.tar.gz',
    'stockfish-linux-x86-64-universal.tar.gz',
    'stockfish-macos-universal.tar.gz',
    'stockfish-windows-arm64-universal.zip',
    'stockfish-windows-x86-64-universal.zip',
)

# What it published before, which older checkouts and mirrors may still serve.
LEGACY = assets(
    'stockfish-ubuntu-x86-64-avx2.tar',
    'stockfish-ubuntu-x86-64-modern.tar',
    'stockfish-macos-m1-apple-silicon.tar',
    'stockfish-macos-x86-64-avx2.tar',
    'stockfish-windows-x86-64-avx2.zip',
)


class PickAssetTests(unittest.TestCase):
    def test_every_platform_the_build_runs_on_finds_an_asset(self):
        expected = {
            ('Windows', 'AMD64'): 'stockfish-windows-x86-64-universal.zip',
            ('Windows', 'ARM64'): 'stockfish-windows-arm64-universal.zip',
            ('Darwin', 'arm64'): 'stockfish-macos-universal.tar.gz',
            ('Darwin', 'x86_64'): 'stockfish-macos-universal.tar.gz',
            ('Linux', 'x86_64'): 'stockfish-linux-x86-64-universal.tar.gz',
            ('Linux', 'aarch64'): 'stockfish-linux-arm64-universal.tar.gz',
        }
        for (system, machine), name in expected.items():
            self.assertEqual(sf.pick_asset(CURRENT, system, machine)['name'], name,
                             '%s/%s' % (system, machine))

    def test_android_and_riscv_are_never_chosen_for_a_desktop(self):
        for system, machine in (('Linux', 'x86_64'), ('Linux', 'aarch64')):
            chosen = sf.pick_asset(CURRENT, system, machine)['name']
            self.assertNotIn('android', chosen)
            self.assertNotIn('riscv', chosen)

    def test_the_older_naming_still_resolves(self):
        self.assertIn('ubuntu', sf.pick_asset(LEGACY, 'Linux', 'x86_64')['name'])
        self.assertIn('m1-apple-silicon', sf.pick_asset(LEGACY, 'Darwin', 'arm64')['name'])
        self.assertIn('macos-x86-64', sf.pick_asset(LEGACY, 'Darwin', 'x86_64')['name'])

    def test_an_unknown_system_is_treated_as_linux(self):
        self.assertIn('linux', sf.pick_asset(CURRENT, 'FreeBSD', 'x86_64')['name'])

    def test_a_release_with_nothing_usable_says_what_it_had(self):
        with self.assertRaises(SystemExit) as caught:
            sf.pick_asset(assets('stockfish-android-arm64-universal.tar.gz'), 'Windows', 'AMD64')
        self.assertIn('android', str(caught.exception))

    def test_universal_is_preferred_over_a_cpu_specific_build(self):
        mixed = assets('stockfish-linux-x86-64-avx2.tar.gz',
                       'stockfish-linux-x86-64-universal.tar.gz')
        self.assertIn('universal', sf.pick_asset(mixed, 'Linux', 'x86_64')['name'])


class ArchiveTests(unittest.TestCase):
    """Windows ships a zip; macOS and Linux ship a .tar.gz. Both must unpack."""

    FILES = {
        'stockfish/stockfish-linux-x86-64-universal': b'\x7fELF-binary',
        'stockfish/nn-abc.nnue': b'weights',
        'stockfish/Top CPU Contributors.txt': b'thanks',
        'stockfish/README.md': b'docs',
    }

    def tarball(self):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
            for name, body in self.FILES.items():
                info = tarfile.TarInfo(name)
                info.size = len(body)
                archive.addfile(info, io.BytesIO(body))
        return buffer.getvalue()

    def zipball(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            for name, body in self.FILES.items():
                archive.writestr(name.replace('universal', 'universal.exe'), body)
        return buffer.getvalue()

    def test_a_tar_gz_yields_the_binary_and_its_weights(self):
        names, read, archive = sf.members(self.tarball(), 'stockfish-linux-x86-64-universal.tar.gz')
        try:
            target = sf.best_binary(names)
            self.assertEqual(target, 'stockfish/stockfish-linux-x86-64-universal')
            self.assertEqual(read(target), b'\x7fELF-binary')
            self.assertEqual([n for n in names if n.endswith('.nnue')], ['stockfish/nn-abc.nnue'])
        finally:
            archive.close()

    def test_a_zip_yields_the_binary(self):
        names, read, archive = sf.members(self.zipball(), 'stockfish-windows-x86-64-universal.zip')
        try:
            target = sf.best_binary(names)
            self.assertTrue(target.endswith('.exe'), target)
            self.assertEqual(read(target), b'\x7fELF-binary')
        finally:
            archive.close()

    def test_documentation_is_never_mistaken_for_the_engine(self):
        for name in ('stockfish/README.md', 'stockfish/Top CPU Contributors.txt',
                     'stockfish/nn-abc.nnue'):
            self.assertNotEqual(sf.best_binary(list(self.FILES)), name)


if __name__ == '__main__':
    unittest.main()

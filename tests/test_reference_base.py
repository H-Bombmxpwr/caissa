"""Attaching a base: headers into the index, moves left in the file."""
import os
import tempfile
import unittest

from backend.api import Api, ApiError
from backend import importers, pgnutil

GAP = '\n\n'

GAMES = [
    ('Carlsen, Magnus', 'Nakamura, Hikaru', '1-0', '2019.06.01', 'B90a', 'Norway Chess',
     '1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6 6. Be3 e5 1-0'),
    ('Nakamura, Hikaru', 'Carlsen, Magnus', '0-1', '2019.06.05', 'B99', 'Norway Chess',
     '1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6 6. Bg5 e6 7. f4 Be7 0-1'),
    ('Kramnik, Vladimir', 'Anand, Viswanathan', '1/2-1/2', '2008.10.14', 'D13k', 'World Championship',
     '1. d4 d5 2. c4 c6 3. Nf3 Nf6 4. cxd5 cxd5 1/2-1/2'),
    ('Fischer, Robert James', 'Spassky, Boris V', '1-0', '1972.07.23', 'E04a', 'World Championship',
     '1. d4 Nf6 2. c4 e6 3. g3 d5 4. Nf3 dxc4 1-0'),
]


def pgn(white, black, result, date, eco, event, moves):
    return '\n'.join([
        '[Event "%s"]' % event, '[Site "?"]', '[Date "%s"]' % date, '[Round "1"]',
        '[White "%s"]' % white, '[Black "%s"]' % black, '[Result "%s"]' % result,
        '[WhiteElo "2800"]', '[BlackElo "2750"]', '[ECO "%s"]' % eco, '', moves])


class ReferenceBaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.api = Api(self.tmp.name)
        self.folder = os.path.join(self.tmp.name, 'reference')
        os.makedirs(self.folder, exist_ok=True)
        self.pgn = os.path.join(self.folder, 'Base.pgn')
        with open(self.pgn, 'w', encoding='utf-8') as handle:
            handle.write(GAP.join(pgn(*g) for g in GAMES) + '\n')

    def tearDown(self):
        self.api.library.close()
        self.tmp.cleanup()

    def attach(self, name='Reference / Base'):
        return importers.attach_reference(self.api.library, self.pgn, name)

    def test_every_offset_opens_the_game_its_headers_describe(self):
        """The whole design rests on this: a byte offset that points at the right game."""
        result = self.attach()
        self.assertEqual(result['added'], len(GAMES))
        rows = self.api.library.connect().execute(
            'SELECT id,white,black,result,ply_count FROM games ORDER BY id').fetchall()
        for row, source in zip(rows, GAMES):
            text = self.api.library.game_pgn(row['id'])
            tags = pgnutil.headers(text)
            self.assertEqual(tags['White'], source[0])
            self.assertEqual(tags['Black'], source[1])
            self.assertEqual(tags['Result'], source[2])
            self.assertEqual(row['white'], source[0])
            self.assertEqual(len(pgnutil.moves(text)), row['ply_count'])

    def test_nothing_is_copied_and_the_path_is_relative_to_the_library(self):
        result = self.attach()
        self.assertEqual(result['path'], os.path.join('reference', 'Base.pgn'))
        collections = os.path.join(self.tmp.name, 'collections')
        copied = sum(os.path.getsize(os.path.join(root, f))
                     for root, _, files in os.walk(collections) for f in files)
        self.assertEqual(copied, 0)
        self.assertEqual(self.api.library.connect().execute(
            "SELECT COUNT(*) FROM games WHERE source='reference'").fetchone()[0], len(GAMES))

    def test_broadcast_urls_shared_by_several_games_do_not_collide(self):
        """Lumbras carries lichess broadcast URLs whose last segment names the round.

        Four games can quote the same one. source_id is the unique key for online
        imports, so a base must not claim it.
        """
        shared = '[Site "https://lichess.org/broadcast/-/-/ZGTi2AfJ"]'
        with open(self.pgn, 'w', encoding='utf-8') as handle:
            handle.write(GAP.join(
                pgn(*g).replace('[Site "?"]', shared) for g in GAMES) + '\n')
        result = self.attach()
        self.assertEqual(result['added'], len(GAMES))
        self.assertEqual(self.api.library.connect().execute(
            "SELECT COUNT(*) FROM games WHERE source_id IS NOT NULL").fetchone()[0], 0)

    def test_one_refused_game_does_not_cost_the_scan(self):
        """Ten million games from a stranger will contain something SQLite refuses."""
        library = self.api.library
        original = library.signature

        def signature(text):                  # collide the two Kramnik games on the
            return 'x' if 'Kramnik' in text else original(text)   # one unique column

        library.connect().execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS test_unique_signature ON games(signature)')
        library.signature = staticmethod(signature)
        with open(self.pgn, 'a', encoding='utf-8') as handle:     # a second Kramnik game
            handle.write(GAP + pgn('Kramnik, Vladimir', 'Leko, Peter', '1-0',
                                   '2004.10.02', 'C42', 'Brissago', '1. e4 e5 1-0'))
        try:
            result = importers.attach_reference(library, self.pgn, 'Reference / Base')
        finally:
            library.signature = original
            library.connect().execute('DROP INDEX IF EXISTS test_unique_signature')
        self.assertEqual(result['skipped'], 1)                    # the collision only
        self.assertEqual(result['added'], len(GAMES))             # everything else landed
        self.assertEqual(library.connect().execute(
            'SELECT COUNT(*) FROM games').fetchone()[0], len(GAMES))

    def test_a_scan_that_dies_before_committing_leaves_nothing(self):
        """A base with no games and no progress is a phantom, not something to resume."""
        original = pgnutil.describe
        seen = []

        def describe(text):
            seen.append(text)
            if len(seen) > 2:
                raise MemoryError('disk went away')
            return original(text)

        importers.pgnutil.describe = describe
        try:
            with self.assertRaises(MemoryError):
                importers.attach_reference(self.api.library, self.pgn, 'Reference / Base')
        finally:
            importers.pgnutil.describe = original
        self.assertEqual(self.api.library.connect().execute(
            'SELECT COUNT(*) FROM games').fetchone()[0], 0)
        self.assertEqual(self.api.library.references(), [])

    def test_attaching_the_same_file_twice_replaces_rather_than_doubles(self):
        """An interrupted scan is fixed by attaching again, not by hand."""
        first = self.attach()
        second = self.attach()
        self.assertEqual(second['added'], len(GAMES))
        self.assertEqual(second['collection_id'], first['collection_id'])
        self.assertEqual(self.api.library.connect().execute(
            'SELECT COUNT(*) FROM games').fetchone()[0], len(GAMES))
        self.assertEqual(len(self.api.library.references()), 1)

    def test_an_interrupted_scan_is_marked_unfinished(self):
        """Saying "240,000 games" without saying "so far" would be a lie."""
        # A scan that raises rolls itself back, so the half-done state is the one a
        # kill leaves: rows committed, the flag never set.
        importers.attach_reference(self.api.library, self.pgn, 'Reference / Base')
        self.assertTrue(self.api.library.references()[0]['complete'])
        self.api.library.connect().execute('UPDATE reference_bases SET complete=0')
        self.api.library.connect().commit()
        base = self.api.library.references()[0]
        self.assertFalse(base['complete'])
        self.assertEqual(base['games'], len(GAMES))
        again = importers.attach_reference(              # attaching again finishes it
            self.api.library, self.pgn, 'Reference / Base')
        self.assertEqual(again['added'], len(GAMES))
        self.assertTrue(self.api.library.references()[0]['complete'])

    def test_a_scan_can_be_stopped_and_picked_up_where_it_left_off(self):
        """Eight gigabytes is too much to start again because the machine got busy."""
        # A deadline already past stops after the first batch, one game at a time.
        first = importers.attach_reference(self.api.library, self.pgn, 'Reference / Base',
                                           batch_size=1, deadline=0)
        self.assertFalse(first['complete'])
        self.assertEqual(first['added'], 1)
        self.assertGreater(first['scanned_bytes'], 0)
        base = self.api.library.references()[0]
        self.assertFalse(base['complete'])
        self.assertEqual(base['games'], 1)

        passes, guard = 1, 0
        while not self.api.library.references()[0]['complete'] and guard < 20:
            out = importers.attach_reference(self.api.library, self.pgn, 'Reference / Base',
                                             batch_size=1, deadline=0, resume=True)
            passes += 1
            guard += 1
        self.assertTrue(self.api.library.references()[0]['complete'])
        self.assertGreater(passes, 1)                      # it really took several passes

        # Nothing lost, nothing counted twice, and every offset still points at its game.
        self.assertEqual(self.api.library.references()[0]['games'], len(GAMES))
        rows = self.api.library.connect().execute(
            'SELECT id, white, black FROM games ORDER BY byte_offset').fetchall()
        self.assertEqual([r['white'] for r in rows], [g[0] for g in GAMES])
        for row in rows:
            self.assertIn(row['black'], pgnutil.headers(self.api.library.game_pgn(row['id']))['Black'])

    def test_resuming_reports_how_far_through_the_file_it_is(self):
        importers.attach_reference(self.api.library, self.pgn, 'Reference / Base',
                                   batch_size=1, deadline=0)
        base = self.api.library.references()[0]
        self.assertGreater(base['scanned_pct'], 0)
        self.assertLess(base['scanned_pct'], 100)

    def test_a_base_reports_itself_and_notices_a_missing_file(self):
        self.attach()
        found = self.api.library.references()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['games'], len(GAMES))
        self.assertFalse(found[0]['missing'])
        os.rename(self.pgn, self.pgn + '.moved')
        self.assertTrue(self.api.library.references()[0]['missing'])

    def test_an_unattached_pgn_is_offered_and_stops_being_offered(self):
        self.assertEqual([a['name'] for a in self.api.library.attachable(minimum_bytes=1)], ['Base.pgn'])
        self.attach()
        self.assertEqual(self.api.library.attachable(minimum_bytes=1), [])

    def test_detaching_forgets_the_games_and_leaves_the_pgn(self):
        self.attach()
        size = os.path.getsize(self.pgn)
        out = importers.detach_reference(self.api.library, 'Reference / Base')
        self.assertEqual(out['deleted'], len(GAMES))
        self.assertEqual(os.path.getsize(self.pgn), size)
        self.assertEqual(self.api.library.connect().execute(
            'SELECT COUNT(*) FROM games').fetchone()[0], 0)

    def test_detaching_refuses_while_a_carved_collection_depends_on_it(self):
        """A carved collection links to the base's rows, so detaching would empty it."""
        self.attach()
        saved = self.api.library.collect_into('Masters / Carlsen', {'player': 'Carlsen, Magnus'}, 'games')
        self.assertEqual(saved['matched'], 2)
        with self.assertRaisesRegex(ValueError, r'Masters / Carlsen \(2 games\)'):
            importers.detach_reference(self.api.library, 'Reference / Base')
        self.assertEqual(self.api.library.connect().execute(
            'SELECT COUNT(*) FROM games').fetchone()[0], len(GAMES))   # nothing was deleted
        out = importers.detach_reference(self.api.library, 'Reference / Base', force=True)
        self.assertEqual(out['emptied'], ['Masters / Carlsen'])
        self.assertEqual(self.api.library.search(collection=saved['id'])['total'], 0)

    def test_extended_eco_codes_stay_inside_their_range(self):
        """Big bases write B90a and D13k. A three-letter range has to still mean itself."""
        self.attach()
        found = self.api.library.search(eco='B90', eco_to='B99')['games']
        self.assertEqual({g['eco'] for g in found}, {'B90a', 'B99'})
        single = self.api.library.search(eco='B90', eco_to='B90')['games']
        self.assertEqual([g['eco'] for g in single], ['B90a'])
        self.assertEqual(len(self.api.library.search(eco='A00', eco_to='E99')['games']), len(GAMES))

    def test_a_surname_is_matched_as_a_prefix_through_an_index(self):
        """The Masters field asks for a surname; a substring scan cannot survive 10M rows."""
        self.attach()
        library = self.api.library
        self.assertEqual(library.search(player_prefix='Carlsen')['total'], 2)
        self.assertEqual(library.search(player_prefix='carlsen')['total'], 2)   # forgiving case
        self.assertEqual(library.search(white_prefix='Carlsen')['total'], 1)
        self.assertEqual(library.search(black_prefix='Carlsen')['total'], 1)
        self.assertEqual(library.search(player_prefix='Carlsen, M')['total'], 2)
        self.assertEqual(library.search(player_prefix='Nobody')['total'], 0)
        self.assertEqual(library.search(event_prefix='World Champ')['total'], 2)

    def test_the_name_range_drives_the_plan_even_beside_an_eco_range(self):
        """Two ranges in one query, and SQLite reliably picks the wrong one.

        A whole-alphabet ECO range is every row, so the names have to be resolved first
        or a narrow search reads the entire base.
        """
        self.attach()
        found = self.api.library.search(player_prefix='Carlsen', eco='A00', eco_to='E99')
        self.assertEqual(found['total'], 2)
        sql = ("SELECT COUNT(*) FROM games WHERE id IN "
               "(SELECT id FROM games WHERE white>=? AND white<? "
               " UNION SELECT id FROM games WHERE black>=? AND black<?) AND eco>=? AND eco<?")
        steps = ' '.join(row[-1] for row in self.api.library.connect().execute(
            'EXPLAIN QUERY PLAN ' + sql,
            ('Carlsen', 'Carlsen\uffff', 'Carlsen', 'Carlsen\uffff', 'A00', 'E99\uffff')))
        self.assertIn('games_white', steps)
        self.assertIn('games_black', steps)

    def test_a_search_becomes_a_collection_that_shares_the_same_file(self):
        result = self.attach()
        saved = self.api.library.collect_into(
            'Masters / Carlsen Najdorf',
            {'player': 'Carlsen, Magnus', 'eco': 'B90', 'eco_to': 'B99'}, 'games')
        self.assertEqual(saved['matched'], 2)
        listed = self.api.library.search(collection=saved['id'])['games']
        self.assertEqual(len(listed), 2)
        for game in listed:                       # still readable, still out of the base
            self.assertIn('Carlsen', self.api.library.game_pgn(game['id']))
        self.assertEqual(self.api.library.references()[0]['games'], result['added'])

    def test_the_route_attaches_a_library_relative_path_and_shelves_it(self):
        status, payload = self.api.handle('POST', '/api/import/reference', {},
                                          {'path': 'reference/Base.pgn', 'collection': 'Reference / Base'})
        self.assertEqual(status, 200)
        self.assertEqual(payload['added'], len(GAMES))
        self.assertNotIn('folder_error', payload)
        folders = self.api.study.folders()
        shelf = [f for f in folders['folders'] if f['name'] == 'Reference']
        self.assertEqual(len(shelf), 1)
        self.assertIn(payload['collection_id'],
                      [a['collection_id'] for a in folders['assignments']])

    def test_the_masters_route_reports_what_is_attached(self):
        self.api.handle('POST', '/api/import/reference', {}, {'path': 'reference/Base.pgn'})
        status, payload = self.api.handle('GET', '/api/masters/references', {}, None)
        self.assertEqual(status, 200)
        self.assertEqual(payload['references'][0]['games'], len(GAMES))
        self.assertEqual(payload['folder'], 'reference')

    def test_an_archive_or_a_missing_file_is_refused_before_any_work(self):
        with self.assertRaisesRegex(ValueError, 'Extract archives first'):
            importers.attach_reference(self.api.library, __file__, 'X')   # a .py, not a .pgn
        with self.assertRaisesRegex(ValueError, 'No PGN at'):
            importers.attach_reference(self.api.library, 'reference/Nope.pgn', 'X')
        with self.assertRaises(ApiError):
            self.api.handle('POST', '/api/import/reference', {}, {'path': 'reference/Nope.pgn'})


if __name__ == '__main__':
    unittest.main()

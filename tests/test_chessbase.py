"""Reading, sorting and searching a ChessBase-exported PGN.

ChessBase differs from lichess in two ways that matter here: it writes the file in
the Windows code page rather than UTF-8, and it writes a much richer tag set.
"""
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from backend.api import Api
from backend import importers, pgnutil

# A game as ChessBase actually exports one: names without a space after the comma,
# team and title tags, a separate tournament date, and a source publication.
CHESSBASE_PGN = '''[Event "Bundesliga 2023"]
[Site "Berlin GER"]
[Date "2023.03.12"]
[Round "7.2"]
[White "Réti,Richard"]
[Black "Polgár,Judit"]
[Result "1/2-1/2"]
[WhiteElo "2680"]
[BlackElo "2735"]
[WhiteTitle "GM"]
[BlackTitle "GM"]
[WhiteTeam "Baden-Baden"]
[BlackTeam "Solingen"]
[WhiteFideId "1503014"]
[BlackFideId "700070"]
[EventDate "2023.03.10"]
[EventType "team-swiss"]
[SourceTitle "ChessBase Magazine 213"]
[ECO "B90"]
[Opening "Sicilian"]
[Variation "Najdorf, English attack"]
[PlyCount "6"]

1. e4 c5 2. Nf3 d6 1/2-1/2
'''


class ChessBaseEncodingTests(unittest.TestCase):
    def test_a_windows_encoded_file_keeps_its_accents(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'chessbase.pgn'
            path.write_bytes(CHESSBASE_PGN.encode('cp1252'))
            with importers.streams(str(path)) as stream:
                text = stream.read()
        self.assertIn('Réti', text)
        self.assertIn('Polgár', text)
        self.assertNotIn('�', text)

    def test_a_utf8_file_is_still_read_as_utf8(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'modern.pgn'
            path.write_text(CHESSBASE_PGN, encoding='utf-8')
            with importers.streams(str(path)) as stream:
                text = stream.read()
        self.assertIn('Réti', text)
        self.assertNotIn('�', text)

    def test_a_windows_encoded_pgn_inside_a_zip_keeps_its_accents(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'export.zip'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('games.pgn', CHESSBASE_PGN.encode('cp1252'))
            with importers.streams(str(path)) as stream:
                text = stream.read()
        self.assertIn('Polgár', text)
        self.assertNotIn('�', text)

    def test_the_sniffer_does_not_trip_over_a_character_split_by_the_sample_edge(self):
        # A two-byte character straddling the sample boundary is not evidence of cp1252.
        sample = ('a' * (importers.SNIFF_BYTES - 1)).encode('utf-8') + 'é'.encode('utf-8')[:1]
        self.assertEqual(importers.sniff_encoding(sample, more_follows=True), 'utf-8-sig')


class ChessBaseTagTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.api = Api(self.temp.name)
        self.call('POST', '/api/games', {'pgn': CHESSBASE_PGN, 'collection': 'ChessBase'})

    def tearDown(self):
        self.api.library.close()
        self.temp.cleanup()

    def call(self, method, path, body=None, query=None):
        return self.api.handle(method, path, query or {}, body)[1]

    def only(self, **query):
        return self.call('GET', '/api/games', query=query)

    def test_describe_reads_every_chessbase_tag(self):
        meta = pgnutil.describe(CHESSBASE_PGN)
        self.assertEqual(meta['white_team'], 'Baden-Baden')
        self.assertEqual(meta['black_team'], 'Solingen')
        self.assertEqual(meta['white_title'], 'GM')
        self.assertEqual(meta['white_fide_id'], '1503014')
        self.assertEqual(meta['event_date'], '2023.03.10')
        self.assertEqual(meta['event_type'], 'team-swiss')
        self.assertEqual(meta['source_title'], 'ChessBase Magazine 213')
        self.assertEqual(meta['variation'], 'Najdorf, English attack')

    def test_the_tags_reach_the_row_the_database_lists(self):
        game = self.only(kind='games')['games'][0]
        self.assertEqual(game['white_team'], 'Baden-Baden')
        self.assertEqual(game['black_title'], 'GM')
        self.assertEqual(game['variation'], 'Najdorf, English attack')
        self.assertEqual(game['event_date'], '2023.03.10')

    def test_team_title_and_fide_id_match_either_player(self):
        self.assertEqual(self.only(team='Solingen')['total'], 1)
        self.assertEqual(self.only(team='Baden')['total'], 1)
        self.assertEqual(self.only(title='GM')['total'], 1)
        self.assertEqual(self.only(fide_id='700070')['total'], 1)
        self.assertEqual(self.only(team='Hamburg')['total'], 0)

    def test_source_variation_and_event_type_are_searchable(self):
        self.assertEqual(self.only(source_title='ChessBase Magazine')['total'], 1)
        self.assertEqual(self.only(variation='Najdorf')['total'], 1)
        self.assertEqual(self.only(event_type='swiss')['total'], 1)

    def test_the_free_text_box_reaches_the_new_columns(self):
        self.assertEqual(self.only(q='Solingen')['total'], 1)
        self.assertEqual(self.only(q='English attack')['total'], 1)

    def test_the_tournament_date_filters_independently_of_the_game_date(self):
        self.assertEqual(self.only(event_date_from='2023-03-10')['total'], 1)
        self.assertEqual(self.only(event_date_from='2023-03-11')['total'], 0)
        self.assertEqual(self.only(event_date_to='2023-03-10')['total'], 1)

    def test_a_name_matches_whichever_way_the_comma_is_spaced(self):
        # The file says "Réti,Richard"; a reader will type it either way.
        self.assertEqual(self.only(player='Réti,Richard')['total'], 1)
        self.assertEqual(self.only(player='Réti, Richard')['total'], 1)
        self.assertEqual(self.only(white='Réti, Richard')['total'], 1)
        self.assertEqual(self.only(black='Polgár, Judit')['total'], 1)

    def test_the_new_sort_orders_are_accepted(self):
        for order in ('event_date', 'round', 'result', 'opening', 'eco', 'black'):
            self.assertEqual(self.only(sort=order)['total'], 1, order)

    def test_an_older_library_gains_the_columns_when_it_is_reopened(self):
        # Simulate a library written before these columns existed.
        library = self.api.library
        with library._write_lock, library.connect() as db:
            db.execute("UPDATE games SET white_team=NULL, event_date=NULL, variation=NULL")
            # Such a library predates the backfill marker as well as the columns.
            db.execute("DELETE FROM settings WHERE key LIKE 'backfill:%'")
        library.close()
        reopened = Api(self.temp.name)
        try:
            game = reopened.handle('GET', '/api/games', {'kind': 'games'}, None)[1]['games'][0]
            self.assertEqual(game['white_team'], 'Baden-Baden')
            self.assertEqual(game['event_date'], '2023.03.10')
        finally:
            reopened.library.close()
            self.api = reopened


if __name__ == '__main__':
    unittest.main()

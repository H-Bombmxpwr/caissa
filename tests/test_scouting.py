import tempfile
import unittest
from unittest.mock import Mock

from backend.api import Api, ApiError
from backend.chess import Chess
from backend.scouting import annotations, features


def game(white='Alice', black='Bob', result='1-0', date='2026.01.01', moves=None):
    return '\n'.join(['[Event "Rated blitz game"]', '[White "'+white+'"]', '[Black "'+black+'"]',
                      '[Result "'+result+'"]', '[Date "'+date+'"]', '[TimeControl "300+2"]',
                      '[WhiteElo "1600"]', '[BlackElo "1700"]', '',
                      moves or '{[%eval 0.20]} 1. e4 {[%eval -2.00] [%clk 0:04:52]} e5 {[%eval 1.00] [%clk 0:04:50]} 2. Nf3 {[%eval 1.00] [%clk 0:04:45]} Nc6 '+result])


class ScoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.api=Api(self.tmp.name)

    def tearDown(self):
        self.api.library.close()
        self.tmp.cleanup()

    def add(self, **kwargs):
        self.api.library.add_games(game(**kwargs), 'Tests')
        return self.api.library.connect().execute('SELECT MAX(id) FROM games').fetchone()[0]

    def report(self, **query):
        return self.api.handle('GET','/api/scouting',dict(player='Alice',**query),None)[1]

    def test_exact_names_perspective_and_missing_results(self):
        self.add()
        self.add(white='NotAlice', date='2026.01.02')
        self.add(white='Bob', black='Alice', result='0-1', date='2026.01.03')
        self.add(result='*', date='2026.01.04')
        report=self.report()
        self.assertEqual(report['baseline']['games'],2)
        self.assertEqual(report['baseline']['score_pct'],100)
        self.assertEqual(report['analyzed_games'],3)
        self.assertEqual(report['patterns'][0]['games'],2)
        self.assertTrue(report['patterns'][0]['small_sample'])
        self.assertEqual(self.report(color='b')['baseline']['games'],1)
        self.assertEqual(self.report(since='2026-01-03')['baseline']['games'],1)

    def test_eval_perspective_and_same_player_clocks(self):
        self.add()
        report=self.report()
        self.assertEqual(report['mistakes'][0]['loss'],220)
        self.assertEqual(report['mistakes'][0]['ply'],0)
        self.assertEqual(report['clocks']['measured_thinks'],2)
        self.assertEqual(report['clocks']['longest_thinks'][0]['spent'],10)
        black=self.api.scouting.report({'player':'Bob'})
        self.assertEqual(black['mistakes'][0]['loss'],300)

    def test_comments_variations_and_mates(self):
        nodes=annotations(game(moves='{[%eval 0.1]} 1. e4 {[%eval 0.2]} (1. d4 {[%eval -9]}) e5 {[%eval #3]} 2. Nf3'))
        self.assertEqual([n['san'] for n in nodes],[None,'e4','e5','Nf3'])
        self.assertEqual([n['cp'] for n in nodes],[10,20,None,None])

    def test_features(self):
        board=Chess('4k3/3p4/8/8/3P4/3P4/8/R3K2r w - - 0 35')
        phase,tags=features(board,'w')
        self.assertEqual(phase,'endgame')
        self.assertIn('Own isolated d-pawn',tags)
        self.assertIn('Own doubled pawns',tags)
        self.assertIn('Opposing isolated d-pawn',tags)
        self.assertIn('Rook ending',tags)

    def test_cache_invalidates_annotation_edit_and_cascades_delete(self):
        ident=self.add()
        self.report()
        db=self.api.library.connect()
        before=db.execute('SELECT digest FROM scouting_cache').fetchone()[0]
        self.api.library.replace_game(ident, game(moves='1. e4 e5 1-0'))
        self.assertEqual(self.report()['evaluated_games'],0)
        self.assertNotEqual(before,db.execute('SELECT digest FROM scouting_cache').fetchone()[0])
        with db:
            db.execute('DELETE FROM games WHERE id=?',(ident,))
        self.assertEqual(db.execute('SELECT COUNT(*) FROM scouting_cache').fetchone()[0],0)

    def test_review_schedule_and_server_checked_answer(self):
        ident=self.add()
        engine=Mock()
        engine.analyze.return_value={'bestmove':'d2d4'}
        self.api.scouting.create_drill({'player':'Alice','game_id':ident,'ply':0},engine)
        drill=self.api.scouting.drills('ALICE')[0]
        self.assertNotIn('solution',drill)
        out=self.api.scouting.review(drill['id'],{'move':'d4'})
        self.assertTrue(out['correct'])
        self.assertEqual(self.api.scouting.drills('Alice')[0]['successes'],1)
        with self.assertRaisesRegex(ValueError,'not due'):
            self.api.scouting.review(drill['id'],{'move':'d4'})
        db=self.api.library.connect()
        with db: db.execute('UPDATE scouting_drills SET due=0')
        self.assertFalse(self.api.scouting.review(drill['id'],{'move':'e4'})['correct'])
        self.assertEqual(self.api.scouting.drills('Alice')[0]['interval'],1)
        self.api.scouting.create_drill({'player':'Alice','game_id':ident,'ply':0},engine)
        self.assertEqual(len(self.api.scouting.drills('Alice')),1)

    def test_human_moves_rating_filter_and_repeat_deduplication(self):
        self.add(moves='1. Nf3 Nf6 2. Ng1 Ng8 3. e4 e5 1-0')
        collection=self.api.library.collection('Tests')
        self.api.study._index(collection['id'])
        data=self.api.scouting.human_moves({'min_elo':'1500','max_elo':'1650'})
        self.assertEqual(data['games'],1)
        self.assertEqual(data['moves'][0]['san'],'Nf3')
        self.assertEqual(self.api.scouting.human_moves({'min_elo':1800,'max_elo':1900})['games'],0)

    def test_bad_game_skipped_and_endpoint_validation(self):
        self.api.library.add_games(game(moves='1. e5 1-0').replace('[White', '[Opening "Unknown"]\n[White',1), 'Tests')
        self.assertEqual(len(self.report()['skipped']),1)
        with self.assertRaises(ApiError):
            self.api.handle('GET','/api/scouting',{},None)
        with self.assertRaises(ApiError):
            self.api.handle('DELETE','/api/scouting',{},None)

    def test_opening_transpositions_merge_but_distinct_choices_do_not(self):
        self.add(moves='1. Nf3 d5 2. g3 c5 3. Bg2 Nc6 4. O-O 1-0')
        self.add(date='2026.01.02', result='0-1', moves='1. g3 d5 2. Bg2 c5 3. Nf3 Nc6 4. O-O 0-1')
        self.add(date='2026.01.03', moves='1. Nf3 d5 2. g3 c5 3. Bg2 Nc6 4. d3 1-0')
        lines=self.report(min_games=2)['repertoire']
        self.assertEqual(len(lines),2)
        self.assertEqual(lines[0]['games'],2)
        self.assertEqual(lines[0]['score_pct'],50)
        self.assertEqual(lines[0]['frequency_pct'],66.7)

    def test_missing_clock_breaks_elapsed_sequence(self):
        self.add(moves='1. e4 {[%clk 0:04:50]} e5 2. Nf3 Nc6 3. Bc4 {[%clk 0:04:20]} Bc5 1-0')
        clocks=self.report()['clocks']
        self.assertEqual(clocks['moves'],2)
        self.assertEqual(clocks['measured_thinks'],1)

    def test_openings_are_named_per_colour_with_their_own_share(self):
        """What they open with, counted separately for each side of the board."""
        for n in range(4):
            self.add(date='2026.01.0%d' % (n + 1),
                     moves='1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6 1-0')
        self.add(white='Bob', black='Alice', result='0-1', date='2026.02.01',
                 moves='1. d4 Nf6 2. c4 g6 3. Nc3 Bg7 0-1')
        openings = self.report()['openings']
        white = [o for o in openings if o['color'] == 'w']
        black = [o for o in openings if o['color'] == 'b']
        self.assertEqual(len(white), 1)
        self.assertIn('Sicilian', white[0]['opening'])
        self.assertEqual(white[0]['games'], 4)
        self.assertEqual(white[0]['frequency_pct'], 100)     # all four of her White games
        self.assertEqual(white[0]['score_pct'], 100)
        self.assertEqual(white[0]['moves'][:2], ['e4', 'c5'])
        self.assertEqual(len(black), 1)
        self.assertEqual(black[0]['games'], 1)
        self.assertEqual(black[0]['score_pct'], 100)         # she won that one as Black

    def test_lines_carry_the_position_they_reach(self):
        """Every line the report offers has to be openable on a board."""
        for n in range(3):
            self.add(date='2026.01.0%d' % (n + 1),
                     moves='1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 0-1', result='0-1')
        line = self.report(min_games=2)['repertoire'][0]
        board = Chess(line['fen'])
        self.assertEqual(board.fen(), line['fen'])           # a legal, replayable position
        self.assertEqual(line['line'].split(), line['moves'])
        self.assertEqual(len(line['moves']), line['ply'])
        replayed = Chess()
        for san in line['moves']:
            self.assertTrue(replayed.move(san))
        self.assertEqual(replayed.fen(), line['fen'])

    def test_mistakes_point_at_the_position_before_the_move(self):
        ident = self.add(moves='{[%eval 0.20]} 1. e4 {[%eval 0.10]} e5 {[%eval 0.20]} '
                               '2. Nf3 {[%eval -4.00]} Nc6 1-0')
        mistake = self.report()['mistakes'][0]
        self.assertEqual(mistake['game_id'], ident)
        self.assertEqual(mistake['color'], 'w')
        board = Chess(mistake['fen'])
        self.assertTrue(board.move(mistake['san']))          # the move played is legal here
        self.assertEqual(mistake['ply'], 2)                  # two half-moves came before it

    def test_only_the_games_the_report_cites_travel_with_it(self):
        for n in range(6):
            self.add(date='2026.01.0%d' % (n + 1))
        report = self.report()
        cited = {i for group in ('patterns', 'repertoire', 'openings', 'weakest_lines')
                 for entry in report[group] for i in entry['evidence']}
        cited.update(m['game_id'] for m in report['mistakes'])
        cited.update(m['game_id'] for m in report['clocks']['longest_thinks'])
        self.assertTrue(cited)
        self.assertEqual({int(i) for i in report['games']}, cited)
        row = report['games'][cited.pop()]
        self.assertEqual(sorted(row),
                         ['black', 'color', 'date', 'eco', 'event', 'id', 'opening',
                          'opponent', 'opponent_elo', 'result', 'speed', 'white'])

    def test_wrong_player_cannot_create_drill(self):
        ident=self.add()
        with self.assertRaisesRegex(ValueError,'played by'):
            self.api.scouting.create_drill({'player':'Other','game_id':ident,'ply':0},Mock())


if __name__=='__main__':
    unittest.main()

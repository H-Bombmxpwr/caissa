import json
import tempfile
import unittest
from unittest.mock import patch
from backend import literature
from backend.api import Api


class FactsMatchingTests(unittest.TestCase):
    def page(self,title,extract):
        return dict(title=title,extract=extract,url='https://en.wikipedia.org/wiki/'+title.replace(' ','_'))

    def test_1959_candidates_rejects_1972_championship(self):
        pages={title:self.page(title,extract) for title,extract in [
            ('Bobby Fischer','An American chess player who played in 1972.'),
            ('Mikhail Tal','A chess grandmaster.'),
            ('Candidates Tournament 1959','The 1959 Candidates Tournament included Fischer and Tal.'),
            ('World Chess Championship 1972','Bobby Fischer won in 1972. He also played the 1959 Candidates against Tal.'),
            ('Unrelated game','Fischer and Tal played many games.'),
            ('Tal versus Fischer, 1959','Tal and Fischer met in 1959.')]}
        with patch.object(literature,'_wikipedia_search',return_value=list(pages)), \
             patch.object(literature,'_wikipedia',return_value=pages), \
             patch.object(literature,'gemini_note',return_value=None):
            data=literature.game_facts(dict(White='Fischer, Bobby',Black='Tal, Mikhail',Event='Candidates',Date='1959.09.??'))
        groups={g['label']:[p['title'] for p in g['items']] for g in data['groups']}
        self.assertEqual(groups['The players'],['Bobby Fischer','Mikhail Tal'])
        self.assertIn('Candidates Tournament 1959',groups['The event and place'])
        self.assertEqual(groups['Possibly about this game'],['Tal versus Fischer, 1959'])
        self.assertNotIn('World Chess Championship 1972',str(groups))

    def test_search_hit_requires_both_players_and_known_year(self):
        pages={'Some game':self.page('Some game','Fischer played a notable game in 1959.')}
        with patch.object(literature,'_wikipedia_search',return_value=list(pages)), \
             patch.object(literature,'_wikipedia',return_value=pages), \
             patch.object(literature,'gemini_note',return_value=None):
            for date in ['1959.01.01','0000.??.??']:
                data=literature.game_facts(dict(White='Fischer',Black='Tal',Date=date))
                self.assertEqual(data['groups'],[])

    def test_stale_recommendations_are_not_reused(self):
        with tempfile.TemporaryDirectory() as folder:
            api=Api(folder)
            try:
                headers=dict(White='Fischer',Black='Tal',Event='Candidates',Site='',Date='1959.01.01')
                api.library.setting('facts:'+json.dumps(headers,sort_keys=True),json.dumps({'groups':['wrong 1972 result']}))
                fresh={'groups':[],'message':'No verified match','query':{}}
                with patch.object(literature,'game_facts',return_value=fresh) as lookup:
                    _,data=api.handle('GET','/api/facts',{k.lower():v for k,v in headers.items()},None)
                self.assertEqual(data,fresh)
                lookup.assert_called_once()
            finally:
                api.library.close()

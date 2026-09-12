"""The auto-import card in Settings, driven end to end with lichess stubbed out.

Run with .venv/Scripts/python tests/autoimport_browser.py
"""
import os
from pathlib import Path
import sys
import tempfile
import threading
from functools import partial
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright

ACCOUNT = {'username': 'Ada', 'id': 'ada', 'title': None, 'url': 'https://lichess.org/@/Ada',
           'scopes': ['study:read'], 'can_read_studies': True}
GAMES = '\n\n'.join([
    '\n'.join(['[Event "rated blitz game"]', '[Site "https://lichess.org/abcd1234"]',
               '[White "Ada"]', '[Black "Bob"]', '[Result "1-0"]', '', '1. e4 e5 1-0']),
    '\n'.join(['[Event "rated blitz game"]', '[Site "https://lichess.org/efgh5678"]',
               '[White "Bob"]', '[Black "Ada"]', '[Result "0-1"]', '', '1. d4 d5 0-1']),
])

with tempfile.TemporaryDirectory(prefix='caissa-autoimport-') as data:
    os.environ['DATA_DIR'] = data
    import server
    server.Handler.log_message = lambda *a: None
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), partial(server.Handler, directory=str(ROOT)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = 'http://127.0.0.1:' + str(httpd.server_port)
    try:
        with patch('backend.lichess.account', return_value=dict(ACCOUNT)), \
             patch('backend.lichess.user_games', return_value=GAMES):
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel='msedge', headless=True)
                page = browser.new_page(viewport={'width': 1500, 'height': 1100})
                errors = []
                page.on('pageerror', lambda e: (errors.append(str(e)), print('Browser error:', e, flush=True)))
                page.goto(url)
                page.wait_for_function('window.Caissa')

                # Nothing on offer until an account is connected.
                page.evaluate('Caissa.go("settings")')
                page.wait_for_selector('input[aria-label="Personal access token"]')
                assert page.locator('.autoimport').count() == 0, 'offered without an account'

                page.fill('input[aria-label="Personal access token"]', 'lip_test')
                page.get_by_role('button', name='Connect account', exact=True).click()
                page.wait_for_selector('.autoimport')
                assert page.get_by_text('Off. Your games arrive only when you import them by hand.').count() == 1

                # The options appear only once it is switched on.
                assert page.locator('.autoimport select[aria-label="How often"]').is_visible() is False
                page.get_by_label('Import my games as they are played').check()
                page.wait_for_selector('.autoimport select[aria-label="How often"]', state='visible')
                page.wait_for_function(
                    '''()=>document.querySelector('.autoimport .status-message').textContent.includes('Watching')''')

                stored = page.evaluate('async()=>await Caissa.api("lichess/autoimport")')
                assert stored['enabled'] is True, stored
                assert stored['running'] is True, stored
                assert stored['collection'] == 'My lichess games', stored
                # Switching on starts from now: no decade of blitz for ticking a box.
                assert stored['since'], stored

                # Changing a setting persists it without a save button.
                page.locator('.autoimport select[aria-label="How often"]').select_option('60')
                page.fill('.autoimport input[aria-label="Collection"]', 'Blitz')
                page.locator('.autoimport input[aria-label="Collection"]').dispatch_event('change')
                page.get_by_label('Rated games only').check()
                page.wait_for_function(
                    '''async()=>{const s=await Caissa.api('lichess/autoimport');
                       return s.interval_minutes===60&&s.collection==='Blitz'&&s.rated_only===true;}''')

                # "Check now" imports and reports, and the games land in the collection.
                page.get_by_role('button', name='Check lichess now', exact=True).click()
                page.wait_for_function(
                    '''async()=>((await Caissa.api('games?'+new URLSearchParams({collection:'Blitz'}))).total)===2''')
                page.wait_for_function(
                    '''()=>document.querySelector('.autoimport .status-message').textContent.includes('2 games imported')''')

                # A second check finds nothing new rather than importing twice.
                page.get_by_role('button', name='Check lichess now', exact=True).click()
                page.wait_for_timeout(500)
                total = page.evaluate('''async()=>(await Caissa.api('games?'+new URLSearchParams({limit:1}))).total''')
                assert total == 2, total

                # The run is undoable like any other import.
                history = page.evaluate('async()=>await Caissa.api("import/history")')
                assert history['batches'][0]['label'] == 'Auto-import from lichess', history

                # Switching it off stops the watcher and hides the options again.
                page.get_by_label('Import my games as they are played').uncheck()
                page.wait_for_function('''async()=>{const s=await Caissa.api('lichess/autoimport');
                                          return s.enabled===false&&s.running===false;}''')
                assert page.locator('.autoimport select[aria-label="How often"]').is_visible() is False

                # Forgetting the token takes the whole card away with it.
                page.get_by_role('button', name='Forget this token', exact=True).click()
                page.wait_for_function('''()=>!document.querySelector('.autoimport')''')

                assert not errors, errors
                browser.close()
                print('PASS: auto-import settings, persistence, a real import, undo and teardown')
    finally:
        httpd.shutdown()
        server.api.autoimport.stop()
        server.api.library.close()

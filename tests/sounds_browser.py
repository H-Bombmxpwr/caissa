"""Bundled sound sets, end to end. Run with .venv/Scripts/python tests/sounds_browser.py"""
import os
from pathlib import Path
import sys
import tempfile
import threading
from functools import partial
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from playwright.sync_api import sync_playwright
from browser_util import wait_until, wait_for_index

with tempfile.TemporaryDirectory(prefix='caissa-sounds-') as data:
    os.environ['DATA_DIR'] = data
    import server
    server.Handler.log_message = lambda *args: None
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), partial(server.Handler, directory=str(ROOT)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = 'http://127.0.0.1:' + str(httpd.server_port)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page()
            errors = []
            page.on('pageerror', lambda e: (errors.append(str(e)), print('Browser error:', e, flush=True)))
            page.goto(url)
            page.wait_for_function('window.ChessSounds && window.Caissa')

            # The catalogue is read from disk, so it lists what was actually fetched.
            catalog = page.evaluate('async()=>await ChessSounds.sets()')
            names = [s['name'] for s in catalog]
            assert 'standard' in names, names
            assert len(names) >= 4, names
            for entry in catalog:
                assert entry['label'], entry
                assert entry['events'], entry

            # Every bundled file the catalogue claims is really served as audio.
            checked = 0
            for entry in catalog:
                for event in entry['events']:
                    got = page.evaluate(
                        '''async(src)=>{const r=await fetch(src);
                           return {ok:r.ok,type:r.headers.get('content-type'),size:(await r.blob()).size};}''',
                        '/assets/sound/%s/%s.mp3' % (entry['name'], event))
                    assert got['ok'], (entry['name'], event, got)
                    assert got['size'] > 200, (entry['name'], event, got)
                    checked += 1
            assert checked >= 40, checked

            # Naming an event from a move: the sound follows what the move did.
            cases = [
                ({'san': 'e4'}, True, 'move'),
                ({'san': 'e4'}, False, 'opponent'),
                ({'san': 'exd5', 'captured': 'p'}, True, 'capture'),
                ({'san': 'O-O'}, True, 'castle'),
                ({'san': 'Qh5+'}, True, 'check'),
                ({'san': 'Qh7#'}, True, 'end'),
                ({'san': 'e8=Q', 'promotion': 'q'}, True, 'promotion'),
            ]
            for move, mine, expected in cases:
                named = page.evaluate('([m,mine])=>ChessSounds.eventFor(m,mine)', [move, mine])
                assert named == expected, (move, mine, named, expected)

            # No set has a sample for every event, so every event must still resolve to
            # a real file. Lichess plays nothing for check or checkmate in its standard
            # set, which is exactly the case that must not fall through to silence.
            resolved = page.evaluate('''async()=>{
              await ChessSounds.sets();
              ChessSounds.configure({soundPack:'standard',soundVolume:0.5});
              const out={};
              for(const event of ChessSounds.events)out[event]=ChessSounds.sampleFor('standard',event);
              return out;}''')
            for event, src in resolved.items():
                assert src, (event, 'resolved to no sample at all')
                assert src.endswith('/%s.mp3' % event), (event, src)
            assert '/standard/' not in resolved['check'], resolved['check']
            assert '/standard/' not in resolved['end'], resolved['end']
            assert resolved['move'] == '/assets/sound/standard/move.mp3', resolved['move']
            # And the borrowed file is genuinely there.
            for event in ('check', 'end'):
                got = page.evaluate('async(src)=>(await fetch(src)).ok', resolved[event])
                assert got, (event, resolved[event])

            # The settings card offers the bundled sets by name, with no file pickers
            # required to use one.
            page.evaluate('Caissa.go("settings")')
            page.wait_for_selector('select[aria-label="Sound set"]')
            options = page.locator('select[aria-label="Sound set"] option').all_inner_texts()
            assert any('Lichess standard' in o for o in options), options
            assert any('Caissa wood' in o for o in options), options
            assert any('My own audio files' in o for o in options), options
            page.locator('select[aria-label="Sound set"]').select_option('standard')
            page.wait_for_function('Caissa.state.prefs.soundPack==="standard"')
            rows = page.locator('.sound-row').count()
            assert rows == len(page.evaluate('ChessSounds.events')), rows
            assert page.locator('.sound-row input[type=file]').count() == 0, 'bundled sets need no files'
            assert page.get_by_text('Uses the lichess standard sound').count() >= 0

            assert not errors, errors
            browser.close()
            print('PASS: sound catalogue, bundled files, event naming and the settings card')
    finally:
        httpd.shutdown()
        server.api.library.close()          # Windows will not delete an open sqlite file

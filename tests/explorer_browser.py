"""The opening explorer: walking a collection's tree and reading its numbers.

Run with .venv/Scripts/python tests/explorer_browser.py
"""
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


def game(white, black, result, moves, date='2024.01.01', tc='300+0'):
    return '\n'.join([
        '[Event "Rated blitz game"]', '[White "%s"]' % white, '[Black "%s"]' % black,
        '[Result "%s"]' % result, '[Date "%s"]' % date, '[TimeControl "%s"]' % tc,
        '[WhiteElo "1800"]', '[BlackElo "1750"]', '', '%s %s' % (moves, result)])


# Ada scores well with 1.e4 e5 and badly against the Sicilian.
PGN = '\n\n'.join(
    [game('Ada', 'Bob%d' % n, '1-0', '1. e4 e5 2. Nf3 Nc6 3. Bb5', date='2023.03.0%d' % (n + 1))
     for n in range(4)]
    + [game('Ada', 'Cy%d' % n, '0-1', '1. e4 c5 2. Nf3 d6 3. d4', date='2024.03.0%d' % (n + 1))
       for n in range(5)]
    + [game('Dee', 'Ada', '0-1', '1. d4 Nf6 2. c4 g6', date='2025.03.01', tc='600+0')]
)

with tempfile.TemporaryDirectory(prefix='caissa-explorer-') as data:
    os.environ['DATA_DIR'] = data
    import server
    server.Handler.log_message = lambda *a: None
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), partial(server.Handler, directory=str(ROOT)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = 'http://127.0.0.1:' + str(httpd.server_port)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page(viewport={'width': 1500, 'height': 1100})
            errors = []
            page.on('pageerror', lambda e: (errors.append(str(e)), print('Browser error:', e, flush=True)))
            page.goto(url)
            page.wait_for_function('window.Caissa')

            page.evaluate('''async(pgn)=>{
              await Caissa.api('games',{pgn,collection:'Mine'});
              const cols=await Caissa.api('collections');
              const mine=cols.collections.find(c=>c.name==='Mine');
              await Caissa.api('study/index',{collection:mine.id});}''', PGN)
            wait_until(page, 
                '''async()=>{const s=await Caissa.api('study/index');
                   return !s.running&&s.total>0&&s.done===s.total;}''')

            # The explorer opens on the collection tree, not on a reference database.
            page.evaluate('Caissa.go("openingbook")')
            page.wait_for_selector('.context-tabs button.active')
            assert page.locator('.context-tabs button.active').inner_text() == 'Collection tree'

            # Name the player and the numbers become theirs.
            page.fill('input[aria-label="Player"]', 'Ada')
            page.locator('input[aria-label="Player"]').dispatch_event('change')
            page.wait_for_selector('.tree-move')
            report = page.evaluate(
                '''async()=>await Caissa.api('tree/position?'+new URLSearchParams({player:'Ada'}))''')
            assert report['totals']['games'] == 10, report['totals']
            assert report['totals']['wins'] == 5, report['totals']
            assert report['totals']['losses'] == 5, report['totals']
            assert report['perspective'] == 'player'

            score = page.locator('.tree-score strong').inner_text()
            assert score == '50.0%', score
            moves = page.locator('.tree-move .tree-san').all_inner_texts()
            assert moves[:2] == ['e4', 'd4'], moves     # ordered by how often they were played

            # Walking the tree: click a move and the report follows the board.
            page.get_by_role('button', name='e4', exact=True).click()
            page.wait_for_function(
                '''()=>document.querySelector('.tree-path')&&
                       document.querySelector('.tree-path').textContent.includes('e4')''')
            # Most played first: Ada met 1...c5 five times and 1...e5 four.
            page.wait_for_function(
                '''()=>[...document.querySelectorAll('.tree-move .tree-san')]
                        .map(b=>b.textContent).join()==='c5,e5' ''')
            after = page.evaluate('''async()=>await Caissa.api('tree/position?'+new URLSearchParams(
                {player:'Ada',fen:'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1'}))''')
            by_san = {m['san']: m for m in after['moves']}
            assert by_san['e5']['score_pct'] == 100.0, by_san['e5']
            assert by_san['c5']['score_pct'] == 0.0, by_san['c5']

            # The breadcrumb steps back to any earlier point in the line.
            page.get_by_role('button', name='c5', exact=True).click()
            page.wait_for_function(
                '''()=>document.querySelector('.tree-path').textContent.includes('c5')''')
            page.locator('.tree-path .linkish').first.click()
            page.wait_for_function(
                '''()=>document.querySelector('.tree-path').textContent.trim().replace(/\\s+/g,' ')==='1.e4' ''')

            # Filters narrow it, and a colour filter is read from the named player.
            black_only = page.evaluate('''async()=>await Caissa.api('tree/position?'+
                new URLSearchParams({player:'Ada',color:'b'}))''')
            assert black_only['totals']['games'] == 1, black_only['totals']
            assert black_only['totals']['wins'] == 1, black_only['totals']
            rapid = page.evaluate('''async()=>await Caissa.api('tree/position?'+
                new URLSearchParams({player:'Ada',speed:'rapid'}))''')
            assert rapid['totals']['games'] == 1, rapid['totals']

            # The trend is per year, and the year Ada met the Sicilian is the bad one.
            trend = {t['period']: t['score_pct'] for t in report['trend']}
            assert trend == {'2023': 100.0, '2024': 0.0, '2025': 100.0}, trend

            # The weakest list names the line that cost the points.
            weakest = page.evaluate('''async()=>await Caissa.api('tree/weakest?'+
                new URLSearchParams({player:'Ada',min_games:'3'}))''')
            assert weakest['weakest'], weakest
            worst = weakest['weakest'][0]
            assert worst['score_pct'] == 0.0, worst
            assert '1.e4' in worst['line'], worst
            assert worst['moves'][0] == 'e4', worst

            # Clicking one puts that line on the board.
            page.locator('.tree-weak .linkish').first.click()
            page.wait_for_function(
                '''()=>document.querySelector('.tree-path').textContent.includes('c5')''')

            # Arrow keys walk the tree without the mouse.
            page.locator('.key-hint').click()
            page.keyboard.press('Home')
            # Wait for the report to catch up with the board before pressing a key:
            # the handler deliberately ignores a list that belongs to another position.
            page.wait_for_function('''()=>!document.querySelector('.tree-path')''')
            page.wait_for_function(
                '''()=>[...document.querySelectorAll('.tree-move .tree-san')]
                        .map(b=>b.textContent).join()==='e4,d4' ''')
            page.keyboard.press('ArrowRight')            # most played continuation: 1.e4
            page.wait_for_function(
                '''()=>document.querySelector('.tree-path')&&
                       document.querySelector('.tree-path').textContent.includes('e4')''')
            page.wait_for_function(
                '''()=>[...document.querySelectorAll('.tree-move .tree-san')]
                        .map(b=>b.textContent).join()==='c5,e5' ''')
            page.keyboard.press('ArrowDown')             # pick the second continuation
            page.wait_for_selector('.tree-move.chosen')
            chosen=page.locator('.tree-move.chosen .tree-san').inner_text()
            assert chosen=='e5',chosen                   # c5 is first, e5 second
            page.keyboard.press('ArrowRight')
            page.wait_for_function(
                '''()=>document.querySelector('.tree-path').textContent.includes('e5')''')
            page.keyboard.press('ArrowLeft')
            page.wait_for_function(
                '''()=>!document.querySelector('.tree-path').textContent.includes('e5')''')

            # Changing the collection re-reads everything that depends on it.
            page.evaluate('''async(pgn)=>{
              await Caissa.api('games',{pgn,collection:'Elsewhere'});
              const cols=await Caissa.api('collections');
              await Caissa.api('study/index',{collection:cols.collections.find(c=>c.name==='Elsewhere').id});}''',
                          game('Zoya', 'Quinn', '1-0', '1. c4 e5'))
            wait_until(page, 
                '''async()=>{const s=await Caissa.api('study/index');
                   return !s.running&&s.total>0&&s.done===s.total;}''')
            page.evaluate('Caissa.go("database")')
            page.evaluate('Caissa.go("openingbook")')
            page.wait_for_selector('input[aria-label="Player"]')
            page.fill('input[aria-label="Player"]', 'Ada')
            page.locator('input[aria-label="Player"]').dispatch_event('change')
            page.wait_for_selector('.tree-move')
            names=lambda: page.evaluate(
                '''()=>[...document.querySelectorAll('#tree-player-names option')].map(o=>o.value)''')
            assert 'Ada' in names(),names()
            elsewhere=page.evaluate('''async()=>{const c=await Caissa.api('collections');
                return String(c.collections.find(x=>x.name==='Elsewhere').id);}''')
            page.locator('select[aria-label="Collection"]').first.select_option(elsewhere)
            # The suggestions follow the collection...
            page.wait_for_function(
                '''()=>{const o=[...document.querySelectorAll('#tree-player-names option')].map(x=>x.value);
                        return o.includes('Zoya')&&!o.includes('Ada');}''')
            # ...and a player with no games there is cleared rather than left reporting zero.
            page.wait_for_function('''()=>!document.querySelector('input[aria-label="Player"]').value''')

            # Flipping the board sticks, including after leaving and returning.
            def bottom_left():
                return page.evaluate(
                    '''()=>document.querySelector('.opening-grid .cg-board square')
                           .getAttribute('data-key')''')
            first=bottom_left()
            page.get_by_role('button',name='Flip board',exact=True).click()
            page.wait_for_function('(was)=>document.querySelector(".opening-grid .cg-board square")'
                                   '.getAttribute("data-key")!==was',arg=first)
            flipped=bottom_left()
            assert {first,flipped}=={'a8','h1'},(first,flipped)
            page.wait_for_function('()=>Caissa.state.prefs.explorerOrientation==="b"')
            page.evaluate('Caissa.go("database")')
            page.evaluate('Caissa.go("openingbook")')
            page.wait_for_selector('.opening-grid .cg-board square')
            assert bottom_left()==flipped,'the flip did not survive leaving the module'

            # The report describes whoever is named, not the reader.
            page.wait_for_selector('input[aria-label="Player"]')
            blurb=page.locator('.context-tabs ~ div p.muted').first.inner_text()
            assert 'Your games' not in blurb,blurb
            assert 'One player' in blurb,blurb

            # The reference tab still works, and going back returns to the tree.
            page.get_by_role('button', name='Reference databases', exact=True).click()
            page.wait_for_selector('select[aria-label="Reference database"]')
            page.get_by_role('button', name='Collection tree', exact=True).click()
            page.wait_for_selector('.tree-move')

            assert not errors, errors
            browser.close()
            print('PASS: explorer opens on the tree, scores from the player, walks, filters, '
                  'trends, and names the weakest lines')
    finally:
        httpd.shutdown()
        server.api.autoimport.stop()
        server.api.library.close()

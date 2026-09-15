"""End-to-end report, saved practice, keyboard board and rating checks with Edge."""
import os
import re
from pathlib import Path
import sys
import tempfile
import threading
from functools import partial
from http.server import ThreadingHTTPServer

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory(prefix='caissa-scout-') as data:
    os.environ['DATA_DIR']=data
    import server
    server.Handler.log_message=lambda *args:None
    httpd=ThreadingHTTPServer(('127.0.0.1',0),partial(server.Handler,directory=str(ROOT)))
    threading.Thread(target=httpd.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='msedge',headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1000})
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.route('**/api/lichess/account',lambda route:route.fulfill(json={'connected':True,'username':'Alice'}))
            page.goto('http://127.0.0.1:'+str(httpd.server_port))
            page.wait_for_function('window.Caissa')
            page.evaluate('''async()=>{
              await Caissa.api('games',{pgn:'[Event "Test"]\\n[White "Alice"]\\n[Black "Bob"]\\n[Result "1-0"]\\n[TimeControl "300+2"]\\n\\n{[%eval 0.2]} 1. e4 {[%eval -2.0] [%clk 0:04:52]} e5 {[%eval 0]} 2. Nf3 Nc6 1-0'});
              await Caissa.go('scouting');
            }''')
            from playwright.sync_api import expect
            player=page.get_by_label('Player',exact=True)
            # Opponent prep leads, because scouting somebody else is the obvious use.
            expect(page.get_by_label('Report',exact=True)).to_have_value('opponent')
            expect(player).to_have_value('')
            expect(page.locator('.mode-purpose')).to_contain_text('Preparing against someone')
            player.fill('Bob')
            page.get_by_label('Report',exact=True).select_option('self')
            expect(player).to_have_value('Alice')
            expect(page.locator('.mode-purpose')).to_contain_text('Reviewing your own play')
            page.get_by_label('Report',exact=True).select_option('opponent')
            expect(player).to_have_value('Bob')
            page.get_by_label('Report',exact=True).select_option('self')
            expect(player).to_have_value('Alice')
            page.get_by_label('Games',exact=True).select_option('chesscom')
            expect(player).to_have_value('Alice')
            expect(page.get_by_label('How many games',exact=True)).to_be_visible()
            page.get_by_label('Games',exact=True).select_option('lichess')
            expect(player).to_have_value('Alice')
            page.get_by_label('Games',exact=True).select_option('local')
            expect(player).to_have_value('Alice')
            expect(page.get_by_label('How many games',exact=True)).to_be_hidden()
            player.fill('Local Alias')
            page.evaluate("CaissaAccount.set({connected:true,username:'NewHandle'})")
            expect(player).to_have_value('Local Alias')
            page.get_by_label('Report',exact=True).select_option('opponent')
            expect(player).to_have_value('Bob')
            page.get_by_label('Report',exact=True).select_option('self')
            expect(player).to_have_value('Local Alias')
            player.fill('Alice')
            page.get_by_role('button',name='Build report',exact=True).click()
            page.get_by_role('heading',name='Scouting report: Alice').wait_for()
            assert '220 centipawns lost' in page.locator('.scouting-report').inner_text()
            assert '1 completed games' in page.locator('.scouting-report').inner_text()
            # One run, and the whole report is there — including the boards behind it.
            expect(page.get_by_role('heading',name='What they open with')).to_be_visible()
            expect(page.get_by_role('heading',name='Mistakes to revisit')).to_be_visible()
            assert 'What people at a rating' not in page.locator('.scouting-report').inner_text()
            thumbs=page.locator('.scout-thumb')
            assert thumbs.count(), 'every claim in the report carries its board'
            assert page.locator('.scout-thumb .cg-board').count()==thumbs.count(), \
                'thumbnails are drawn on arrival, not when something else happens first'
            assert page.locator('.evidence-list .linkish').first.inner_text().startswith('Alice')
            printed=page.pdf(format='A4')
            assert len(re.findall(rb'/Type\s*/Page\b',printed))==1, 'Prep sheet must fit one page for this fixture'
            page.get_by_role('button',name='Create practice position',exact=True).click()
            page.get_by_label('Your move',exact=True).wait_for()
            page.get_by_label('Your move',exact=True).fill('d4')
            page.get_by_role('button',name='Check move',exact=True).click()
            page.wait_for_function("document.querySelector('.scouting-drill input[disabled]')")
            # The explorer is handed the player the report was about.
            page.get_by_role('button',name='Open in the opening explorer',exact=True).click()
            page.wait_for_selector('.opening-grid')
            expect(page.get_by_label('Player',exact=True)).to_have_value('Alice')
            expect(page.locator('.book-arrow-controls')).to_be_visible()
            page.evaluate("async()=>await Caissa.go('scouting')")
            page.get_by_label('Player',exact=True).fill('Alice')
            page.get_by_role('button',name='Build report',exact=True).click()
            page.get_by_role('heading',name='Scouting report: Alice').wait_for()
            # Open evidence and exercise the real board input.
            page.locator('.evidence-list .linkish').first.click()
            page.wait_for_selector('.analysis-board')
            page.screenshot(path=str(ROOT/'tmp'/'scouting-analysis.png'))
            wrap=page.locator('.analysis-board .cg-wrap')
            wrap.focus()
            page.keyboard.press('ArrowRight')
            assert 'b1 white knight' in page.locator('.analysis-board .board-access').inner_text()
            page.get_by_role('button',name='Read position',exact=True).filter(visible=True).first.click()
            assert 'White to move' in page.locator('.analysis-board .board-access').inner_text()
            page.get_by_label('Move in SAN').fill('d4')
            page.get_by_role('button',name='Play move',exact=True).click()
            assert 'd4' in page.locator('.move-tree button.current').inner_text()
            page.evaluate("async()=>{Caissa.state.dirty=false;await Caissa.go('training');}")
            page.evaluate("App.stat('l1',{asked:1,right:1})")
            assert '1 attempts (experimental)' in page.locator('#visualization-rating').inner_text()
            for level in ['openings','analyze']:
                page.evaluate('(level)=>App.go(level)',level)
                expect(page.get_by_placeholder('lichess username',exact=True)).to_have_value('NewHandle')
            page.evaluate("async()=>await Caissa.go('imports')")
            username=page.get_by_label('Username',exact=True)
            expect(username).to_have_value('NewHandle')
            page.get_by_label('Service',exact=True).select_option('chesscom')
            expect(username).to_have_value('')
            page.get_by_label('Service',exact=True).select_option('lichess')
            expect(username).to_have_value('NewHandle')
            page.evaluate("CaissaAccount.set({connected:false})")
            expect(username).to_have_value('')
            assert not errors,errors
            browser.close()
            print('Scouting browser checks passed')
    finally:
        httpd.shutdown()
        httpd.server_close()
        server.api.engine.stop()
        server.api.library.close()


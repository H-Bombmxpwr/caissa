"""Interactive repertoire drills: board sizing, moves, orientation, optional blindfold and review persistence."""
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

with tempfile.TemporaryDirectory(prefix='caissa-repertoire-') as data:
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
            from playwright.sync_api import expect
            page.goto('http://127.0.0.1:'+str(httpd.server_port))
            page.wait_for_function('window.Caissa')
            rep_id=page.evaluate("""async()=>{
                const result=await Caissa.api('repertoires',{name:'Black practice',color:'b',data:{lines:[{fen:Chess.DEFAULT_FEN,moves:['e4','e5','Nf3','Nc6'],successes:2}]}});
                await Caissa.go('repertoire');return result.id;
            }""")
            page.get_by_role('button',name='Drill due lines',exact=True).click()
            board=page.locator('.repertoire-drill-board')
            assert board.bounding_box()['width']>=450
            expect(page.get_by_role('checkbox',name='Blindfold mode (optional)',exact=True)).not_to_be_checked()
            assert board.locator('.cg-coords').inner_text().startswith('h')
            expect(page.get_by_label('Moves played',exact=True)).to_have_text('1. e4 ')
            def square(key):
                box=board.locator('square[data-key="'+key+'"]').bounding_box()
                return box['x']+box['width']/2,box['y']+box['height']/2
            def play_move(start,end,drag=False):
                x,y=square(start);page.mouse.move(x,y)
                if drag:
                    page.mouse.down();page.mouse.move(*square(end),steps=8);page.mouse.up()
                else:
                    page.mouse.click(x,y);page.mouse.click(*square(end))
            play_move('c7','c5')
            page.get_by_text('That is not the saved move. Try again.',exact=True).wait_for()
            expect(page.get_by_label('Moves played',exact=True)).to_have_text('1. e4 ')
            play_move('e7','e5',True)
            expect(page.get_by_label('Moves played',exact=True)).to_contain_text('2. Nf3')
            play_move('b8','c6')
            page.get_by_role('heading',name='Line complete',exact=True).wait_for()
            page.get_by_role('button',name='Save review',exact=True).click()
            page.get_by_role('button',name='Change side',exact=True).click()
            page.get_by_label('Repertoire color',exact=True).select_option('w')
            page.get_by_role('button',name='Save side',exact=True).click()
            page.get_by_role('button',name='Browse lines',exact=True).click()
            page.get_by_role('button',name='Drill',exact=True).click()
            board=page.locator('.repertoire-drill-board')
            assert board.locator('.cg-coords').inner_text().startswith('a')
            expect(page.get_by_label('Moves played',exact=True)).to_be_empty()
            page.get_by_role('checkbox',name='Blindfold mode (optional)',exact=True).check()
            expect(page.get_by_role('button',name='Peek',exact=True)).to_be_visible()
            page.get_by_role('checkbox',name='Blindfold mode (optional)',exact=True).uncheck()
            play_move('e2','e4',True)
            expect(page.get_by_label('Moves played',exact=True)).to_contain_text('1... e5')
            page.screenshot(path=str(ROOT/'tmp'/'repertoire-drill.png'))
            page.get_by_label('Drill board size',exact=True).evaluate("el=>{el.value='400';el.dispatchEvent(new Event('input',{bubbles:true}));}")
            assert board.bounding_box()['width']<=401
            page.set_viewport_size({'width':390,'height':844})
            assert board.bounding_box()['width']<=390
            assert not errors,errors
            browser.close()
            print('Interactive repertoire drill browser checks passed')
    finally:
        httpd.shutdown()
        httpd.server_close()
        server.api.engine.stop()
        server.api.library.close()


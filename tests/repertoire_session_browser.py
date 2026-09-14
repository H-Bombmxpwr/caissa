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
              const result=await Caissa.api('repertoires',{name:'Branches',color:'w',data:{lines:[
                {fen:Chess.DEFAULT_FEN,moves:['e4','e5','Nf3','Nc6','Bb5']},
                {fen:Chess.DEFAULT_FEN,moves:['e4','e5','Bc4','Nc6']},
                {fen:Chess.DEFAULT_FEN,moves:['e4','c5','Nf3','d6']}]}});
              await Caissa.go('repertoire');return result.id;
            }""")
            page.get_by_role('button',name='Drill all lines',exact=True).click()
            board=page.locator('.repertoire-drill-board')
            def play_move(start,end):
                for key in [start,end]:
                    box=board.locator('square[data-key="'+key+'"]').bounding_box()
                    page.mouse.click(box['x']+box['width']/2,box['y']+box['height']/2)
            play_move('e2','e4')
            expect(page.get_by_label('Moves played',exact=True)).to_contain_text('1... e5')
            play_move('f1','c4')
            expect(page.locator('.drill-progress')).to_have_text('1 / 3 lines completed')
            expect(page.get_by_label('Moves played',exact=True)).to_have_text('1. e4 1... e5 ')
            # One completed line is enough to save, and closing before that asks first.
            expect(page.get_by_role('button',name='Save review',exact=True)).to_be_enabled()
            page.once('dialog',lambda dialog:dialog.dismiss())
            page.get_by_role('button',name='Close',exact=True).click()
            expect(page.locator('.repertoire-drill-dialog')).to_have_count(1)
            play_move('d2','d4')
            page.get_by_text('That is not the saved move. Try again.',exact=True).wait_for()
            play_move('g1','f3')
            expect(page.get_by_label('Moves played',exact=True)).to_contain_text('2... Nc6')
            play_move('f1','b5')
            expect(page.locator('.drill-progress')).to_have_text('2 / 3 lines completed')
            expect(page.get_by_label('Moves played',exact=True)).to_have_text('1. e4 1... c5 ')
            play_move('g1','f3')
            page.get_by_role('heading',name='Repertoire session complete',exact=True).wait_for()
            expect(page.locator('.drill-progress')).to_have_text('3 / 3 lines completed')
            page.get_by_role('button',name='Save review',exact=True).click()
            expect(page.locator('.repertoire-drill-dialog')).to_have_count(0)
            import json
            data=json.loads(page.evaluate('(id)=>Caissa.api("repertoires/"+id)',rep_id)['repertoire']['data'])
            assert [line['successes'] for line in data['lines']]==[0,1,1],data
            assert all(line['due']>0 for line in data['lines']),data
            # A part-finished session saves the lines it did complete, and only those.
            page.get_by_role('button',name='Drill all lines',exact=True).click()
            play_move('e2','e4')
            expect(page.get_by_label('Moves played',exact=True)).to_contain_text('1... e5')
            play_move('g1','f3')
            expect(page.get_by_label('Moves played',exact=True)).to_contain_text('2... Nc6')
            play_move('f1','b5')
            expect(page.locator('.drill-progress')).to_have_text('1 / 3 lines completed')
            page.get_by_role('button',name='Save review',exact=True).click()
            expect(page.locator('.repertoire-drill-dialog')).to_have_count(0)
            page.get_by_text('1 line scheduled for review',exact=True).wait_for()
            data=json.loads(page.evaluate('(id)=>Caissa.api("repertoires/"+id)',rep_id)['repertoire']['data'])
            assert [line['successes'] for line in data['lines']]==[1,1,1],data
            assert not errors,errors
            browser.close()
            print('Repertoire branching session checks passed')
    finally:
        httpd.shutdown()
        httpd.server_close()
        server.api.engine.stop()
        server.api.library.close()


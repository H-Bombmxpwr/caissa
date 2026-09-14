"""Repertoire rename, line deletion, cancellation and persistence checks with Edge."""
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
              const fen=Chess.DEFAULT_FEN;
              const result=await Caissa.api('repertoires',{name:'Original',color:'b',data:{note:'keep',lines:[
                {fen,moves:['e4','e5'],due:123,successes:3},
                {fen,moves:['e4','c5'],due:456,successes:7}]}});
              await Caissa.go('repertoire');return result.id;
            }""")
            page.get_by_role('button',name='View repertoire',exact=True).click()
            page.wait_for_selector('.analysis-board')
            assert page.evaluate("Caissa.state.parsed.root.children.length") == 1
            assert page.evaluate("Caissa.state.parsed.root.children[0].children.map(n=>n.san)") == ['e5','c5']
            page.get_by_role('button',name='Last move',exact=True).click()
            page.get_by_role('button',name='Add to repertoire',exact=True).click()
            expect(page.get_by_label('New repertoire name',exact=True)).to_be_visible()
            page.get_by_label('Repertoire',exact=True).select_option(str(rep_id))
            expect(page.get_by_label('New repertoire name',exact=True)).to_be_hidden()
            expect(page.get_by_label('Play as',exact=True)).to_be_hidden()
            page.get_by_label('Repertoire',exact=True).select_option('')
            expect(page.get_by_label('New repertoire name',exact=True)).to_be_visible()
            page.get_by_role('button',name='Cancel',exact=True).click()
            page.evaluate("async()=>await Caissa.go('repertoire')")
            page.get_by_role('button',name='Rename',exact=True).click()
            page.get_by_label('Repertoire name',exact=True).fill('Sicilian practice')
            page.get_by_role('button',name='Save name',exact=True).click()
            page.get_by_role('heading',name='Sicilian practice',exact=True).wait_for()
            page.get_by_role('button',name='Browse lines',exact=True).click()
            page.get_by_label('Select line 1',exact=True).check()
            page.get_by_role('button',name='Delete 1 selected lines',exact=True).click()
            page.get_by_role('button',name='Browse lines',exact=True).wait_for()
            saved=page.evaluate('(id)=>Caissa.api("repertoires/"+id)',rep_id)['repertoire']
            import json
            result=json.loads(saved['data'])
            assert saved['name']=='Sicilian practice' and saved['color']=='b',saved
            assert result['note']=='keep' and len(result['lines'])==1,result
            assert result['lines'][0]['moves']==['e4','c5'] and result['lines'][0]['successes']==7,result
            page.get_by_role('button',name='Browse lines',exact=True).click()
            page.get_by_label('Select line 1',exact=True).check()
            page.get_by_role('button',name='Close',exact=True).click()
            saved=page.evaluate('(id)=>Caissa.api("repertoires/"+id)',rep_id)['repertoire']
            assert len(json.loads(saved['data'])['lines'])==1
            page.get_by_role('button',name='Browse lines',exact=True).click()
            page.get_by_label('Select line 1',exact=True).check()
            page.get_by_role('button',name='Delete 1 selected lines',exact=True).click()
            page.get_by_role('button',name='Browse lines',exact=True).click()
            page.get_by_text('No saved lines. Add a line from analysis or import a repertoire PGN.',exact=True).wait_for()
            assert not errors,errors
            browser.close()
            print('Repertoire editing browser checks passed')
    finally:
        httpd.shutdown()
        httpd.server_close()
        server.api.engine.stop()
        server.api.library.close()


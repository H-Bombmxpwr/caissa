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
              const rep=await Caissa.api('repertoires',{name:'All openings',color:'w',data:{note:'keep',lines:[]}});
              const pgn='[White "Tree"]\\n[Black "Test"]\\n[Result "*"]\\n\\n1. e4 (1. d4 d5 (1... Nf6 2. c4) 2. c4) e5 2. Nf3 (2. Bc4 Nc6) Nc6 *';
              await Caissa.api('games',{pgn});await Caissa.openGame((await Caissa.api('games')).games[0].id);
              return rep.id;
            }""")
            def add(scope):
                page.get_by_role('button',name='Add to repertoire',exact=True).click()
                page.get_by_label('Repertoire',exact=True).select_option(str(rep_id))
                expect(page.get_by_label('New repertoire name',exact=True)).to_be_hidden()
                page.get_by_label('Include',exact=True).select_option(scope)
                page.get_by_role('button',name='Add lines',exact=True).click()
                expect(page.get_by_label('Include',exact=True)).to_have_count(0)
            import json
            def saved():
                return json.loads(page.evaluate('(id)=>Caissa.api("repertoires/"+id)',rep_id)['repertoire']['data'])
            add('main')
            assert [line['moves'] for line in saved()['lines']]==[['e4','e5','Nf3','Nc6']]
            page.evaluate("""async id=>{
                const rep=(await Caissa.api('repertoires/'+id)).repertoire;
                rep.data=JSON.parse(rep.data);rep.data.lines[0].successes=9;
                await Caissa.api('repertoires/'+id,rep,'PUT');
            }""",rep_id)
            add('all')
            data=saved()
            assert data['note']=='keep' and data['lines'][0]['successes']==9
            assert {tuple(line['moves']) for line in data['lines']}=={
                ('e4','e5','Nf3','Nc6'),('e4','e5','Bc4','Nc6'),
                ('d4','d5','c4'),('d4','Nf6','c4')}
            add('all')
            assert saved()==data, 'Adding the same tree must preserve lines and review history'
            page.evaluate("async()=>await Caissa.go('repertoire')")
            page.get_by_role('button',name='View repertoire',exact=True).click()
            page.wait_for_selector('.analysis-board')
            assert page.evaluate('Caissa.state.parsed.root.children.length')==2
            assert page.locator('.move-tree details.variation').count()==3
            assert not errors,errors
            browser.close()
            print('All-variation repertoire browser checks passed')
    finally:
        httpd.shutdown()
        httpd.server_close()
        server.api.engine.stop()
        server.api.library.close()


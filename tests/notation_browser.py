"""Nested notation, promotion, preference changes and board orientation regression checks."""
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
            page.evaluate("""async()=>{
              const pgn='[White "Tree"]\\n[Black "Test"]\\n[Result "*"]\\n\\n1. e4 (1. d4 d5 (1... Nf6 2. c4) 2. c4) e5 2. Nf3 (2. Bc4 Nc6) Nc6 *';
              const result=await Caissa.api('games',{pgn});await Caissa.openGame((await Caissa.api('games')).games[0].id);
            }""")
            page.wait_for_selector('.analysis-board')
            assert page.locator('.move-tree details.variation').count()==3
            assert page.locator('.move-tree details.variation[open]').count()==3
            assert page.locator('.move-tree details.variation .move-row').count()==0
            page.get_by_role('button',name='Flip board',exact=True).click()
            def flipped():
                assert page.evaluate("Caissa.state.boards[Caissa.state.boardIndex].orientation")=='b'
                assert page.locator('.analysis-board .cg-coords').inner_text().replace('\n','').replace(' ','').startswith('h')
            flipped()
            page.get_by_role('checkbox',name='Score sheet rows',exact=True).check()
            flipped()
            page.locator('.move-tree').get_by_role('button',name='Move 1, White, d4',exact=True).click()
            page.get_by_role('button',name='Make main line',exact=True).click()
            flipped()
            assert page.evaluate('Caissa.state.parsed.root.children[0].san')=='d4'
            page.evaluate("async()=>await Caissa.go('analysis')")
            flipped()
            page.get_by_role('button',name='New analysis board',exact=True).click()
            assert page.evaluate("Caissa.state.boards[Caissa.state.boardIndex].orientation")=='w'
            page.get_by_role('tab',name='Tree',exact=False).click()
            flipped()
            page.get_by_role('checkbox',name='Score sheet rows',exact=True).uncheck()
            flipped()
            page.screenshot(path=str(ROOT/'tmp'/'notation-tree.png'))
            assert not errors,errors
            browser.close()
            print('Notation and orientation browser checks passed')
    finally:
        httpd.shutdown()
        httpd.server_close()
        server.api.engine.stop()
        server.api.library.close()


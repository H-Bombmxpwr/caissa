"""Run with .venv/Scripts/python tests/workbench_browser.py (Playwright + Edge)."""
import os
from pathlib import Path
import sys
import tempfile
import threading
from functools import partial
from http.server import ThreadingHTTPServer

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright


with tempfile.TemporaryDirectory(prefix='caissa-browser-') as data:
    os.environ['DATA_DIR']=data
    import server
    server.Handler.log_message=lambda *args:None
    httpd=ThreadingHTTPServer(('127.0.0.1',0),partial(server.Handler,directory=str(ROOT)))
    threading.Thread(target=httpd.serve_forever,daemon=True).start()
    url='http://127.0.0.1:'+str(httpd.server_port)
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='msedge',headless=True)
            page=browser.new_page(viewport={'width':1600,'height':1100})
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(url)
            page.wait_for_function('window.Caissa && document.querySelector(".games")')
            page.evaluate('''async()=>{await Caissa.api('games',{pgn:'[Event "Browser test"]\\n[White "Alpha"]\\n[Black "Beta"]\\n[Result "0-1"]\\n\\n1. f3 e5 2. g4 Qh4# 0-1'});await Caissa.go('database');}''')
            page.locator('tbody tr').first.click()
            page.wait_for_selector('.preview .btn.primary')
            assert page.locator('.preview piece.black.queen').count()==1
            assert 'translate(700%, 400%)' in page.locator('.preview piece.black.queen').get_attribute('style')
            page.locator('.preview .btn.primary').click()
            page.wait_for_selector('.analysis-board')
            assert page.get_by_text('Hold to peek',exact=True).count()==0
            page.get_by_role('button',name='Last move',exact=True).click()
            assert 'Qh4#' in page.locator('.move-tree button.current').inner_text()
            page.locator('.analysis-board .cg-wrap').hover()
            page.mouse.wheel(0,-120)
            assert 'g4' in page.locator('.move-tree button.current').inner_text()
            wrap=page.locator('.analysis-board .cg-wrap').bounding_box()
            x,y,w=wrap['x'],wrap['y'],wrap['width']
            page.mouse.move(x+w/16,y+w*15/16)
            page.mouse.down(button='right')
            page.mouse.move(x+w*3/16,y+w*11/16)
            page.mouse.up(button='right')
            assert page.locator('.analysis-board .cg-shapes line').count()==1
            page.get_by_role('button',name='Clear arrows',exact=True).click()
            assert page.locator('.analysis-board .cg-shapes line').count()==0
            before=page.locator('.analysis-board .cg-wrap').bounding_box()['width']
            page.locator('.board-resize').hover()
            page.mouse.down()
            page.mouse.move(x+before+70,y+before+5)
            page.mouse.up()
            assert page.locator('.analysis-board .cg-wrap').bounding_box()['width']>before
            page.get_by_role('button',name='Board editor',exact=True).click()
            page.get_by_label('FEN',exact=True).fill('8/8/8/8/8/5k2/8/7K w - - 0 1')
            page.get_by_role('button',name='Apply position',exact=True).click()
            page.wait_for_function('Caissa.state.parsed.headers.Event === "Edited position" && !document.querySelector("dialog")')
            page.route('**/api/tablebase?*',lambda r:r.fulfill(json={'category':'draw','dtz':0,'moves':[]}))
            page.get_by_label('Show exact endgame results (online)').check()
            page.get_by_text('White to move: draw',exact=True).wait_for()
            page.get_by_role('button',name='Analyze',exact=True).click()
            page.wait_for_selector('.engine-line',timeout=30000)
            page.wait_for_function('document.querySelector(".section-stack").textContent.includes("Memory")')
            page.get_by_label('Live analysis',exact=True).uncheck()
            page.evaluate('Caissa.go("settings")')
            page.get_by_label('Dark theme',exact=True).check()
            page.wait_for_function('document.body.classList.contains("dark-theme")')
            page.get_by_label('Piece set',exact=True).select_option('merida')
            page.wait_for_function('document.querySelector(".settings-grid piece").style.backgroundImage.includes("merida")')
            page.evaluate('''async()=>{
              window.__storageChoice=null;window.__storageSaved=false;
              window.pywebview={api:{storage_info:async()=>({path:'C:/CurrentLibrary'}),
                choose_storage_folder:async()=>window.__storageChoice,
                use_storage_folder:async()=>{window.__storageSaved=true;return {pending:window.__storageChoice};},
                cancel_storage_change:async()=>({cancelled:true})}};
              await Caissa.go('settings');
            }''')
            page.get_by_role('button',name='Browse folders…',exact=True).click()
            assert page.get_by_role('button',name='Use selected folder',exact=True).is_disabled()
            page.evaluate('window.__storageChoice="D:/MyChess"')
            page.get_by_role('button',name='Browse folders…',exact=True).click()
            page.get_by_role('button',name='Use selected folder',exact=True).click()
            page.get_by_text('Saved. Close all Caissa windows',exact=False).wait_for()
            assert page.evaluate('window.__storageSaved')
            page.get_by_role('button',name='Cancel pending change',exact=True).click()
            page.get_by_text('Storage change cancelled.',exact=False).wait_for()
            page.evaluate('delete window.pywebview')
            page.evaluate('Caissa.go("imports")')
            page.get_by_role('button',name='Undo import',exact=True).wait_for()
            page.on('dialog',lambda d:d.accept())
            page.get_by_role('button',name='Undo import',exact=True).click()
            page.wait_for_function('document.querySelector(".import-history").textContent.includes("Undone")')
            assert page.evaluate('async()=>(await Caissa.api("stats")).games')==0
            for view in ['database','masters','repertoire','studies','tactics','settings']:
                page.evaluate('(view)=>Caissa.go(view)',view)
                assert page.locator('.view-error').count()==0,view
            page.evaluate('''async()=>{await Caissa.api('games',{pgn:'[Event "Delete me"]\\n[White "Match"]\\n[Result "*"]\\n\\n1. e4 e5 *'});Caissa.state.filters={event:'Delete me'};await Caissa.go('database');}''')
            page.get_by_role('button',name='Delete matching games',exact=True).click()
            page.get_by_role('button',name='Delete 1 games',exact=True).click()
            page.wait_for_function('document.querySelector(".pagination").textContent.includes("0 games")')
            page.evaluate('''async()=>{Caissa.state.dirty=false;await Caissa.go('analysis');}''')
            page.get_by_role('button',name='Reset board',exact=True).click()
            page.wait_for_function('Caissa.state.node.fenAfter === Chess.DEFAULT_FEN')
            page.evaluate('App.stat("persistence-check",{count:7})')
            page.wait_for_function('async()=>JSON.parse((await Caissa.api("settings/trainer")).value).stats["persistence-check"].count===7')
            page.reload()
            page.wait_for_function('window.Caissa && App.store.stats["persistence-check"].count===7')
            assert page.evaluate('Caissa.state.prefs.darkMode')
            for smoke in ['workspace-smoke.html','smoke.html']:
                page.goto(url+'/tests/'+smoke)
                page.wait_for_function('document.querySelector("#results").textContent.includes("DONE")',timeout=60000)
                result=page.locator('#results').inner_text()
                assert 'FAIL' not in result and 'no uncaught errors' in result,result
            assert not errors,errors
            print('PASS: final preview, navigation, arrows, resize, editor, tablebase, live engine, appearance, import undo, bulk delete, reset, persistence, workspace and trainer smokes')
            browser.close()
    finally:
        server.api.live.stop()
        server.api.engine.stop()
        httpd.shutdown()
        httpd.server_close()
        server.api.library.close()

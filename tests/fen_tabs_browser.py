"""Run with .venv/Scripts/python tests/fen_tabs_browser.py (Playwright + Edge).

Pasting a FEN into the analysis board, and naming its tabs.
"""
import os
from pathlib import Path
import sys
import tempfile
import threading
from functools import partial
from http.server import ThreadingHTTPServer

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tests'))
from playwright.sync_api import sync_playwright
from browser_util import wait_until

ITALIAN_FOUR='r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq -'
ENDGAME='8/8/4k3/8/8/4K3/4P3/8 w - - 0 1'


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
            page.on('pageerror',lambda e:(errors.append(str(e)),print('Browser error:',e,flush=True)))
            page.on('dialog',lambda d:d.accept())
            page.goto(url)
            page.wait_for_function('window.Caissa && document.querySelector(".games")')
            page.evaluate("Caissa.go('analysis')")
            page.wait_for_selector('.fen-input')
            node_fen="()=>Caissa.state.node.fenAfter"
            def tabs():
                page.wait_for_selector('.board-tab')
                return page.locator('.board-tab').count()

            # A four-field FEN, as some sites copy it, lands in the untouched board.
            box=page.locator('.fen-input')
            box.fill(ITALIAN_FOUR)
            box.press('Enter')
            wait_until(page,"()=>Caissa.state.node.fenAfter.startsWith('r1bqkbnr/pppp1ppp/2n5')",what='the FEN to load')
            assert page.evaluate(node_fen)==ITALIAN_FOUR+' 0 1'
            assert tabs()==1, 'an empty board is reused'
            assert page.locator('.fen-input').input_value()==ITALIAN_FOUR+' 0 1'
            assert page.locator('.analysis-board piece.white.knight').count()==2
            assert not page.evaluate('Caissa.state.dirty'), 'a bare position has nothing to lose'

            # Once a move is made there, a pasted FEN opens beside it instead.
            page.get_by_label('Move in SAN').fill('Bc4')
            page.get_by_label('Move in SAN').press('Enter')
            wait_until(page,"()=>Caissa.state.node.san==='Bc4'")
            page.evaluate("""fen=>{const e=new ClipboardEvent('paste',{clipboardData:new DataTransfer(),bubbles:true});
                e.clipboardData.setData('text/plain',fen);document.body.dispatchEvent(e);}""",ENDGAME)
            wait_until(page,"()=>Caissa.state.node.fenAfter==='%s'"%ENDGAME,what='Ctrl+V to load the FEN')
            assert tabs()==2
            assert page.evaluate('Caissa.state.boards[0].parsed.root.children[0].san')=='Bc4', 'the first board kept its work'

            # Not a FEN: refused with a reason, nothing changes.
            box=page.locator('.fen-input')
            box.fill('hello there')
            box.press('Enter')
            page.wait_for_selector('.toast.show')
            assert 'not a FEN' in page.locator('.toast').inner_text()
            assert tabs()==2 and page.evaluate(node_fen)==ENDGAME
            # Impossible: the side that just moved is in check.
            box.fill('4k3/8/8/8/8/8/4r3/4K3 b - - 0 1')
            box.press('Enter')
            wait_until(page,"()=>/in check/.test(document.querySelector('.toast').textContent)")
            # Castling rights the pieces cannot back up are dropped rather than trusted.
            box.fill('4k3/8/8/8/8/8/8/4K3 w KQkq - 0 1')
            box.press('Enter')
            wait_until(page,"()=>Caissa.state.node.fenAfter==='4k3/8/8/8/8/8/8/4K3 w - - 0 1'")

            # Naming a tab: double-click, type, Enter. It survives switching away and back.
            page.locator('.board-tab.active .tab-label').dblclick()
            page.locator('.tab-rename').fill('Rook ending')
            page.locator('.tab-rename').press('Enter')
            assert page.locator('.board-tab.active .tab-label').inner_text()=='Rook ending'
            page.locator('.board-tab .tab-label').first.click()
            wait_until(page,"()=>Caissa.state.boardIndex===0")
            assert page.locator('.board-tab .tab-label').nth(1).inner_text()=='Rook ending'
            # Escape leaves the name alone.
            page.locator('.board-tab.active .tab-label').dblclick()
            page.locator('.tab-rename').fill('Not this')
            page.locator('.tab-rename').press('Escape')
            assert 'Not this' not in page.locator('.board-tabs').inner_text()
            # From the menu too; an empty name hands the tab back to its players' names.
            page.locator('.page-heading .btn-menu').click()
            page.get_by_role('menuitem',name='Rename board').click()
            page.locator('.tab-rename').fill('Italian')
            page.locator('.tab-rename').press('Enter')
            assert page.locator('.board-tab.active .tab-label').inner_text().startswith('Italian')
            page.locator('.board-tab.active .tab-label').dblclick()
            page.locator('.tab-rename').fill('')
            page.locator('.tab-rename').press('Enter')
            assert page.locator('.board-tab.active .tab-label').inner_text().startswith('New study')
            # Typing in the rename box must not drive the board.
            assert page.evaluate("Caissa.state.node.san")=='Bc4'

            # The board editor reads FENs the same way.
            page.locator('.page-heading .btn-menu').click()
            page.get_by_role('menuitem',name='Board editor').click()
            page.locator('dialog[open] input[aria-label="FEN"]').fill('4k3/8/8/8/8/8/8/4K3 w KQkq')
            page.get_by_role('button',name='Apply position').click()
            wait_until(page,"()=>Caissa.state.node.fenAfter==='4k3/8/8/8/8/8/8/4K3 w - - 0 1'")

            assert errors==[], errors
            browser.close()
    finally:
        httpd.shutdown()
        server.api.library.close()
print('fen and tab checks passed')

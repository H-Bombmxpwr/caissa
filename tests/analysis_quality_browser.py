"""Analysis UX regression checks; temporary library, mocked engine annotation."""
import os
from pathlib import Path
import sys
import tempfile
import threading
from functools import partial
from http.server import ThreadingHTTPServer
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
PGN='''[Event "Annotated model game"]
[White "Alpha"]
[Black "Beta"]
[Date "2025.11.01"]
[Annotator "A. Teacher"]
[Result "*"]

1. e4 {Keep this explanation. [%eval 0.26]} e5 {[%csl Re8][%cal Bf1b5,Rb5e8]}
2. Nf3 (2. Bc4 {Alternative idea.} Nf6 (2... Bc5 3. Nc3)) Nc6
3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 *
'''

with tempfile.TemporaryDirectory(prefix='caissa-quality-') as data:
    os.environ['DATA_DIR']=data
    import server
    server.Handler.log_message=lambda *args:None
    httpd=ThreadingHTTPServer(('127.0.0.1',0),partial(server.Handler,directory=str(ROOT)))
    threading.Thread(target=httpd.serve_forever,daemon=True).start()
    url='http://127.0.0.1:'+str(httpd.server_port)
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='msedge',headless=True)
            page=browser.new_page(viewport={'width':1920,'height':1200},accept_downloads=True)
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('dialog',lambda d:d.accept())
            page.goto(url)
            page.wait_for_function('window.Caissa')
            page.evaluate('''async pgn=>{await Caissa.api('games',{pgn,collection:'Quality'});const found=await Caissa.api('games?collection=Quality');await Caissa.openGame(found.games[0].id);}''',PGN)
            page.wait_for_selector('.move-tree button')
            assert '[%' not in page.locator('.move-tree').inner_text()
            assert page.locator('.move-row').first.locator('.move-cell').count()==2,'notes must not split a White/Black pair'
            assert page.locator('.pgn-tags').get_by_text('A. Teacher',exact=True).count()==1
            page.locator('.analysis-board').click(position={'x':10,'y':10})
            page.keyboard.press('ArrowRight');page.keyboard.press('ArrowRight')
            assert page.evaluate('Caissa.state.node.san')=='e5'
            assert page.locator('.cg-shapes line').count()==2
            assert page.locator('.cg-shapes circle').count()>=1
            assert '[%' not in page.get_by_label('Position comment',exact=True).input_value()
            page.keyboard.press('ArrowRight');page.keyboard.press('ArrowDown')
            assert page.evaluate('Caissa.state.node.san')=='Bc4'
            page.keyboard.press('ArrowUp')
            assert page.evaluate('Caissa.state.node.san')=='Nf3'
            page.keyboard.press('End');assert page.evaluate('Caissa.state.node.san')=='Be7'
            page.keyboard.press('Home');assert page.evaluate('Caissa.state.node.ply')==0
            page.get_by_label('Position comment',exact=True).fill('Root note typed immediately before export.')
            with page.expect_download() as download:
                page.get_by_role('button',name='Export PGN',exact=True).click()
            exported=Path(download.value.path()).read_text(encoding='utf-8')
            assert 'Root note typed immediately before export.' in exported
            assert '[%cal Bf1b5,Rb5e8]' in exported and '(2. Bc4' in exported
            page.evaluate('''()=>{window.__exported=null;window.pywebview={api:{export_pgn:async text=>{window.__exported=text;return {saved:true,path:'test.pgn'};}}};}''')
            page.get_by_role('button',name='Export PGN',exact=True).click()
            page.wait_for_function('window.__exported && window.__exported.includes("Root note")')
            page.evaluate('delete window.pywebview')
            page.get_by_role('button',name='Span Notation across both columns',exact=True).click()
            assert page.locator('.dock-wide [data-panel=notation]').count()==1
            assert page.locator('[data-panel=notation]').bounding_box()['width']>=page.locator('.analysis-panels').bounding_box()['width']-2
            # Repeated engine annotation replaces scores, leaving prose, NAGs and branches.
            def annotate(route):
                if route.request.method=='POST':route.fulfill(json={'started':True});return
                positions=page.evaluate('[Caissa.state.parsed.root,...PGN.mainline(Caissa.state.parsed.root)].map(n=>({ply:n.ply,fen:n.fenAfter,cp:35,mate:null}))')
                route.fulfill(json={'running':False,'done':len(positions),'total':len(positions),'results':positions})
            page.route('**/api/engine/annotate',annotate)
            for _ in range(2):
                page.get_by_role('button',name='Annotate game',exact=True).click()
                page.get_by_text('Annotation complete.',exact=False).wait_for()
            assert '[%' not in page.locator('.move-tree').inner_text()
            assert 'Keep this explanation.' in page.locator('.move-tree').inner_text()
            assert page.evaluate('Caissa.state.parsed.root.children[0].commands.filter(c=>c.startsWith("[%eval")).length')==1
            page.get_by_label('One move per line',exact=True).uncheck()
            assert page.locator('details.variation').count()==2
            page.get_by_role('button',name='Collapse variations',exact=True).click()
            assert page.locator('details.variation[open]').count()==0
            page.get_by_role('button',name='Expand variations',exact=True).click()
            page.evaluate('document.body.classList.add("dark-theme")')
            (ROOT/'tmp').mkdir(exist_ok=True)
            page.screenshot(path=str(ROOT/'tmp/analysis-quality.png'),full_page=True)
            page.evaluate('''async()=>{const c=(await Caissa.api('collections')).collections.find(c=>c.name==='Quality');const parent=await Caissa.api('study/folders',{name:'Preparation'});const child=await Caissa.api('study/folders',{name:'King pawn',parent_id:parent.id});await Caissa.api('study/assign',{folder_id:child.id,collection_id:c.id});window.__qualityCollection=c.id;Caissa.state.dirty=false;await Caissa.go('studies');}''')
            assert page.locator('.study-node .study-node .collection-leaf').count()==1
            page.get_by_role('button',name='Collapse all',exact=True).click()
            assert page.locator('.study-node[open]').count()==0
            page.get_by_role('button',name='Expand all',exact=True).click()
            page.screenshot(path=str(ROOT/'tmp/study-hierarchy.png'),full_page=True)
            page.evaluate('''async()=>{await Caissa.api('study/index',{collection:window.__qualityCollection});await Caissa.go('analysis');}''')
            page.wait_for_function('async()=>!(await Caissa.api("study/index")).running')
            page.get_by_role('button',name='Library',exact=True).click()
            page.get_by_label('Example search',exact=True).fill('Teacher')
            page.get_by_role('button',name='Find examples',exact=True).click()
            page.get_by_text('1 matching games',exact=True).wait_for()
            page.get_by_label('Example result',exact=True).select_option('1-0')
            page.get_by_text('0 matching games',exact=True).wait_for()
            page.evaluate('Caissa.go("settings")')
            page.get_by_label('Sound set',exact=True).select_option('wood')
            page.get_by_label('Animation duration',exact=True).select_option('350')
            page.get_by_role('button',name='Preview castle',exact=True).click()
            assert page.evaluate('ChessSounds.eventFor({san:"O-O"})')=='castle'
            assert page.evaluate('ChessSounds.eventFor({san:"exd5",captured:"p"})')=='capture'
            page.reload();page.wait_for_function('window.Caissa')
            page.get_by_label('Sound set',exact=True).wait_for()
            assert page.get_by_label('Sound set',exact=True).input_value()=='wood'
            assert page.get_by_label('Animation duration',exact=True).input_value()=='350'
            def reopen():
                page.evaluate('''async()=>{Caissa.state.dirty=false;await Caissa.openGame((await Caissa.api('games?collection=Quality')).games[0].id);}''')
                page.get_by_label('One move per line',exact=True).check()
            reopen()
            page.locator('details.variation').first.get_by_role('button',name='Nf6',exact=True).click()
            page.locator('details.variation summary').first.click(button='right')
            page.get_by_role('button',name='Delete entire variation (4 moves)',exact=True).click()
            assert page.evaluate('Caissa.state.node.san')=='e5','deleting the current variation returns to its parent'
            assert page.evaluate('Caissa.state.parsed.root.children[0].children[0].children.map(n=>n.san)')==['Nf3']
            reopen()
            page.get_by_role('button',name='Last move',exact=True).click()
            page.locator('.move-tree').get_by_role('button',name='Nf3',exact=True).click(button='right')
            page.get_by_role('button',name='Delete following moves only (7 moves)',exact=True).click()
            assert page.evaluate('Caissa.state.node.san')=='Nf3'
            assert page.evaluate('Caissa.state.node.children.length')==0
            assert page.locator('details.variation').count()==2,'sibling variations survive trimming'
            reopen()
            page.locator('.move-tree').get_by_role('button',name='Nf3',exact=True).click(button='right')
            page.get_by_role('button',name='Cancel',exact=True).click()
            assert page.evaluate('PGN.mainline(Caissa.state.parsed.root).length')==10
            page.locator('.move-tree').get_by_role('button',name='Nf3',exact=True).click(button='right')
            page.get_by_role('button',name='Delete move and continuation (8 moves)',exact=True).click()
            assert page.evaluate('Caissa.state.parsed.root.children[0].children[0].children.map(n=>n.san)')==['Bc4']
            page.get_by_role('button',name='Save changes *',exact=True).click()
            page.wait_for_function('!Caissa.state.dirty')
            assert 'Nf3' not in page.evaluate('Caissa.serialize(Caissa.state.parsed)')
            assert not errors,errors
            print('PASS: readable notation, nested variations, arrows, keys, browser/native export, repeated annotation, full-width panels, hierarchy, example filters, tags, sounds and animation settings')
            browser.close()
    finally:
        server.api.live.stop();server.api.engine.stop();httpd.shutdown();httpd.server_close();server.api.library.close()

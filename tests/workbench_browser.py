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
            page.on('pageerror',lambda e:(errors.append(str(e)),print('Browser error:',e,flush=True)))
            page.on('dialog',lambda d:d.accept())
            page.goto(url)
            page.wait_for_function('window.Caissa && document.querySelector(".games")')
            # The golden rule: a1 dark, h1 light, and the board agreeing with Game.squareColor.
            mismatch=page.evaluate("""()=>{const bad=[];
              for(const f of 'abcdefgh')for(let r=1;r<=8;r++){const key=f+r;
                const el=document.querySelector('.board-holder .cg-board square[data-key="'+key+'"]');
                if(!el){bad.push(key+':missing');continue;}
                const shown=el.classList.contains('light')?'light':'dark';
                if(shown!==Chess.squareColor(key))bad.push(key+':'+shown);}
              return bad;}""")
            assert mismatch==[],mismatch
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
            # Drawing the same arrow again removes it; a different colour recolours in place.
            def sweep(mods=None):
                page.mouse.move(x+w/16,y+w*15/16)
                page.keyboard.down(mods) if mods else None
                page.mouse.down(button='right')
                page.mouse.move(x+w*3/16,y+w*11/16,steps=6)
                assert page.locator('.analysis-board .cg-shapes line').count()>=1,'live preview while dragging'
                page.mouse.up(button='right')
                page.keyboard.up(mods) if mods else None
            sweep()
            assert page.locator('.analysis-board .cg-shapes line').count()==0,'redrawing removes'
            sweep('Shift')
            assert page.locator('.analysis-board .cg-shapes line').count()==1
            assert page.locator('.analysis-board .cg-shapes .shape-red').count()>0,'Shift paints red'
            sweep()
            assert page.locator('.analysis-board .cg-shapes .shape-green').count()>0,'recoloured in place'
            assert page.locator('.analysis-board .cg-shapes line').count()==1,'not stacked'
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
            page.wait_for_function('document.querySelector(".dock-main").textContent.includes("Memory")')
            # Stop the search first: live analysis rewrites these lines underneath you.
            page.get_by_label('Live analysis',exact=True).uncheck()
            # Depth is legible on its own, and a line can be walked in the move tree.
            assert page.locator('.engine-line .line-depth').first.inner_text().startswith('depth')
            pv=page.locator('.engine-line span').nth(2).inner_text().split()
            page.get_by_role('button',name='Add to tree',exact=True).first.click()
            page.wait_for_function('(san)=>Caissa.state.node.san===san',arg=pv[0])
            assert page.locator('.move-tree button.current').inner_text().strip().startswith(pv[0])
            # Annotations land in the game as they are typed - there is no Keep button.
            assert page.get_by_role('button',name='Keep annotation').count()==0
            page.get_by_label('Position comment',exact=True).fill('key idea')
            page.wait_for_function('Caissa.state.node.comment==="key idea"')
            # Panels hide and cross between the two docks, and each tab keeps its own layout.
            assert page.locator('.dock-main [data-panel=notation]').count()==1
            page.locator('[data-panel=tags] .panel-btn[aria-label="Hide Game tags"]').click()
            assert page.locator('[data-panel=tags]').count()==0
            page.locator('[data-panel=notation] .panel-btn[aria-label="Move Notation to the other column"]').click()
            assert page.locator('.dock-side [data-panel=notation]').count()==1
            page.get_by_role('button',name='New analysis board',exact=True).click()
            page.wait_for_function('document.querySelectorAll(".board-tab").length===2')
            # A new tab starts from the remembered arrangement, not the neighbour's edits.
            assert page.locator('.dock-main [data-panel=notation]').count()==1,'new tab uses the saved layout'
            assert page.locator('[data-panel=tags]').count()==1
            page.locator('.board-tab').first.locator('.tab-label').click()
            page.wait_for_function('document.querySelector(".dock-side [data-panel=notation]")!==null')
            assert page.locator('[data-panel=tags]').count()==0,'each tab restores its own layout'
            page.locator('.board-tab').nth(1).locator('.tab-close').click()
            page.wait_for_function('document.querySelectorAll(".board-tab").length===1')
            # Nothing inside the analysis grid should scroll until a panel is given a height,
            # and the grip has to be able to pull a panel past its own content.
            # The move list is the one scroller a panel is meant to have. Anything else
            # scrolling means the inner caps are stacking scrollbars again.
            overflowing=page.evaluate("""()=>{const out=[];
              for(const el of document.querySelectorAll('.analysis-grid *')){
                if(el.classList.contains('move-tree'))continue;
                if(!/auto|scroll/.test(getComputedStyle(el).overflowY))continue;
                if(el.scrollHeight-el.clientHeight>1)out.push((el.dataset.panel||el.className)+':'+(el.scrollHeight-el.clientHeight));}
              return out;}""")
            assert overflowing==[],overflowing
            assert page.evaluate("getComputedStyle(document.querySelector('[data-panel=notation] .panel-body')).overflowY")=='hidden'
            grip=page.locator('[data-panel=engine] .panel-grip')
            grip.hover()
            spot=grip.bounding_box()
            short=page.evaluate("document.querySelector('[data-panel=engine] .panel-body').offsetHeight")
            page.mouse.down()
            page.mouse.move(spot['x']+spot['width']/2,spot['y']+240,steps=10)
            page.mouse.up()
            tall=page.evaluate("document.querySelector('[data-panel=engine] .panel-body').offsetHeight")
            assert tall>short+150,(short,tall)
            assert page.evaluate('Caissa.state.boards[Caissa.state.boardIndex].layout.heights.engine')>short+150
            # Saving offers every collection outright, not just My games.
            page.evaluate('''async()=>{await Caissa.api('collections',{name:'Model games'});Caissa.state.dirty=false;await Caissa.go('analysis');}''')
            page.get_by_role('button',name='Save game',exact=True).click()
            names=page.locator('dialog select').first
            assert 'Model games' in names.inner_text(),names.inner_text()
            assert 'My games' in names.inner_text(),names.inner_text()
            page.get_by_role('button',name='Cancel',exact=True).click()
            # PGN comment commands: [%evp from,to,...] is the main line's engine eval per
            # ply. It belongs beside the moves, not in the notes, and must survive a save.
            evp_pgn=('[Event "Evp"]\n[White "Alpha"]\n[Black "Beta"]\n[Result "*"]\n\n'
                     '{[%evp 0,4,10,-20,30,-40,50] Opening note.} '
                     '1. e4 $10 e5 (1... c5 $19 {Sharper.}) 2. Nf3 Nc6 *')
            page.evaluate('''async(pgn)=>{await Caissa.api('games',{pgn,collection:'Evp'});
              const found=await Caissa.api('games?'+new URLSearchParams({collection:'Evp',limit:1}));
              Caissa.state.dirty=false;await Caissa.openGame(found.games[0].id);}''',evp_pgn)
            page.wait_for_selector('.move-tree button')
            assert page.evaluate('Caissa.state.parsed.root.comment')=='Opening note.','prose survives the harvest'
            chips=page.locator('.move-eval').all_inner_texts()
            assert chips==['-0.20','+0.30','-0.40','+0.50'],chips
            # The variation shares a ply with the main line but not its evaluation.
            assert page.evaluate('''(()=>{const v=Caissa.state.parsed.root.children[0].children[1];
              return v.san+':'+(v.eval?'has':'none');})()''')=='c5:none'
            texts=page.evaluate('[...document.querySelectorAll(".move-tree button")].map(b=>b.textContent.trim())')
            assert any(t.startswith('e4') and '=' in t for t in texts),texts
            assert any(t.startswith('c5') and '\u2212+' in t for t in texts),texts
            assert '[%evp 0,4,10,-20,30,-40,50]' in page.evaluate('Caissa.serialize(Caissa.state.parsed)')
            # Drawings belong to the move, survive stepping away and back, are marked in
            # the move list, and are written into the PGN as [%cal]/[%csl] like lichess.
            page.evaluate('''async()=>{Caissa.state.dirty=false;await Caissa.go('analysis');}''')
            page.wait_for_selector('.analysis-board .cg-wrap')
            page.get_by_role('button',name='Next move',exact=True).click()
            wrap=page.locator('.analysis-board .cg-wrap').bounding_box()
            bx,by,bw=wrap['x'],wrap['y'],wrap['width']
            page.mouse.move(bx+bw/16,by+bw*15/16)
            page.mouse.down(button='right')
            page.mouse.move(bx+bw*3/16,by+bw*11/16,steps=6)
            page.mouse.up(button='right')
            page.wait_for_function('(Caissa.state.node.shapes||[]).length===1')
            drawn=page.evaluate('Caissa.state.node.shapes[0]')
            assert drawn['from']=='a1' and drawn['to']=='b3' and drawn['brand']=='green',drawn
            assert page.locator('.move-tree .move-drawings').count()>=1,'the move list describes the drawing'
            page.get_by_role('button',name='First position',exact=True).click()
            assert page.locator('.analysis-board .cg-shapes line').count()==0,'other moves keep their own board'
            page.get_by_role('button',name='Next move',exact=True).click()
            page.wait_for_function('document.querySelectorAll(".analysis-board .cg-shapes line").length===1')
            written=page.evaluate('Caissa.serialize(Caissa.state.parsed)')
            assert '[%cal Ga1b3]' in written,written[-260:]
            # And they come back when the game is reopened.
            page.evaluate('''async(pgn)=>{const parsed=PGN.parse(pgn);Caissa.state.parsed=parsed;
              Caissa.state.node=parsed.root;Caissa.state.dirty=false;await Caissa.go('analysis');}''',written)
            page.wait_for_selector('.move-tree button')
            assert page.evaluate('''(()=>{const n=Caissa.state.parsed.root.children[0];
              return (n.shapes||[]).map(s=>s.brand+s.from+s.to).join();})()''')=='greena1b3'
            # The Facts tab reads Wikipedia; the lookup is stubbed so the test stays offline.
            page.route('**/api/facts?*',lambda r:r.fulfill(json={'groups':[{'label':'The players','note':None,
              'items':[{'title':'Alpha','extract':'A player.','url':'https://en.wikipedia.org/wiki/Alpha'}]}],
              'message':None,'query':{}}))
            page.get_by_role('button',name='Facts',exact=True).click()
            page.get_by_text('Background from Wikipedia',exact=True).wait_for()
            assert page.get_by_role('link',name='Alpha',exact=True).count()==1
            assert 'Wikipedia' in page.locator('.context-body').inner_text()
            # Put the library back as it was so the import-history checks below stay honest.
            page.evaluate('''async()=>{const cols=(await Caissa.api('collections')).collections;
              const evp=cols.find(c=>c.name==='Evp');
              if(evp)await Caissa.api('collections/'+evp.id,null,'DELETE');
              Caissa.state.dirty=false;}''')
            page.evaluate('Caissa.go("settings")')
            page.get_by_label('Dark theme',exact=True).check()
            page.wait_for_function('document.body.classList.contains("dark-theme")')
            page.get_by_role('button',name='Merida',exact=True).click()
            page.wait_for_function('document.querySelector(".settings-grid piece").style.backgroundImage.includes("merida")')
            assert 'merida' in page.locator('.piece-swatch.active .piece-pair img').first.get_attribute('src')
            treatment=page.get_by_role('button',name='Warm wood',exact=True)
            assert 'merida' in treatment.locator('img').first.get_attribute('src'),'treatment thumbnails follow the chosen set'
            treatment.click()
            page.wait_for_function('document.body.classList.contains("piece-wood")')
            page.evaluate('''async()=>{
              window.__storageChoice=null;window.__storageSaved=false;window.__revealed=false;
              window.pywebview={api:{storage_info:async()=>({path:'C:/CurrentLibrary'}),
                reveal_storage_folder:async()=>{window.__revealed=true;return {opened:'C:/CurrentLibrary'};},
                choose_storage_folder:async()=>window.__storageChoice,
                use_storage_folder:async()=>{window.__storageSaved=true;return {pending:window.__storageChoice};},
                cancel_storage_change:async()=>({cancelled:true})}};
              await Caissa.go('settings');
            }''')
            page.get_by_role('button',name='Show in folder',exact=True).click()
            assert page.evaluate('window.__revealed'),'Show in folder reaches the native bridge'
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
            page.get_by_role('button',name='Undo import',exact=True).click()
            page.wait_for_function('document.querySelector(".import-history").textContent.includes("Undone")')
            assert page.evaluate('async()=>(await Caissa.api("stats")).games')==0
            for view in ['database','masters','repertoire','studies','tactics','settings']:
                page.evaluate('(view)=>Caissa.go(view)',view)
                assert page.locator('.view-error').count()==0,view
            page.evaluate('''async()=>{await Caissa.api('games',{pgn:'[Event "Delete me"]\\n[White "Match"]\\n[Result "*"]\\n\\n1. e4 e5 *'});Caissa.state.filters={event:'Delete me'};await Caissa.go('database');}''')
            before=page.locator('.stat-grid .metric strong').first.inner_text()
            page.get_by_role('button',name='Delete matching games',exact=True).click()
            page.get_by_role('button',name='Delete 1 games',exact=True).click()
            page.wait_for_function('document.querySelector(".pagination").textContent.includes("0 games")')
            # The library total is a whole-library count, so it has to fall without a reload.
            page.wait_for_function('(was)=>document.querySelector(".stat-grid .metric strong").textContent!==was',arg=before)
            assert page.locator('.stat-grid .metric strong').first.inner_text()=='0',page.locator('.stat-grid').inner_text()
            # An import started in one view has to land in the database without a reload,
            # even when the user walks away from the view that kicked it off.
            page.evaluate('Caissa.go("imports")')
            page.get_by_label('Collection name (required)',exact=True).fill('Fresh import')
            page.locator('#workspace textarea').first.fill('[Event "Fresh"]\n[White "Alpha"]\n[Black "Beta"]\n[Result "1-0"]\n\n1. d4 d5 1-0')
            page.get_by_role('button',name='Import PGN',exact=True).click()
            page.evaluate('Caissa.state.filters={};Caissa.go("database")')
            page.wait_for_function('document.querySelector(".stat-grid .metric strong").textContent==="1"',timeout=20000)
            assert page.locator('table.games tbody tr').first.locator('td').nth(1).inner_text()=='Alpha','the imported White player is listed straight away'
            assert page.locator('table.games tbody tr').first.locator('td').nth(3).inner_text()=='Beta','the imported Black player is listed straight away'
            # Opening names and their ECO span are offered from the library itself.
            page.get_by_role('button',name='Filters',exact=True).click()
            page.get_by_label('Colour',exact=True).select_option('white')
            page.get_by_label('Outcome',exact=True).select_option('win')
            page.get_by_label('Player',exact=True).fill('Alpha')
            page.get_by_role('button',name='Apply',exact=True).click()
            page.wait_for_function('Caissa.state.filters.outcome==="win"')
            matched=page.evaluate('async()=>(await Caissa.api("games?"+new URLSearchParams({...Caissa.state.filters,limit:1,offset:0}))).total')
            assert matched==1,matched
            assert page.evaluate('Caissa.state.filters.white')=='Alpha'
            assert page.evaluate('Caissa.state.filters.outcome')=='win'
            page.get_by_role('button',name='Filters',exact=True).click()
            page.get_by_role('button',name='Clear all fields',exact=True).click()
            page.wait_for_function('Object.keys(Caissa.state.filters).length===0')
            page.evaluate('''async()=>{Caissa.state.dirty=false;await Caissa.go('analysis');}''')
            page.get_by_role('button',name='Reset board',exact=True).click()
            page.wait_for_function('Caissa.state.node.fenAfter === Chess.DEFAULT_FEN')
            page.evaluate('App.stat("persistence-check",{count:7})')
            page.wait_for_function('async()=>JSON.parse((await Caissa.api("settings/trainer")).value).stats["persistence-check"].count===7')
            page.reload()
            page.wait_for_function('window.Caissa && App.store.stats["persistence-check"].count===7')
            assert page.evaluate('Caissa.state.prefs.darkMode')
            # Annotated PGNs retain all comments, including those after the result.
            page.evaluate('''async()=>{
              const text='[Event "Linares"]\\n[White "Karpov"]\\n[Black "Kasparov"]\\n[Annotator "Knaak"]\\n[Result "0-1"]\\n\\n{Introduction} 1. e4! {First note} {Second note} e5; Not a move: Qh9\\n2. Nf3 Nc6 0-1 {White resigned}';
              const parsed=PGN.parse(text),line=PGN.mainline(parsed.root);
              if(parsed.errors.length||!line[0].comment.includes('First note')||!line[0].comment.includes('Second note')||!line[3].comment.includes('White resigned')||line[0].nags[0]!=='$1')throw Error('PGN annotation loss');
              const roundtrip=PGN.parse(Caissa.serialize(parsed));if(!PGN.mainline(roundtrip.root).at(-1).comment.includes('White resigned'))throw Error('Save loses end comment');
              await Caissa.api('games',{pgn:text,collection:'Annotated tests'});Caissa.state.filters={annotator:'Knaak'};await Caissa.go('database');
            }''')
            assert page.locator('tbody').inner_text().find('Knaak')>=0
            page.locator('tbody tr').first.dblclick()
            page.get_by_text('White resigned',exact=True).wait_for()
            assert page.get_by_text('Introduction',exact=True).count()>0
            page.evaluate('Caissa.go("masters")')
            assert page.locator('.desk-body > .page-heading').count()==1
            assert page.locator('.desk-body').evaluate('(el)=>el.firstElementChild.classList.contains("page-heading")')
            page.get_by_label('Player surname',exact=True).fill('Fisc')
            page.wait_for_function('document.querySelector("#master-player-names option[value=Fischer]")')
            page.evaluate('Caissa.go("books")')
            pdf=b'%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Count 0/Kids[]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF'
            page.get_by_label('Choose PDF',exact=True).set_input_files({'name':'Reading.pdf','mimeType':'application/pdf','buffer':pdf})
            page.get_by_role('button',name='Add PDF',exact=True).click()
            page.get_by_text('PDF saved with your library.',exact=True).wait_for()
            book_id=page.evaluate('async()=>(await Caissa.api("books")).books[0].id')
            response=page.request.get(url+'/api/books/'+str(book_id)+'/file',headers={'Range':'bytes=0-7'})
            assert response.status==206 and response.body()==pdf[:8]
            page.get_by_label('Book page',exact=True).fill('2')
            page.get_by_role('button',name='Go to page',exact=True).click()
            page.wait_for_function('async()=>(await Caissa.api("books")).books[0].page===2')
            page.evaluate('Caissa.go("analysis")')
            page.get_by_role('button',name='Panels',exact=True).click()
            page.get_by_label('Books',exact=True).check()
            page.get_by_label('Opening book',exact=True).check()
            page.get_by_role('button',name='Done',exact=True).click()
            page.locator('[data-panel=books]').get_by_label('Book',exact=True).select_option(str(book_id))
            assert page.locator('[data-panel=books] iframe').is_visible()
            page.evaluate('Caissa.go("openingbook")')
            page.get_by_label('Reference database',exact=True).select_option('local')
            page.get_by_label('Collection to index',exact=True).select_option(label='Annotated tests (1)')
            page.get_by_role('button',name='Index positions',exact=True).click()
            page.wait_for_function('async()=>!(await Caissa.api("study/index")).running')
            page.get_by_role('button',name='Refresh opening book',exact=True).click()
            page.locator('.book-move').get_by_role('button',name='e4',exact=True).wait_for()
            page.locator('.book-move').get_by_role('button',name='e4',exact=True).click()
            page.get_by_text('Position after 1 plies',exact=True).wait_for()
            page.route('**/api/book?**',lambda r:r.fulfill(json={'source':'masters','total':9000,'cached':True,'moves':[{'san':'e5','games':9000,'white':3000,'draws':4000,'black':2000,'average_elo':2500}],'games':[],'reference_games':[]}))
            page.get_by_label('Reference database',exact=True).select_option('masters')
            page.get_by_text('Lichess Masters · 9,000 games · Saved reference',exact=True).wait_for()
            page.locator('.book-move').get_by_role('button',name='e5',exact=True).click()
            page.get_by_text('Position after 2 plies',exact=True).wait_for()
            page.unroute('**/api/book?**')
            page.evaluate('Caissa.go("repertoire")')
            page.get_by_text('How to use your repertoire',exact=True).wait_for()
            page.route('**/api/network',lambda r:r.fulfill(json={'reachable':False}))
            page.evaluate('Caissa.go("settings")')
            page.get_by_role('button',name='Check online services',exact=True).click()
            page.get_by_text('PGN Mentor is unreachable.',exact=False).wait_for()
            for smoke in ['workspace-smoke.html','smoke.html']:
                page.goto(url+'/tests/'+smoke)
                page.wait_for_function('document.querySelector("#results").textContent.includes("DONE")',timeout=60000)
                result=page.locator('#results').inner_text()
                assert 'FAIL' not in result and 'no uncaught errors' in result,result
            assert not errors,errors
            print('PASS: final preview, navigation, arrows, resize, editor, tablebase, live engine, live annotation, panels, board tabs, appearance, import undo, bulk delete, reset, persistence, workspace and trainer smokes')
            browser.close()
    finally:
        server.api.live.stop()
        server.api.engine.stop()
        httpd.shutdown()
        httpd.server_close()
        server.api.library.close()

"""Renaming a collection, and the master search saving what it searched for as its own shelf."""
import json
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

KID='[Event "?"]\n[White "Morozevich, A"]\n[Black "X"]\n[Date "1999.05.01"]\n[Result "1-0"]\n\n1. d4 Nf6 2. c4 g6 3. Nc3 Bg7 4. e4 d6 5. f3 O-O 1-0'
SICILIAN='[Event "?"]\n[White "Y"]\n[Black "Morozevich, A"]\n[Date "2011.03.02"]\n[Result "0-1"]\n\n1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6 0-1'
OLD_KID='[Event "?"]\n[White "Morozevich, A"]\n[Black "Z"]\n[Date "1994.09.09"]\n[Result "1/2-1/2"]\n\n1. d4 Nf6 2. c4 g6 3. Nc3 Bg7 4. e4 d6 5. Nf3 O-O 1/2-1/2'

with tempfile.TemporaryDirectory(prefix='caissa-collections-') as data:
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

            # ---- renaming a collection from Study folders ----
            page.evaluate("""async(pgn)=>{
              await Caissa.api('games',{pgn,collection:'Typo colection'});
              await Caissa.go('studies');
            }""",KID)
            page.get_by_text('All collections · export, delete and position indexing',exact=True).click()
            row=page.locator('.context-item').filter(has_text='Typo colection')
            row.get_by_role('button',name='More actions',exact=False).first.click()
            page.get_by_role('menuitem',name='Rename',exact=True).click()
            name=page.get_by_label('Collection name',exact=True)
            expect(name).to_have_value('Typo colection')
            name.fill('Annotated tournament games')
            page.get_by_role('button',name='Save name',exact=True).click()
            page.get_by_text('Collection renamed',exact=True).wait_for()
            page.get_by_text('All collections · export, delete and position indexing',exact=True).click()
            expect(page.get_by_text('Annotated tournament games · 1 games',exact=True)).to_be_visible()
            assert page.get_by_text('Typo colection · 1 games',exact=True).count()==0
            # The PGN folder moved with the name, so the game still reads back.
            game=page.evaluate("()=>Caissa.api('games?collection=Annotated tournament games')")['games'][0]
            assert 'annotated-tournament-games' in game['path'],game['path']

            # ---- the master search keeps what it searched for ----
            page.evaluate("""async(pgns)=>{
              await Caissa.api('games',{pgn:pgns.join('\\n\\n'),collection:'Masters / Morozevich'});
              await Caissa.go('masters');
            }""",[KID,SICILIAN,OLD_KID])
            page.get_by_label('Player surname',exact=True).fill('Morozevich')
            page.get_by_label('ECO from',exact=True).fill('E60')
            page.get_by_label('ECO through',exact=True).fill('E99')
            page.get_by_label('Year from',exact=True).fill('1996')
            page.get_by_label('Year through',exact=True).fill('2012')
            page.get_by_label('Opening name',exact=True).fill("King's Indian Defense")
            # PGN Mentor and the archive download are the only parts that need the network.
            page.route('**/api/masters/catalog*',lambda route:route.fulfill(status=200,
                content_type='application/json',
                body=json.dumps({'players':[{'name':'Morozevich','url':'https://example.invalid/M.zip'}]})))
            page.route('**/api/import/source',lambda route:route.fulfill(status=200,
                content_type='application/json',body=json.dumps({'added':0,'duplicates':3})))
            page.get_by_role('button',name='Find collections',exact=True).click()
            page.get_by_role('button',name='Import & find matching games',exact=True).click()
            shelf="Masters / Morozevich / King's Indian Defense 1996–2012"
            page.get_by_text(shelf,exact=False).first.wait_for()
            shelved=page.evaluate("(name)=>Caissa.api('games?collection='+name)",shelf)
            assert shelved['total']==1,shelved
            assert shelved['games'][0]['date'].startswith('1999'),shelved['games'][0]['date']
            # The archive keeps all three: the shelf holds links, not copies.
            assert page.evaluate("()=>Caissa.api('games?collection=Masters / Morozevich')")['total']==3
            # The database view lands on the shelf that was just built.
            shelf_id=page.evaluate("(name)=>Caissa.state.collections.find(c=>c.name===name).id",shelf)
            assert page.evaluate('()=>Caissa.state.filters')=={'collection':str(shelf_id)}
            page.screenshot(path=str(ROOT/'tmp'/'masters-shelf.png'))

            # ---- a connected lichess account is not asked for a token again ----
            page.evaluate("()=>Caissa.go('imports')")
            expect(page.get_by_label('lichess token',exact=True)).to_be_visible()
            page.evaluate("""()=>{
              CaissaAccount.set({connected:true,username:'ExampleUser',scopes:['study:read']});
            }""")
            expect(page.get_by_label('lichess token',exact=True)).to_be_hidden()
            expect(page.locator('.account-note')).to_contain_text('importing as ExampleUser')
            page.get_by_label('Service',exact=True).select_option('chesscom')
            expect(page.get_by_label('lichess token',exact=True)).to_be_visible()
            page.get_by_label('Service',exact=True).select_option('lichess')
            expect(page.get_by_label('lichess token',exact=True)).to_be_hidden()
            page.evaluate("()=>CaissaAccount.set({connected:false})")
            expect(page.get_by_label('lichess token',exact=True)).to_be_visible()

            assert not errors,errors
            browser.close()
            print('Collection rename, master shelf and lichess connection checks passed')
    finally:
        httpd.shutdown()
        httpd.server_close()
        server.api.engine.stop()
        server.api.library.close()

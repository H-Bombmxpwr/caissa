"""Interaction regressions for the UI polish, called by workbench_browser.py."""
from pathlib import Path

def check(page):
    shots=Path('tmp/ui-review');shots.mkdir(parents=True,exist_ok=True)
    page.evaluate('Caissa.go("computer")')
    page.get_by_role('button',name='New game',exact=True).click()
    page.get_by_label('Your move',exact=True).fill('e4')
    page.get_by_role('button',name='Play move',exact=True).click()
    page.wait_for_function('document.querySelectorAll(".computer-moves span").length===2',timeout=30000)
    page.get_by_role('button',name='Take back',exact=True).click()
    assert page.locator('.computer-moves span').count()==0
    page.get_by_label('Your move',exact=True).fill('d4')
    page.get_by_role('button',name='Play move',exact=True).click()
    page.wait_for_function('document.querySelectorAll(".computer-moves span").length===2',timeout=30000)
    page.get_by_role('button',name='Save to database',exact=True).click()
    page.wait_for_function('document.body.textContent.includes("Game saved to Computer games")')
    page.screenshot(path=str(shots/'computer.png'),full_page=True)
    # The computer board resizes by its corner handle and the width is remembered.
    wide=page.locator('.computer-grid .cg-wrap').bounding_box()['width']
    grip=page.locator('.computer-grid .board-resize').bounding_box()
    page.mouse.move(grip['x']+grip['width']/2,grip['y']+grip['height']/2)
    page.mouse.down()
    page.mouse.move(grip['x']-120,grip['y'],steps=5)
    page.mouse.up()
    narrow=page.locator('.computer-grid .cg-wrap').bounding_box()['width']
    assert narrow<wide-60,(wide,narrow)
    page.wait_for_function('Caissa.state.prefs.computerBoardSize>0')
    page.evaluate('Caissa.go("database")')
    page.evaluate('Caissa.go("computer")')
    page.wait_for_selector('.computer-grid .cg-wrap')
    assert abs(page.locator('.computer-grid .cg-wrap').bounding_box()['width']-narrow)<8,'width survives leaving the view'
    page.get_by_role('button',name='Analyze game',exact=True).click()
    page.wait_for_selector('.analysis-board')
    assert page.evaluate('Caissa.state.parsed.root.children[0].san')=='d4'
    page.evaluate('''async()=>{
      await Caissa.api('repertoires',{name:'UI merged repertoire',color:'w',data:{lines:[
        {fen:new Chess().fen(),moves:['e4','e5','Nf3']},
        {fen:new Chess().fen(),moves:['e4','c5','Nf3']} ]}});
      await Caissa.go('repertoire');
    }''')
    page.locator('.study-card').filter(has_text='UI merged repertoire').get_by_role('button',name='View repertoire',exact=True).click()
    page.wait_for_selector('.analysis-board')
    page.get_by_role('button',name='Next move',exact=True).click()
    assert page.locator('.branch-picker button').count()==2
    page.locator('.page-heading h1').click()
    page.keyboard.press('ArrowDown');page.keyboard.press('ArrowRight')
    assert page.evaluate('Caissa.state.node.san')=='c5'
    page.get_by_label('Span Notation across both columns',exact=True).click()
    page.get_by_label('Span Stockfish · local analysis across both columns',exact=True).click()
    page.get_by_label('Move Stockfish · local analysis up',exact=True).click()
    assert page.locator('.dock-wide>.panel').first.get_attribute('data-panel')=='engine'
    page.get_by_label('Move Stockfish · local analysis to the other column',exact=True).click()
    assert page.locator('.dock-wide>[data-panel=engine]').count()==0
    assert page.locator('[data-panel=engine]').bounding_box()['width']>250
    page.get_by_role('button',name='Panels',exact=True).click()
    page.get_by_role('button',name='Reset arrangement',exact=True).click()
    page.screenshot(path=str(shots/'analysis.png'),full_page=True)
    for view in ['settings','masters','tactics','studies','imports']:
        page.evaluate('(v)=>Caissa.go(v)',view)
        page.wait_for_selector('.page-heading')
        page.screenshot(path=str(shots/(view+'.png')),full_page=True)
    assert page.evaluate('''()=>{const history=document.querySelector('.import-history'),options=document.querySelector('.settings-grid');return !!(options.compareDocumentPosition(history)&Node.DOCUMENT_POSITION_FOLLOWING)}''')
    page.evaluate('Caissa.go("masters")')
    player=page.get_by_label('Player surname',exact=True)
    player.fill('Fischer')
    page.wait_for_selector('.suggestions:not([hidden]) [role=option]',timeout=15000)
    player.press('ArrowDown');player.press('Enter')
    assert player.get_attribute('aria-expanded')=='false'
    assert not player.get_attribute('list')
    page.wait_for_timeout(500)
    assert player.get_attribute('aria-expanded')=='false','Selecting a suggestion must not reopen the popup'
    page.evaluate('Caissa.go("settings")')
    page.get_by_label('Dark theme',exact=True).uncheck()
    page.screenshot(path=str(shots/'settings-light.png'),full_page=True)
    page.set_viewport_size({'width':1100,'height':850})
    page.evaluate('Caissa.go("analysis")')
    page.wait_for_selector('.analysis-board')
    assert page.locator('[data-panel=engine]').bounding_box()['width']>250
    page.screenshot(path=str(shots/'analysis-compact.png'),full_page=True)
    page.set_viewport_size({'width':1600,'height':1100})
    page.evaluate('''async()=>{await Caissa.go('training');App.go('colors');}''')
    square=page.locator('#panel .prompt').inner_text()
    colour=page.evaluate('(s)=>Chess.squareColor(s)',square)
    page.locator('#panel .darkbtn' if colour=='light' else '#panel .lightbtn').click()
    page.locator('#panel').get_by_role('button',name='Peek',exact=True).click()
    assert page.evaluate('App.peek.active')
    page.get_by_role('button',name='Continue / Enter',exact=True).click()
    assert page.locator('#panel .prompt').inner_text()!=square
    page.evaluate('''()=>{App.board.setPosition(new Chess());App.go('colors');}''')
    assert page.locator('#board piece').count()==0,'Chapter entry clears the previous board'

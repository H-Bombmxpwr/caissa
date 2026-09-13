"""Shared board sounds and opening-tree navigation regressions."""
def check(page):
    result=page.evaluate('''async()=>{
      const original=ChessSounds.play,events=[];
      ChessSounds.configure({soundPack:'wood'});
      ChessSounds.play=async event=>events.push(event);
      const holder=document.createElement('div');document.body.append(holder);
      const b=new Board(holder,{animationMs:0});
      try{
        let g=new Chess();b.setPosition(g);
        const initial=events.length;
        for(const san of ['e4','d5','exd5']){g.move(san);b.setPosition(g);}
        const forward=events.splice(0);
        b.setPosition(g);b.toggleOrientation();b.setPosition(g);
        const redraw=events.length;
        g.undo();b.setPosition(g);
        const back=events.splice(0);
        b.setPosition(new Chess(),{sound:false});
        const load=events.length;
        async function event(fen,san){const g=new Chess(fen);b.setPosition(g,{sound:false});g.move(san);b.setPosition(g);return events.pop();}
        const castle=await event('r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1','O-O');
        const promotion=await event('7k/P7/8/8/8/8/8/7K w - - 0 1','a8=N');
        const check=await event('7k/8/8/8/8/8/8/KR6 w - - 0 1','Rh1+');
        ChessSounds.configure({soundPack:'off'});
        g=new Chess();b.setPosition(g,{sound:false});g.move('e4');b.setPosition(g);
        const muted=events.length;
        return {initial,forward,redraw,back,load,castle,promotion,check,muted};
      }finally{ChessSounds.play=original;ChessSounds.configure(Caissa.state.prefs);holder.remove();}
    }''')
    assert result==dict(initial=0,forward=['move','opponent','capture'],redraw=0,
                        back=['move'],load=0,castle='castle',promotion='promotion',check='check',muted=0),result
    page.evaluate('''async()=>{
      window.__originalSound=ChessSounds.play;window.__moveSounds=[];
      window.__explorerSide=Caissa.state.prefs.explorerOrientation;
      Caissa.state.prefs.explorerOrientation='w';
      ChessSounds.configure({soundPack:'wood'});
      ChessSounds.play=async e=>window.__moveSounds.push(e);
      await Caissa.go('openingbook');
    }''')
    try:
        # Actual board clicks on the Collection tree page, then its Back control.
        board=page.locator('.opening-grid .board-holder')
        wrap=board.locator('.cg-wrap')
        width=wrap.bounding_box()['width']
        wrap.click(position={'x':width*4.5/8,'y':width*6.5/8})
        wrap.click(position={'x':width*4.5/8,'y':width*4.5/8})
        assert page.evaluate('window.__moveSounds')==['move']
        page.get_by_role('button',name='Back a move',exact=True).click()
        assert page.evaluate('window.__moveSounds')==['move','move']
        page.evaluate('Caissa.go("analysis")')
        page.get_by_role('button',name='First position',exact=True).click()
        page.evaluate('window.__moveSounds=[]')
        page.get_by_role('button',name='Next move',exact=True).click()
        assert page.evaluate('window.__moveSounds.length')==1,'Analysis must not double-play sounds'
    finally:
        page.evaluate('ChessSounds.play=window.__originalSound;Caissa.state.prefs.explorerOrientation=window.__explorerSide;ChessSounds.configure(Caissa.state.prefs)')

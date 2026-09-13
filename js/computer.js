/* A computer game persists when visiting other sections, independently of analysis tabs. */
window.ComputerPlay=(function(){
  'use strict';
  let game=new Chess(),side='w',level=5,started=false,result='*',revision=0,request=0;
  const positions=[];
  function mount(content,ui){
    const {h,button,field,select,api,heading,analyze,resizeBoard}=ui;
    let closed=false,busy=false;
    const holder=h('div.board-holder'),b=new Board(holder,{viewOnly:false}),status=h('p.computer-status',{role:'status'}),moves=h('div.computer-moves');
    const difficulty=select(Array.from({length:11},(_,i)=>[String(i+1),'Level '+(i+1)+(i===10?' · These go to eleven':'')]),String(level));
    const colour=select([['w','White'],['b','Black'],['random','Random']],side);
    const retry=button('Retry computer move',think);retry.hidden=true;
    function pgn(){return '[Event "Computer practice"]\n[Date "'+new Date().toISOString().slice(0,10).replace(/-/g,'.')+'"]\n[White "'+(side==='w'?'You':'Stockfish level '+level)+'"]\n[Black "'+(side==='b'?'You':'Stockfish level '+level)+'"]\n[Result "'+result+'"]\n\n'+game.historySan().map((m,i)=>(i%2===0?(i/2+1)+'. ':'')+m).join(' ')+' '+result;}
    function render(){
      b.setPosition(game);const last=game.lastMove();b.setLastMove(last?[last.from,last.to]:null);
      const can=started&&!busy&&result==='*'&&game.turnColor()===side;
      b.setMovable({color:can?side:null,dests:can?game.destinationsMap():null,onMove:(from,to)=>{
        if(game.get(from)?.type==='p'&&/[18]$/.test(to)){ui.promote(promotion=>play({from,to,promotion}));}else play({from,to});
      }});
      status.textContent=!started?'Choose your side and level, then start a game.':result!=='*'?'Game over · '+result:busy?'Stockfish is thinking…':game.turnColor()===side?'Your move'+(game.inCheck()?' · Check':''):'Computer to move';
      moves.replaceChildren(...game.historySan().map((san,i)=>h('span',{text:(i%2===0?(i/2+1)+'. ':'')+san})));
    }
    function finish(){
      if(game.isCheckmate())result=game.turnColor()==='w'?'0-1':'1-0';
      else if(game.isDraw()||positions.filter(f=>f===game.fen().split(' ').slice(0,4).join(' ')).length>=3)result='1/2-1/2';
    }
    function record(move){if(!move)throw new Error('That move is not legal.');positions.push(game.fen().split(' ').slice(0,4).join(' '));revision++;finish();render();}
    function play(move){if(!started||busy||result!=='*'||game.turnColor()!==side)return;try{record(game.move(move));think();}catch(err){App.toast(err.message);}}
    async function think(){
      if(closed||busy||!started||result!=='*'||game.turnColor()===side)return;
      const id=++request,fen=game.fen();busy=true;retry.hidden=true;render();
      try{const data=await api('engine/play',{fen,level});if(closed||id!==request||game.fen()!==fen)return;record(game.move(data.bestmove));}
      catch(err){if(!closed&&id===request){status.textContent=err.message;retry.hidden=false;}}
      finally{if(id===request){busy=false;if(!closed&&retry.hidden)render();}}
    }
    const input=h('input',{'aria-label':'Your move',placeholder:'e.g. Nf3'});
    content.append(heading('A sparring partner, always ready','Play the computer','Local Stockfish, eleven levels. Take back a move, save your game, or explore it on the analysis board.'));
    content.append(h('div.computer-grid',[h('section.card.card-pad',[holder,h('form.toolbar',{onsubmit:e=>{e.preventDefault();play(input.value);input.value='';}},[input,h('button.btn.primary',{type:'submit',text:'Play move'})])]),h('div.section-stack',[
      h('section.card.card-pad',[h('h2',{text:'Your opponent'}),field('Computer level',difficulty),field('Play as',colour),h('p.muted',{text:'Level 1 is the gentlest; level 11 uses full skill. Levels are practice settings, not Elo ratings. Changes apply to the next game.'}),button('New game',()=>{if(started&&game.history.length&&result==='*'&&!confirm('Start a new game? Save this game first if you want to keep it.'))return;++request;busy=false;game=new Chess();positions.splice(0,positions.length,game.fen().split(' ').slice(0,4).join(' '));side=colour.value==='random'?(Math.random()<.5?'w':'b'):colour.value;level=Number(difficulty.value);result='*';revision++;started=true;b.setOrientation(side);render();think();},'primary'),status,retry]),
      h('section.card.card-pad',[h('h2',{text:'This game'}),moves,h('div.toolbar',[
        button('Take back',()=>{if(busy||!game.history.length)return;game.undo();positions.pop();if(game.turnColor()!==side&&game.history.length){game.undo();positions.pop();}result='*';revision++;render();think();}),
        button('Resign',()=>{if(!started||result!=='*')return;if(!confirm('Resign this game?'))return;++request;busy=false;result=side==='w'?'0-1':'1-0';revision++;render();}),
        button('Analyze game',()=>analyze(pgn())),
        button('Save to database',async()=>{if(!game.history.length)throw new Error('Play a move first.');const rev=revision;await api('games',{pgn:pgn(),collection:'Computer games'});App.toast(revision===rev?'Game saved to Computer games':'Game snapshot saved; save again to include newer moves.');},'primary')])])])]));
    resizeBoard(holder,'computerBoardSize',()=>window.innerWidth>1000?300:0);
    b.setOrientation(side);render();think();return()=>{closed=true;++request;};
  }
  return {mount};
})();

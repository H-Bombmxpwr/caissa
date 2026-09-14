/* PDF reading and opening exploration, shared by modules and analysis panels. */
(function(){
  'use strict';
  let ui;
  const categories=['Games to study','Chess studies','Opening examples','Model games','Endgames','Tactics','Tournament preparation'];
  const get=()=>ui;
  async function separateBook(id){
    if(window.pywebview?.api?.open_book){const r=await window.pywebview.api.open_book(Number(id));if(r.error)throw new Error(r.error);}
    else window.open('/?reader=1&book='+encodeURIComponent(id)+'#workspace/books','_blank','noopener');
  }
  function pdfReader(){
    const {h,api,button,field,select}=get();
    const chosen=select([['','Choose a book']],'');
    const page=h('input',{type:'number',min:1,value:1,'aria-label':'Book page'});
    const frame=h('iframe.pdf-reader',{title:'PDF book',hidden:true});
    const status=h('p.muted',{text:'Add PDFs in Books, then choose one here.'});
    const root=h('div.card-pad.pdf-controls',[field('Book',chosen),h('div.toolbar',[field('Page',page),button('Go to page',async()=>{
      if(!chosen.value)return;await api('books/'+chosen.value,{page:Number(page.value)},'PUT');show();
    }),button('Separate window',()=>{if(!chosen.value)throw new Error('Choose a book first');return separateBook(chosen.value);})]),status,frame]);
    let books=[];
    function show(){frame.hidden=!chosen.value;status.hidden=!!chosen.value;if(chosen.value)frame.src='/api/books/'+chosen.value+'/file#page='+Math.max(1,Number(page.value)||1);else frame.removeAttribute('src');}
    chosen.addEventListener('change',()=>{page.value=books.find(b=>String(b.id)===chosen.value)?.page||1;show();});
    async function refresh(id){const data=await api('books');books=data.books;const previous=String(id||chosen.value||'');chosen.replaceChildren(h('option',{value:'',text:'Choose a book'}),...books.map(b=>h('option',{value:b.id,text:b.title+(b.author?' — '+b.author:'')})));chosen.value=books.some(b=>String(b.id)===previous)?previous:'';page.value=books.find(b=>String(b.id)===chosen.value)?.page||1;show();}
    refresh(new URLSearchParams(location.search).get('book')).catch(e=>status.textContent=e.message);
    return {root,refresh};
  }
  async function booksView(content){
    const {h,api,button,field,heading}=get();
    const reader=pdfReader();
    if(new URLSearchParams(location.search).get('reader')==='1'){
      document.body.classList.add('reader-window');content.append(reader.root);return;
    }
    content.append(heading('Your chess bookshelf','Books','Keep PDFs with your library. Read here, beside analysis, or on another monitor.'));
    const file=h('input',{type:'file',accept:'application/pdf,.pdf'}),title=h('input',{placeholder:'Book title'}),author=h('input',{placeholder:'Author (optional)'}),status=h('p',{role:'status'});
    file.addEventListener('change',()=>{if(file.files[0])title.value=file.files[0].name.replace(/\.pdf$/i,'');});
    content.append(h('section.card.card-pad',[field('Choose PDF',file),field('Title',title),field('Author',author),button('Add PDF',async()=>{
      const selected=file.files[0];if(!selected)throw new Error('Choose a PDF');if(selected.size>128*1024*1024)throw new Error('Choose a PDF smaller than 128 MB');
      status.textContent='Copying PDF into your library…';
      try{const data=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result.split(',')[1]);r.onerror=()=>reject(new Error('Could not read PDF'));r.readAsDataURL(selected);});
        const added=await api('books',{title:title.value,author:author.value,data});await reader.refresh(added.id);status.textContent='PDF saved with your library.';
      }catch(e){status.textContent=e.message;throw e;}
    },'primary'),h('p.muted',{text:'PDF copies and saved page numbers travel with your library. In Analysis → Panels, enable Books to read beside your board.'}),status]),reader.root);
  }
  function indexControls(){
    const {h,api,button,select,field}=get();
    const choice=select([['','Choose collection']],'');const status=h('p.muted',{role:'status'});
    const root=h('div.card-pad',[field('Collection to index',choice),button('Index positions',async()=>{if(!choice.value)throw new Error('Choose a collection');await api('study/index',{collection:Number(choice.value)});}),status]);
    api('collections').then(d=>choice.append(...d.collections.map(c=>h('option',{value:c.id,text:c.name+' ('+c.games+')'})))).catch(e=>status.textContent=e.message);
    return root;
  }
  function openingPanel(getFen,onMove){
    const {h,api,button,field,select}=get();
    let shown={fen:null,sans:[]};
    const source=select([['bundled','Included book — Lichess Elite (offline)'],['local','My indexed games (offline)'],['masters','Lichess Masters — deep reference'],['lichess','Lichess rated games — broad reference']],'bundled');
    const choice=select([['','All indexed collections']],'');const output=h('div');let request=0,timer;
    const since=h('input',{type:'text',placeholder:'e.g. 2000 (Masters) or 2020-01 (Lichess)'}),until=h('input',{type:'text',placeholder:'Latest available'});
    const ratings=select([['','All ratings'],['2200,2500','2200+'],['2000,2200,2500','2000+'],['1600,1800,2000,2200,2500','1600+']],'');
    const speeds=select([['','All time controls'],['rapid,classical','Rapid & classical'],['blitz','Blitz'],['classical','Classical']],'');
    const signin=h('p.muted',{hidden:true,text:'Lichess now requires a signed-in account on its opening explorer. Connect your lichess account in Settings — any token will do; no extra permission is needed.'});
    const online=h('div',{hidden:true},[signin,field('From year / month',since),field('Through year / month',until),field('Lichess rating bands',ratings),field('Lichess time controls',speeds)]);
    const root=h('div.card-pad',[field('Reference database',source),field('Opening-book source',choice),online,button('Refresh opening book',refresh),h('p.muted',{text:'Explore as deep as the database has games: no fixed move-depth cutoff. Online positions are cached in your library. White / draw / Black statistics are game results, not engine evaluations.'}),output]);
    api('collections').then(d=>choice.append(...d.collections.map(c=>h('option',{value:c.id,text:c.name})))).catch(()=>{});
    choice.addEventListener('change',refresh);
    choice.disabled=true;
    api('lichess/account').then(a=>{signin.hidden=!!a.connected;}).catch(()=>{});
    source.addEventListener('change',()=>{online.hidden=['local','bundled'].includes(source.value);choice.disabled=source.value!=='local';ratings.disabled=speeds.disabled=source.value!=='lichess';refresh();});
    for(const control of [since,until,ratings,speeds])control.addEventListener('change',refresh);
    function refresh(){clearTimeout(timer);const id=++request;timer=setTimeout(()=>load(id),250);}
    async function load(id){const fen=getFen();output.textContent='Reading opening book…';try{
      const data=await api('book?'+new URLSearchParams({fen,collection:choice.value,source:source.value,since:since.value,until:until.value,ratings:ratings.value,speeds:speeds.value}));if(id!==request||fen!==getFen())return;
      shown={fen,sans:data.moves.map(m=>m.san)};
      output.replaceChildren();const total=data.moves.reduce((n,m)=>n+m.games,0);
      if(data.book)output.append(h('p',{text:data.book.title+' · Included offline · '+data.book.games.toLocaleString()+' source games · '+data.book.positions.toLocaleString()+' positions · through '+data.book.max_plies/2+' moves · continuations seen in at least '+data.book.min_games+' games'}));
      else if(data.source)output.append(h('p',{text:(data.source==='masters'?'Lichess Masters':'Lichess rated games')+' · '+(data.total||0).toLocaleString()+' games'+(data.stale?' · Offline fallback: older cached results':data.cached?' · Saved reference':' · Online reference')}));
      if(data.opening)output.append(h('strong',{text:data.opening.eco+' · '+data.opening.name}));
      if(!total)output.append(h('p',{text:source.value==='local'?'No continuations indexed here. Select a deep reference above, or index a collection below.':source.value==='bundled'?'This position is outside the included book. Select Lichess Masters or rated games for an online lookup, or explore your own indexed games.':'No games continue from this position with these filters. Broaden the filters or step back.'}));
      for(const m of data.moves)output.append(h('div.book-move',[button(m.san,()=>onMove(m.san)),h('span',{text:`${m.games} games · ${(100*m.games/total).toFixed(1)}% · ${m.white} / ${m.draws} / ${m.black}`}),h('small',{text:m.average_elo?'Average rating '+m.average_elo:''})]));
      for(const g of data.games)output.append(button(g.white+' — '+g.black+' · '+g.date,()=>ui.openGame(g.id)));
      for(const g of data.reference_games||[])output.append(h('a.btn',{href:'https://lichess.org/'+(data.source==='masters'?'study/master/':'')+encodeURIComponent(g.id),target:'_blank',rel:'noopener',text:(g.white?.name||'White')+' — '+(g.black?.name||'Black')+' · '+(g.year||'')+' · Open reference game'}));
    }catch(e){if(id===request)output.textContent=e.message;}}
    return {root,refresh,listed:()=>shown};
  }
  /* One player's openings, scored from that player's side of the board.

     A reference book says what is played here. This says how it went for whoever is
     named — which may be the reader, and just as easily may be Fischer, or the
     strongest player in an imported collection. The score, the win/draw/loss bar and
     the trend all belong to that player. It reads the position index, so a collection
     must be indexed before it has anything to say. */
  function openingReport(getFen,onMove,onLine){
    const {h,api,button,field,select}=get();
    const collection=select([['','Every indexed collection']],'');
    const names=h('datalist',{id:'tree-player-names'});
    const player=h('input',{placeholder:'Player name, as it appears in the games',list:'tree-player-names',autocomplete:'off'});
    const colour=select([['','Both colours'],['w','As White'],['b','As Black']],'');
    const speed=select([['','Any time control'],['bullet','Bullet'],['blitz','Blitz'],
                        ['rapid','Rapid'],['classical','Classical'],['correspondence','Correspondence'],
                        ['blitz,rapid,classical','Blitz and slower']],'');
    const rated=select([['','Rated and casual'],['1','Rated only'],['0','Casual only']],'');
    const since=h('input',{placeholder:'From, e.g. 2023 or 2023-06'});
    const until=h('input',{placeholder:'Until'});
    const minElo=h('input',{type:'number',placeholder:'Opponent rating from',min:0});
    const maxElo=h('input',{type:'number',placeholder:'…to',min:0});
    const minGames=select([['2','2+ games'],['3','3+ games'],['5','5+ games'],['10','10+ games']],'3');
    const summary=h('div.tree-summary');
    const movesBody=h('div');
    // What is on screen, and the position it belongs to. The keyboard reads this
    // rather than scraping the list, so a key pressed before the debounced reload
    // lands cannot play a move from the previous position.
    let shown={fen:null,sans:[]};
    const trendBody=h('div.tree-trend');
    const weakBody=h('div');
    let request=0,timer;

    function params(extra){
      return new URLSearchParams(Object.entries({
        collection:collection.value,player:player.value.trim(),color:colour.value,
        speed:speed.value,rated:rated.value,since:since.value.trim(),until:until.value.trim(),
        min_opponent_elo:minElo.value,max_opponent_elo:maxElo.value,...(extra||{}),
      }).filter(([,v])=>v!==''&&v!=null));
    }
    const pct=v=>v==null?'—':v.toFixed(1)+'%';
    function resultBar(entry){
      const total=entry.games||1;
      const part=(n,cls,label)=>n?h('i.'+cls,{style:{width:(100*n/total)+'%'},title:label+': '+n}):null;
      return h('div.wdl',[part(entry.wins,'won','Wins'),part(entry.draws,'drew','Draws'),
                          part(entry.losses,'lost','Losses')].filter(Boolean));
    }

    function showSummary(data){
      const t=data.totals;
      if(!t.games){
        summary.replaceChildren(h('p.muted',{text:data.player
          ?'No indexed games by '+data.player+' reached this position with these filters.'
          :'No indexed games reached this position. Name a player above, or index a collection below.'}));
        return;
      }
      summary.replaceChildren(
        h('div.tree-score',[h('strong',{text:pct(t.score_pct)}),
          h('small',{text:(data.player?data.player+'’s score':'White’s score')+' from here'})]),
        h('div.tree-counts',[
          h('div',[h('b',{text:t.games.toLocaleString()}),h('small',{text:'games'})]),
          h('div',[h('b',{text:t.wins}),h('small',{text:'won'})]),
          h('div',[h('b',{text:t.draws}),h('small',{text:'drawn'})]),
          h('div',[h('b',{text:t.losses}),h('small',{text:'lost'})]),
          ...(t.avg_opponent_elo?[h('div',[h('b',{text:t.avg_opponent_elo}),h('small',{text:'avg opponent'})])]:[]),
        ]),
        resultBar(t));
    }

    function showMoves(data){
      shown={fen:data.fen,sans:data.moves.map(m=>m.san)};
      movesBody.replaceChildren();
      if(!data.moves.length){
        movesBody.append(h('p.muted',{text:'Nothing was played from here in the indexed games.'}));
        return;
      }
      const best=Math.max(...data.moves.map(m=>m.games));
      for(const m of data.moves){
        movesBody.append(h('div.tree-move',[
          button(m.san,()=>onMove(m.san),'tree-san'),
          h('div.tree-bars',[
            h('div.tree-volume',[h('i',{style:{width:(100*m.games/best)+'%'}}),
              h('span',{text:m.games+' game'+(m.games===1?'':'s')+' · '+m.share_pct+'%'})]),
            resultBar(m)]),
          h('div.tree-figures',[h('b',{text:pct(m.score_pct),
              title:'Score from '+(data.player||'White')+'’s side'}),
            h('small',{text:[m.avg_opponent_elo?'vs '+m.avg_opponent_elo:'',
                             m.last_played?'last '+m.last_played.slice(0,4):''].filter(Boolean).join(' · ')})]),
        ]));
      }
    }

    function showTrend(data){
      trendBody.replaceChildren();
      if(data.trend.length<2){
        trendBody.append(h('p.muted',{text:'A trend needs games in at least two different years.'}));
        return;
      }
      trendBody.append(h('div.eyebrow',{text:'Score by year from this position'}));
      const chart=h('div.tree-years');
      for(const year of data.trend){
        chart.append(h('div.tree-year',{title:year.games+' games, '+pct(year.score_pct)},[
          h('i',{style:{height:Math.max(3,Math.round(year.score_pct))+'%'},
                 class:year.score_pct>=55?'good':year.score_pct<45?'poor':'level'}),
          h('small',{text:year.period.slice(2)})]));
      }
      trendBody.append(chart,h('p.muted',{text:'Bars are the score out of 100 in that year; the count is on hover. A line that stopped working shows up here first.'}));
    }

    async function loadWeakest(){
      weakBody.replaceChildren(h('p.muted',{text:'Looking for the lines that cost the most…'}));
      try{
        const data=await api('tree/weakest?'+params({min_games:minGames.value,limit:12}));
        weakBody.replaceChildren();
        if(!data.weakest.length){
          weakBody.append(h('p.muted',{text:data.player
            ?'No line scores below even with that many games. Lower the threshold, or widen the filters.'
            :'Name a player above: a weakest-lines list only means something from one side of the board.'}));
          return;
        }
        weakBody.append(h('p.muted',{text:'Ranked by points dropped — games multiplied by the shortfall against an even score — so a line played often at 40% outranks one played twice at 0%.'}));
        for(const entry of data.weakest){
          weakBody.append(h('div.tree-weak',[
            h('button.linkish',{type:'button',text:entry.line||entry.san,
              title:'Put this line on the board',onclick:()=>onLine(entry.moves||[])}),
            h('div.tree-weak-figures',[
              h('b',{text:pct(entry.score_pct)}),
              h('small',{text:entry.games+' games · '+entry.points_dropped+' points dropped'})]),
            resultBar(entry)]));
        }
      }catch(err){weakBody.replaceChildren(h('p.error-message',{text:err.message}));}
    }

    async function load(){
      const id=++request;
      summary.replaceChildren(h('p.muted',{text:'Reading your games…'}));
      try{
        const data=await api('tree/position?'+params({fen:getFen()}));
        if(id!==request)return;
        showSummary(data);showMoves(data);showTrend(data);
      }catch(err){if(id===request)summary.replaceChildren(h('p.error-message',{text:err.message}));}
    }
    function refresh(){clearTimeout(timer);timer=setTimeout(load,200);}
    function refreshAll(){refresh();loadWeakest();}

    async function suggest(){
      try{
        const data=await api('tree/players?'+new URLSearchParams({collection:collection.value,limit:60}));
        names.replaceChildren(...data.players.map(p=>h('option',{value:p.name,label:p.games+' games'})));
        return data.players.map(p=>p.name);
      }catch(e){return [];}          // typing still works without suggestions
    }
    api('collections').then(d=>{
      collection.append(...d.collections.map(c=>h('option',{value:c.id,text:c.name+' · '+c.games+' games'})));
      suggest();
    }).catch(()=>{});
    collection.addEventListener('change',async()=>{
      shown={fen:null,sans:[]};
      // The names in the old collection mean nothing in the new one, so the
      // suggestions are re-read and a player who is not in it is cleared rather
      // than left behind to report zero games with no explanation.
      const known=await suggest();
      if(player.value.trim()&&!known.some(name=>name.toLowerCase().includes(player.value.trim().toLowerCase()))){
        player.value='';
        App.toast('That player has no games in this collection, so the name was cleared.');
      }
      refreshAll();
    });
    player.addEventListener('change',refreshAll);
    for(const control of [colour,speed,rated,since,until,minElo,maxElo])control.addEventListener('change',refreshAll);
    minGames.addEventListener('change',loadWeakest);

    const root=h('div',[
      h('div.card-pad',[
        h('p.muted',{text:'One player’s games, scored from that player’s side of the board. Name the player below — yourself, or whoever the collection is of — and every figure reads as their result rather than White’s. Leave it empty to read the collection from White’s side. Needs an indexed collection.'}),
        field('Collection',collection),names,field('Player',player),
        h('div.toolbar',[field('Colour',colour),field('Time control',speed),field('Rated',rated)]),
        h('div.toolbar',[field('From',since),field('Until',until)]),
        h('div.toolbar',[field('Opponent rating from',minElo),field('Opponent rating to',maxElo)]),
        summary]),
      h('div.divider'),h('div.card-pad',[h('div.eyebrow',{text:'Moves played from here'}),movesBody]),
      h('div.divider'),h('div.card-pad',[trendBody]),
      h('div.divider'),h('div.card-pad',[h('div.eyebrow',{text:'Where the points go'}),
        field('Only lines with',minGames),weakBody]),
    ]);
    refreshAll();
    return {root,refresh:refreshAll,player,collection,listed:()=>shown};
  }
  async function openingView(content){
    const {h,button,heading}=get();let game=new Chess();const history=[];
    content.append(heading('Walk the tree','Opening explorer','Browse a collection\u2019s openings move by move \u2014 what was played, how it scored, and where the points went. Reference databases are a tab away.'));
    const holder=h('div.board-holder'),board=new Board(holder,
      {viewOnly:false,orientation:ui.explorerOrientation?.()||'w'});
    const line=h('p');
    const panel=openingPanel(()=>game.fen(),play);
    const report=openingReport(()=>game.fen(),play,replay);
    // Two readings of the same board: the reference, and your own results.
    const tabs=h('div.context-tabs');
    const pane=h('div');
    let showing='Collection tree';
    function choose(name){showing=name;
      tabs.querySelectorAll('button').forEach(b=>b.classList.toggle('active',b.textContent===name));
      pane.replaceChildren(name==='Collection tree'?report.root:panel.root);
      refresh();}
    for(const name of ['Collection tree','Reference databases'])
      tabs.append(h('button',{type:'button',text:name,onclick:()=>choose(name)}));
    function play(input){const moved=game.move(input);if(!moved)throw new Error('Illegal book move');
      history.push(game.fen());played.push(moved.san);render();}
    function replay(moves){
      const fresh=new Chess();history.length=0;played.length=0;
      for(const san of moves||[]){const moved=fresh.move(san);if(!moved)break;
        history.push(fresh.fen());played.push(moved.san);}
      game=fresh;render();
    }
    function refresh(){if(showing==='Collection tree')report.refresh();else panel.refresh();}
    // Studying a Black repertoire from White's side is needlessly hard work, and the
    // choice is remembered so it survives leaving the module and coming back.
    function flip(){
      board.toggleOrientation();
      ui.saveExplorerOrientation?.(board.opts.orientation);
    }
    const played=[];                       // the SAN of the line currently on the board
    function render(){
      board.setPosition(game);
      board.setMovable({color:game.turnColor(),dests:game.destinationsMap(),
        onMove:(from,to)=>play({from,to,promotion:'q'})});
      line.replaceChildren(played.length
        ?h('span.tree-path',played.map((san,i)=>h('button.linkish',{type:'button',
            text:(i%2===0?(i/2+1)+'.':'')+san+' ',title:'Back to here',
            onclick:()=>replay(played.slice(0,i+1))})))
        :h('span.muted',{text:'Starting position \u2014 play a move, or choose one below, to walk the tree.'}));
      refresh();
      setTimeout(highlight,260);           // after the debounced report has redrawn
    }
    // Walking a tree is a keyboard job: left steps back, right takes the most played
    // continuation, and up/down pick a different one without reaching for the mouse.
    let choice=0;
    function keys(event){
      if(!document.body.contains(line))return document.removeEventListener('keydown',keys);
      if(/INPUT|TEXTAREA|SELECT/.test(event.target.tagName)||event.target.isContentEditable)return;
      if(event.ctrlKey||event.altKey||event.metaKey||document.querySelector('dialog[open]'))return;
      const step={ArrowLeft:1,ArrowRight:1,ArrowUp:1,ArrowDown:1,Home:1}[event.key];
      if(!step)return;
      event.preventDefault();
      if(event.key==='ArrowLeft')return replay(played.slice(0,-1));
      if(event.key==='Home')return replay([]);
      // Only act on a list that belongs to the position on the board; a reload in
      // flight means the answer for this position is not in yet.
      const {fen,sans}=(showing==='Collection tree'?report:panel).listed();
      if(fen!==game.fen()||!sans.length)return;
      if(event.key==='ArrowRight'){const san=sans[Math.min(choice,sans.length-1)];choice=0;
        try{play(san);}catch(err){/* not legal from here after all */}return;}
      choice=Math.max(0,Math.min(sans.length-1,choice+(event.key==='ArrowDown'?1:-1)));
      highlight();
    }
    function highlight(){
      document.querySelectorAll('.tree-move,.book-move').forEach((row,i)=>
        row.classList.toggle('chosen',i===choice));
    }
    document.addEventListener('keydown',keys);
    content.append(h('div.opening-grid',[h('div',[holder,line,h('div.toolbar',[button('Back a move',()=>replay(played.slice(0,-1))),button('Start again',()=>replay([])),button('Flip board',flip),button('Analyze this position',()=>ui.analyzeFen(game.fen())),button('Open these games',()=>ui.browsePosition(game.fen()))]),
      h('p.muted.key-hint',{text:'← back · → play the highlighted move · ↑ ↓ choose one · Home to the start'})]),h('section.card',[tabs,pane,indexControls(),h('p.card-pad.muted',{text:'Import PGNs from Master games or Online & imports, then index them. ChessBase CTG/CTB/CTO and Polyglot BIN files are not imported by this module.'})])]));
    ui.resizeBoard(holder,'openingBoardSize');choose('Collection tree');render();
  }
  function localFacts(parsed){
    const {h}=get(),line=PGN.mainline(parsed.root);let captures=0,promotions=0,castles=0;
    for(const n of line){if(n.move?.captured)captures++;if(n.move?.promotion)promotions++;if(/^O-O/.test(n.san))castles++;}
    const facts=[`${line.length} plies (${Math.ceil(line.length/2)} move numbers) recorded.`,`${captures} captures, ${castles} castling moves, ${promotions} promotions in the main line.`];
    if(line.at(-1)?.san.endsWith('#'))facts.push('The final recorded move is checkmate.');
    if(parsed.headers.Annotator)facts.push('Annotated by '+parsed.headers.Annotator+'.');
    return h('section.local-facts',[h('h3',{text:'From this game’s PGN'}),...facts.map(text=>h('p',{text}))]);
  }
  function networkStatus(){
    const {h,api,button}=get();const text=h('p.network-status',{role:'status',text:navigator.onLine?'Online connection reported by this device.':'Offline: local library, PDFs and Stockfish still work.'});
    const root=h('section.card.card-pad',[h('h2',{text:'Connection'}),text,button('Check online services',async()=>{text.textContent='Checking PGN Mentor…';const result=await api('network');text.textContent=result.reachable?'Online — PGN Mentor is reachable.':'PGN Mentor is unreachable. Your device reports '+(navigator.onLine?'an online connection; the service may be blocked or unavailable.':'offline.');})]);
    return root;
  }
  function positionLibrary(fen,data,play){
    const {h,api,field,select,button,openGame}=get();
    const root=h('section',[h('h3',{text:data.moves.length+' candidate moves from this position'}),h('p.muted',{text:data.indexed_games.toLocaleString()+' games indexed across your library. Counts below show games that continued with each move.'})]);
    for(const m of data.moves)root.append(h('div.book-move',[button(m.san,()=>play(m.san)),h('span',{text:m.games+' games · White '+m.white+' / draw '+m.draws+' / Black '+m.black})]));
    if(!data.moves.length)root.append(h('p',{text:'No recorded continuations. This may be a final position, or its collection may need indexing.'}));
    const player=h('input',{placeholder:'Player, tournament or annotator'}),result=select([['','Any result'],['1-0','White won'],['0-1','Black won'],['1/2-1/2','Draw']],'');
    const annotated=select([['','Any annotation status'],['1','Annotated only']],'');
    const collection=select([['','All collections']],'');const examples=h('div');let request=0;
    api('collections').then(d=>collection.append(...d.collections.map(c=>h('option',{value:c.id,text:c.name})))).catch(()=>{});
    root.append(h('h3',{text:'Example games reaching this exact position'}),h('div.example-filters',[field('Example search',player),field('Example result',result),field('Example annotations',annotated),field('Example collection',collection),button('Find examples',find)]),examples);
    for(const control of [player,result,annotated,collection])control.addEventListener('change',find);
    async function find(){const id=++request;examples.textContent='Finding example games…';try{const found=await api('games?'+new URLSearchParams({position:fen,q:player.value,result:result.value,annotated:annotated.value,collection:collection.value,limit:12,sort:'elo'}));if(id!==request)return;
      examples.replaceChildren(h('p.muted',{text:found.total+' matching games'+(found.total>12?' · showing the 12 highest rated':'')}));
      for(const g of found.games)examples.append(h('div.context-item',[button(g.white+' — '+g.black,()=>openGame(g.id)),h('p.muted',{text:[g.event,g.date,g.result,Math.ceil(g.ply_count/2)+' moves',g.annotator?'Annotated by '+g.annotator:''].filter(Boolean).join(' · ')} )]));
    }catch(e){if(id===request)examples.textContent=e.message;}}
    const children=[...root.children],split=children.findIndex(n=>n.tagName==='H3'&&n.textContent.startsWith('Example games'));
    const tabs=h('div.section-tabs'),pane=h('div');
    if(split>=0){const groups=[['Continuations',children.slice(0,split)],['Example games',children.slice(split)]];
      function show(label,nodes){pane.replaceChildren(...nodes);tabs.querySelectorAll('button').forEach(b=>{b.classList.toggle('active',b.textContent===label);b.setAttribute('aria-pressed',String(b.textContent===label));});}
      groups.forEach(([label,nodes])=>tabs.append(button(label,()=>show(label,nodes))));root.replaceChildren(tabs,pane);show(...groups[0]);}
    find();return root;
  }
  function studyTree(state,actions){
    const {h,button,field,select,api}=get(),tree=h('div.study-tree'),cards=new Map();
    const listFor=id=>state.assignments.filter(a=>a.folder_id===id).map(a=>state.collections.find(c=>c.id===a.collection_id)).filter(Boolean);
    function collection(c){const count=c.indexed_games||0,ready=c.games>0&&count===c.games;return h('div.collection-leaf'+(ready?'.indexed':'.needs-index'),[h('span.index-badge',{text:ready?'✓ Indexed':count?'Partially indexed':'Not indexed',title:count+' of '+c.games+' games indexed'}),button(c.name,()=>actions.browse(c)),h('small',{text:count+' / '+c.games+' indexed'})]);}
    for(const folder of state.folders){
      const children=state.folders.filter(f=>f.parent_id===folder.id),collections=listFor(folder.id),parent=state.folders.find(f=>f.id===folder.parent_id);
      const node=h('details.study-node',{open:true,'data-folder-id':folder.id},[h('summary',[h('b',{text:folder.name}),h('span.kind-badge',{text:folder.category}),h('small',{text:children.length+' subfolders · '+collections.length+' collections'})]),h('div.folder-tools',[h('p.breadcrumb',{text:'Study folders / '+(parent?folder.path:'Top level / '+folder.name)}),field('Study category',select(categories,folder.category||categories[0],async e=>{await api('study/folders/'+folder.id,{category:e.target.value},'PUT');folder.category=e.target.value;node.querySelector('.kind-badge').textContent=e.target.value;})),h('div.toolbar',[button('Add collection',()=>actions.assign(folder)),button('New subfolder',()=>actions.create(folder.id)),button('Delete folder',()=>actions.remove(folder),'danger')])]),...collections.map(collection)]);
      cards.set(folder.id,node);
    }
    const top=h('section',[h('h3',{text:'Study folders · top level'})]);tree.append(h('p.muted',{text:'Folders contain subfolders and collections. Collections contain games. Repertoires are separate sets of lines to practise.'}),h('div.toolbar',[button('Expand all',()=>tree.querySelectorAll('details').forEach(d=>d.open=true)),button('Collapse all',()=>tree.querySelectorAll('details').forEach(d=>d.open=false))]),top);
    for(const folder of state.folders)(cards.get(folder.parent_id)||top).append(cards.get(folder.id));
    const unfiled=state.collections.filter(c=>!state.assignments.some(a=>a.collection_id===c.id));
    tree.append(h('section.unfiled-collections',[h('h3',{text:'Unfiled collections · '+unfiled.length}),h('p.muted',{text:'These collections are at library level, outside study folders. Use Add collection on a folder to file one.'}),...unfiled.map(collection)]),h('section',[h('h3',{text:'Repertoires · separate practice library'}),button('Open repertoire lines and drills',actions.repertoire)]));return tree;
  }
  window.LibraryTools={init(value){ui=value;},categories,pdfReader,booksView,openingPanel,openingReport,openingView,indexControls,localFacts,networkStatus,positionLibrary,studyTree};
  for(const name of ['online','offline'])window.addEventListener(name,()=>document.querySelectorAll('.network-status').forEach(el=>el.textContent=name==='online'?'Online connection reported by this device.':'Offline: local library, PDFs and Stockfish still work.'));
})();

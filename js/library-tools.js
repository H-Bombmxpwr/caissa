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
    const refresh=async()=>{const data=await api('study/index');status.textContent=data.running?`Indexing ${data.collection}: ${data.done}/${data.total}`:data.error||`${data.done} games processed; ${data.errors} errors. Refresh the book or position view when finished.`;};
    const root=h('div.card-pad',[field('Collection to index',choice),h('div.toolbar',[button('Index positions',async()=>{if(!choice.value)throw new Error('Choose a collection');await api('study/index',{collection:Number(choice.value)});await refresh();}),button('Check indexing progress',refresh)]),status]);
    api('collections').then(d=>choice.append(...d.collections.map(c=>h('option',{value:c.id,text:c.name+' ('+c.games+')'})))).catch(e=>status.textContent=e.message);
    return root;
  }
  function openingPanel(getFen,onMove){
    const {h,api,button,field,select}=get();
    const source=select([['bundled','Included book — Lichess Elite (offline)'],['local','My indexed games (offline)'],['masters','Lichess Masters — deep reference'],['lichess','Lichess rated games — broad reference']],'bundled');
    const choice=select([['','All indexed collections']],'');const output=h('div');let request=0,timer;
    const since=h('input',{type:'text',placeholder:'e.g. 2000 (Masters) or 2020-01 (Lichess)'}),until=h('input',{type:'text',placeholder:'Latest available'});
    const ratings=select([['','All ratings'],['2200,2500','2200+'],['2000,2200,2500','2000+'],['1600,1800,2000,2200,2500','1600+']],'');
    const speeds=select([['','All time controls'],['rapid,classical','Rapid & classical'],['blitz','Blitz'],['classical','Classical']],'');
    const online=h('div',{hidden:true},[field('From year / month',since),field('Through year / month',until),field('Lichess rating bands',ratings),field('Lichess time controls',speeds)]);
    const root=h('div.card-pad',[field('Reference database',source),field('Opening-book source',choice),online,button('Refresh opening book',refresh),h('p.muted',{text:'Explore as deep as the database has games: no fixed move-depth cutoff. Online positions are cached in your library. White / draw / Black statistics are game results, not engine evaluations.'}),output]);
    api('collections').then(d=>choice.append(...d.collections.map(c=>h('option',{value:c.id,text:c.name})))).catch(()=>{});
    choice.addEventListener('change',refresh);
    choice.disabled=true;
    source.addEventListener('change',()=>{online.hidden=['local','bundled'].includes(source.value);choice.disabled=source.value!=='local';ratings.disabled=speeds.disabled=source.value!=='lichess';refresh();});
    for(const control of [since,until,ratings,speeds])control.addEventListener('change',refresh);
    function refresh(){clearTimeout(timer);const id=++request;timer=setTimeout(()=>load(id),250);}
    async function load(id){const fen=getFen();output.textContent='Reading opening book…';try{
      const data=await api('book?'+new URLSearchParams({fen,collection:choice.value,source:source.value,since:since.value,until:until.value,ratings:ratings.value,speeds:speeds.value}));if(id!==request||fen!==getFen())return;
      output.replaceChildren();const total=data.moves.reduce((n,m)=>n+m.games,0);
      if(data.book)output.append(h('p',{text:data.book.title+' · Included offline · '+data.book.games.toLocaleString()+' source games · '+data.book.positions.toLocaleString()+' positions · through '+data.book.max_plies/2+' moves · continuations seen in at least '+data.book.min_games+' games'}));
      else if(data.source)output.append(h('p',{text:(data.source==='masters'?'Lichess Masters':'Lichess rated games')+' · '+(data.total||0).toLocaleString()+' games'+(data.stale?' · Offline fallback: older cached results':data.cached?' · Saved reference':' · Online reference')}));
      if(data.opening)output.append(h('strong',{text:data.opening.eco+' · '+data.opening.name}));
      if(!total)output.append(h('p',{text:source.value==='local'?'No continuations indexed here. Select a deep reference above, or index a collection below.':source.value==='bundled'?'This position is outside the included book. Select Lichess Masters or rated games for an online lookup, or explore your own indexed games.':'No games continue from this position with these filters. Broaden the filters or step back.'}));
      for(const m of data.moves)output.append(h('div.book-move',[button(m.san,()=>onMove(m.san)),h('span',{text:`${m.games} games · ${(100*m.games/total).toFixed(1)}% · ${m.white} / ${m.draws} / ${m.black}`}),h('small',{text:m.average_elo?'Average rating '+m.average_elo:''})]));
      for(const g of data.games)output.append(button(g.white+' — '+g.black+' · '+g.date,()=>ui.openGame(g.id)));
      for(const g of data.reference_games||[])output.append(h('a.btn',{href:'https://lichess.org/'+(data.source==='masters'?'study/master/':'')+encodeURIComponent(g.id),target:'_blank',rel:'noopener',text:(g.white?.name||'White')+' — '+(g.black?.name||'Black')+' · '+(g.year||'')+' · Open reference game'}));
    }catch(e){if(id===request)output.textContent=e.message;}}
    return {root,refresh};
  }
  async function openingView(content){
    const {h,button,heading}=get();let game=new Chess();const history=[];
    content.append(heading('Learn from the games','Opening book','Explore deep lines from Lichess Masters, rated games, or your own indexed PGNs. Choose a reference database below.'));
    const holder=h('div.board-holder',{style:{maxWidth:'520px'}}),board=new Board(holder,{viewOnly:false});
    const panel=openingPanel(()=>game.fen(),play),line=h('p');
    function play(san){if(!game.move(san))throw new Error('Illegal book move');history.push(game.fen());render();}
    function render(){board.setPosition(game);board.setMovable({color:game.turnColor(),dests:game.destinationsMap(),onMove:(from,to)=>play({from,to,promotion:'q'})});line.textContent='Position after '+history.length+' plies';panel.refresh();}
    content.append(h('div.settings-grid',[h('div',[holder,line,h('div.toolbar',[button('Back',()=>{history.pop();game=new Chess(history[history.length-1]||Chess.DEFAULT_FEN);render();}),button('Reset opening',()=>{history.length=0;game=new Chess();render();}),button('Analyze this position',()=>ui.analyzeFen(game.fen()))])]),h('section.card',[panel.root,indexControls(),h('p.card-pad.muted',{text:'Import PGNs from Master games or Online & imports, then index them. ChessBase CTG/CTB/CTO and Polyglot BIN files are not imported by this module.'})])]));render();
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
    find();return root;
  }
  function studyTree(state,actions){
    const {h,button,field,select,api}=get(),tree=h('div.study-tree'),cards=new Map();
    const listFor=id=>state.assignments.filter(a=>a.folder_id===id).map(a=>state.collections.find(c=>c.id===a.collection_id)).filter(Boolean);
    function collection(c){return h('div.collection-leaf',[h('span.kind-badge',{text:'Collection'}),button(c.name,()=>actions.browse(c)),h('small',{text:c.games+' games'})]);}
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
  window.LibraryTools={init(value){ui=value;},categories,pdfReader,booksView,openingPanel,openingView,indexControls,localFacts,networkStatus,positionLibrary,studyTree};
  for(const name of ['online','offline'])window.addEventListener(name,()=>document.querySelectorAll('.network-status').forEach(el=>el.textContent=name==='online'?'Online connection reported by this device.':'Offline: local library, PDFs and Stockfish still work.'));
})();

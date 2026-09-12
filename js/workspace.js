/* Caissa desktop workspace. No framework and no build step. */
(function () {
  'use strict';
  const h = App.h;
  const state = {view:'database', collections:[], folders:[], assignments:[], offset:0, filters:{},
    selected:null, parsed:null, node:null, dirty:false, context:'Library', route:0, prefs:{}, rep:null,
    boards:[], boardIndex:0};
  // Light squares first, then dark. The last four are dark palettes; they stay light enough
  // that the black pieces' outlines still read against the dark squares.
  const themes = {Sage:['#ecebd9','#73917c'], Walnut:['#f0d9b5','#b58863'], Slate:['#e3e7eb','#8293a2'],
    Sand:['#f5e9d0','#b7a17b'], Forest:['#e1e4cd','#4e7560'], Rose:['#f1e0da','#ae8584'],
    Ocean:['#dbe6f0','#5a7fa3'], Maple:['#f6e0bf','#c08a4e'], Lilac:['#e9e5f2','#8a7cae'],
    Coral:['#f7e3d8','#c07f66'], Midnight:['#6b7a91','#3a4759'], Graphite:['#787b7e','#474b4f'],
    Pine:['#5c7767','#334739'], Espresso:['#7d6155','#4a362e']};
  const modules = [['database','▤','Database'],['analysis','♙','Analysis board'],['repertoire','♧','Repertoire'],
    ['masters','♜','Master games'],['imports','⇣','Online & imports'],['studies','▱','Study folders'],
    ['training','◉','Blindfold training'],['tactics','♞','Tactics'],['settings','⚙','Settings']];
  let content, nav, crumb, board, preview, poll, liveTimer;
  let engineQueue=Promise.resolve();
  async function api(path, body, method) {
    if(path==='engine/live'&&(body||method==='DELETE')){
      engineQueue=engineQueue.catch(()=>{}).then(()=>rawApi(path,body,method));
      return engineQueue;
    }
    return rawApi(path,body,method);
  }
  async function rawApi(path, body, method) {
    const response = await fetch('/api/' + path, {method:method || (body ? 'POST' : 'GET'),
      headers:body ? {'Content-Type':'application/json'} : {}, body:body ? JSON.stringify(body) : undefined});
    const data = await response.json();
    if(data.batch_id&&state.view==='imports')await importHistory();
    if (!response.ok) throw new Error(data.error || 'Request failed');
    return data;
  }
  function act(fn) { return async function (event) {try {await fn(event);} catch(err) {App.toast(err.message,5000);}}; }
  function button(text, fn, cls) {return h('button.btn' + (cls ? '.' + cls : ''), {type:'button',text,onclick:act(fn)});}
  function link(text,url) {return h('a',{text,href:url,target:'_blank',rel:'noopener noreferrer'});}
  function field(label, control) {if(/INPUT|SELECT|TEXTAREA/.test(control.tagName)&&!control.hasAttribute('aria-label'))control.setAttribute('aria-label',label);return h('label.field',[h('span',{text:label}),control]);}
  function select(options,value,onchange) {const el=h('select',{onchange},options.map(o=>h('option',{value:Array.isArray(o)?o[0]:o,text:Array.isArray(o)?o[1]:o})));el.value=value;return el;}
  /* ---------- imports in flight ---------- */
  // An import finishes on the server whether or not the view that started it is still on
  // screen, so the progress and the refresh that follows it live outside any one view.
  let importBanner=null,importPoll=null,importSeen=false;
  function importProgress(status){
    if(!importBanner){importBanner=h('div.import-banner',{role:'status'},[h('strong'),h('div.progress-track',[h('span')]),h('small')]);document.body.append(importBanner);}
    const [label,track,note]=importBanner.children;
    label.textContent='Importing into '+(status.label||'your library')+'…';
    const percent=status.total?Math.round(status.done/status.total*100):0;
    track.classList.toggle('indeterminate',!status.total);
    track.firstChild.style.width=status.total?Math.max(percent,2)+'%':'';
    note.textContent=status.total?status.done.toLocaleString()+' of '+status.total.toLocaleString()+' games · '+percent+'%':'Fetching games…';
  }
  function watchImport(){
    if(importPoll)return;
    importPoll=setInterval(act(async()=>{
      const status=await api('import/status');
      if(status.running){importSeen=true;importProgress(status);return;}
      clearInterval(importPoll);importPoll=null;
      if(importBanner){importBanner.remove();importBanner=null;}
      if(!importSeen)return;
      importSeen=false;
      if(status.error){App.toast('Import failed: '+status.error,6000);return;}
      App.toast('Imported '+status.added+' games · '+status.duplicates+' duplicates'+(status.skipped?' · '+status.skipped+' skipped':''),6000);
      await refreshMeta();
      if(state.view==='database'||state.view==='imports')await go(state.view);
    }),700);
  }
  // Opening suggestions come from the library's own games, and carry the ECO span each
  // name covers so the range fields can fill themselves in.
  function openingPicker(onPick,initial){
    const id='openings-'+Math.random().toString(36).slice(2,9);
    const list=h('datalist',{id});
    const input=h('input',{list:id,value:initial||'',autocomplete:'off',placeholder:'Start typing: Sicilian, King’s Indian…'});
    let known=[],timer;
    async function load(){
      const data=await api('openings?'+new URLSearchParams({q:input.value.trim()}));
      known=data.openings;
      list.replaceChildren(...known.map(o=>h('option',{value:o.name,
        label:(o.eco_from?(o.eco_from===o.eco_to?o.eco_from:o.eco_from+'–'+o.eco_to)+' · ':'')+o.games+' games'})));
    }
    input.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(act(async()=>{
      await load();const hit=known.find(o=>o.name===input.value);if(hit&&onPick)onPick(hit);}),220);});
    load().catch(()=>{});
    return {input,list,match:()=>known.find(o=>o.name===input.value)||null};
  }
  function colourSelect(current){return select([['','Either colour'],['white','Played White'],['black','Played Black']],current||'');}
  function outcomeSelect(current){return select([['','Any outcome'],['win','Won'],['loss','Lost'],['draw','Drew']],current||'');}
  // lichess and ChessBase hide machine data inside comments as {[%name body]} commands.
  // The big one is [%evp from,to,cp,cp,...]: a centipawn score for every ply in that
  // range. Left alone it reads as noise in the notes, so the commands are lifted out of
  // the comment text, shown beside the moves they belong to, and put back by serialize().
  const PGN_COMMAND=/\[%(\w+)\s*([^\]]*)\]/g;
  const NAG_SYMBOLS={$1:'!',$2:'?',$3:'!!',$4:'??',$5:'!?',$6:'?!',$7:'□',$10:'=',$11:'=',$12:'=',
    $13:'∞',$14:'⩲',$15:'⩱',$16:'±',$17:'∓',$18:'+−',$19:'−+',
    $22:'⊙',$23:'⊙',$32:'⟳',$33:'⟳',$36:'→',$37:'→',$40:'↑',$41:'↑',
    $44:'=∞',$132:'⇆',$133:'⇆',$140:'∆',$141:'∇',$142:'⌓',$145:'RR'};
  function allNodes(root){const out=[];(function walk(n){out.push(n);n.children.forEach(walk);})(root);return out;}
  function harvestCommands(parsed){
    if(parsed.harvested)return parsed;
    const evals={};
    for(const node of allNodes(parsed.root)){
      if(!node.comment)continue;
      const kept=[];
      const text=node.comment.replace(PGN_COMMAND,(whole,name,body)=>{
        kept.push(whole);
        const lower=name.toLowerCase();
        if(lower==='evp'){
          const numbers=body.split(',').map(v=>parseInt(v,10));
          const from=numbers[0],to=numbers[1];
          if(Number.isFinite(from)&&Number.isFinite(to))
            for(let i=2;i<numbers.length&&from+i-2<=to;i++)
              if(Number.isFinite(numbers[i]))evals[from+i-2]={cp:numbers[i]};
        } else if(lower==='eval'){
          const mate=/^#(-?\d+)/.exec(body.trim());
          // A per-move [%eval] belongs to this node wherever it sits, variations included.
          if(mate)node.eval={mate:parseInt(mate[1],10)};
          else if(Number.isFinite(parseFloat(body)))node.eval={cp:Math.round(parseFloat(body)*100)};
        }
        return ' ';
      }).replace(/\s+/g,' ').trim();
      if(kept.length){node.commands=(node.commands||[]).concat(kept);node.comment=text||null;}
    }
    // evp is a list for the game's main line, so only the main line takes those scores:
    // a variation move at the same ply is a different position and borrows nothing.
    for(const node of [parsed.root,...PGN.mainline(parsed.root)])
      if(!node.eval&&evals[node.ply])node.eval=evals[node.ply];
    parsed.harvested=true;
    return parsed;
  }
  function evalLabel(entry){
    if(!entry)return '';
    if(entry.mate!=null)return (entry.mate<0?'-#':'#')+Math.abs(entry.mate);
    return (entry.cp>0?'+':entry.cp<0?'-':'')+Math.abs(entry.cp/100).toFixed(2);
  }
  // Nobody remembers 500 ECO codes. Show the PGN's own opening name when it has one,
  // and otherwise the volume the code belongs to, with the code itself always in view.
  const ECO_VOLUMES = {A:'Flank openings', B:'Semi-open games', C:'Open games and the French',
    D:'Closed and semi-closed games', E:'Indian defences'};
  function openingLabel(game){
    const eco=(game.eco||'').trim().toUpperCase(), name=(game.opening||'').trim();
    return {name:name||ECO_VOLUMES[eco[0]]||'Unclassified', eco:/^[A-E]\d\d$/.test(eco)?eco:''};
  }
  // A row of labelled thumbnails, used where a <select> cannot show what it is offering.
  function thumbPicker(label,items,current,onpick){
    const group=h('div.swatches',{role:'group','aria-label':label});
    for(const [value,text,art] of items){
      const choice=h('button.swatch.piece-swatch'+(current===value?'.active':''),{type:'button',title:text,'aria-pressed':String(current===value),
        onclick:act(async()=>{group.querySelectorAll('button').forEach(b=>{b.classList.toggle('active',b===choice);b.setAttribute('aria-pressed',String(b===choice));});await onpick(value);})},[art,h('small',{text})]);
      group.append(choice);
    }
    return group;
  }
  function heading(kicker,title,description,actions) {return h('div.page-heading',[h('div',[h('div.eyebrow',{text:kicker}),h('h1',{text:title}),h('p',{text:description})]),h('div.toolbar',actions||[])]);}
  function card(title,body,actions) {return h('section.card',[h('div.card-head',[h('h2',{text:title}),h('div.toolbar',actions||[])]),body]);}
  function empty(title,text,actions) {return h('div.empty',[h('h3',{text:title}),h('p',{text}),h('div.toolbar',{style:{justifyContent:'center'}},actions||[])]);}
  function download(text,name,type) {const url=URL.createObjectURL(new Blob([text],{type:type||'application/x-chess-pgn'}));const a=h('a',{href:url,download:name});a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  function modal(title,build) {
    const dialog=h('dialog.dialog-backdrop');const body=h('div.dialog-content',[h('h2',{text:title})]);
    dialog.append(body);document.body.append(dialog);build(body,()=>dialog.close());
    dialog.addEventListener('close',()=>dialog.remove());dialog.showModal();return dialog;
  }
  async function refreshMeta() {
    const [c,f]=await Promise.all([api('collections'),api('study/folders')]);
    state.collections=c.collections;state.folders=f.folders;state.assignments=f.assignments;state.studyRoot=f.root;
  }
  async function storageSettings(){
    const bridge=window.pywebview?.api;
    const info=bridge?.storage_info?await bridge.storage_info():{path:(await api('stats')).data_dir};
    const path=h('input',{value:info.path,readonly:true,'aria-label':'Current storage folder'});
    const status=h('p.status-message',{text:info.error?'The storage change could not be completed: '+info.error:info.pending?'Next launch: '+info.pending:''});
    const selection=h('p.muted');
    const use=button('Use selected folder',async()=>{
      const result=await window.pywebview.api.use_storage_folder();
      if(result.error)throw new Error(result.error);
      status.textContent='Saved. Close all Caissa windows and reopen the app to copy your library to '+result.pending+'. The current library stays active until then.';
      use.disabled=true;cancel.hidden=false;selection.textContent='';
    },'primary');use.disabled=true;
    const choose=button('Browse folders…',async()=>{
      if(!window.pywebview?.api?.choose_storage_folder)throw new Error('Open the desktop app (desktop.py or Caissa.exe) to use the native folder picker.');
      const selected=await window.pywebview.api.choose_storage_folder();
      selection.textContent=selected?'Selected: '+selected:'';use.disabled=!selected;
    });
    const reveal=button('Show in folder',async()=>{
      if(!window.pywebview?.api?.reveal_storage_folder)throw new Error('Open the desktop app (desktop.py or Caissa.exe) to open the folder from here.');
      const result=await window.pywebview.api.reveal_storage_folder();
      if(result.error)throw new Error(result.error);
    });reveal.disabled=!bridge?.reveal_storage_folder;
    const cancel=button('Cancel pending change',async()=>{await window.pywebview.api.cancel_storage_change();status.textContent='Storage change cancelled. Your current folder is unchanged.';cancel.hidden=true;selection.textContent='';use.disabled=true;});cancel.hidden=!info.pending;
    if(info.overridden){choose.disabled=true;use.disabled=true;status.textContent='DATA_DIR controls this launch. Remove that override to choose a folder here.';}
    content.append(h('div',{style:{marginBottom:'25px'}},[card('Storage location',h('div.card-pad',[field('Current storage folder',path),h('p.muted',{text:'Games, studies, repertoires, settings, trainer progress, and cached data stay together in this folder. Choose an empty folder; Caissa copies everything on the next launch and retains the original as a backup.'}),
      ...(!bridge?.storage_info?[h('p.muted',{text:'The native folder picker is available in the desktop app. Browser launches use the saved folder too.'})]:[]),
      h('div.toolbar',[reveal,choose,use,cancel]),selection,status]))]));
  }
  async function deleteMatching(reload){
    const data=await api('games/delete-preview',{filters:state.filters});
    if(!data.total){App.toast('No games match these filters.');return;}
    modal('Delete '+data.total.toLocaleString()+' matching games?',(body,close)=>{
      body.append(h('p',{text:'All active filters are combined. This removes the matching games from your library index; original PGN text stays on disk.'}),
        h('pre',{text:JSON.stringify(state.filters,null,2)}),
        ...data.sample.map(g=>h('p',{text:g.white+' — '+g.black+' · '+g.date})),
        h('div.dialog-actions',[button('Cancel',close),button('Delete '+data.total+' games',async()=>{const r=await api('games/delete-confirm',{token:data.token});close();App.toast(r.deleted+' games removed');state.offset=0;await reload();},'danger')]));
    });
  }
  async function importHistory(){
    if(state.view!=='imports')return;
    const data=await api('import/history');
    let panel=content.querySelector('.import-history');
    if(!panel){panel=h('section.card.card-pad.import-history');content.append(panel);}
    panel.replaceChildren(h('h2',{text:'Recent imports'}),h('p.muted',{text:'Undo removes only games added by that import, including partially completed imports. Duplicates already in your library are preserved.'}),
      ...data.batches.filter(b=>b.games||b.undone).map(b=>h('div.context-item',[h('span',{text:b.label+' · '+new Date(b.created_at*1000).toLocaleString()+' · '+b.games+' games'}),
        ...(b.games?[button('Undo import',async()=>{if(!confirm('Remove the '+b.games+' games added by this import?'))return;await api('import/undo',{batch_id:b.id});await importHistory();})]:[h('span',{text:' · Undone'})])])),button('Refresh import history',importHistory));
  }
  function resizeBoard(holder){
    const handle=h('button.board-resize',{type:'button',text:'◢',title:'Drag to resize board','aria-label':'Resize board'});
    holder.append(handle);holder.style.position='relative';
    const apply=width=>{const grid=holder.closest('.analysis-grid');const reserve=window.innerWidth>1400?550:window.innerWidth>950?300:0;const max=Math.max(260,Math.min(1000,grid.getBoundingClientRect().width-reserve));const size=Math.max(260,Math.min(max,width));grid.style.setProperty('--board-size',size+'px');};
    if(state.prefs.boardSize)apply(state.prefs.boardSize);
    handle.addEventListener('pointerdown',e=>{e.preventDefault();handle.setPointerCapture(e.pointerId);const x=e.clientX,width=holder.getBoundingClientRect().width;
      const move=e=>apply(width+e.clientX-x);
      const end=act(async()=>{handle.removeEventListener('pointermove',move);handle.removeEventListener('pointerup',end);handle.removeEventListener('pointercancel',end);state.prefs.boardSize=holder.getBoundingClientRect().width;await savePrefs();});
      handle.addEventListener('pointermove',move);handle.addEventListener('pointerup',end);handle.addEventListener('pointercancel',end);
    });
  }
  function boardEditor(){modal('Board editor',(body,close)=>{
    let map=new Chess(state.node.fenAfter).piecesMap();
    const holder=h('div.board-holder',{style:{width:'min(400px,100%)',margin:'auto'}}),b=new Board(holder,{viewOnly:true});
    const piece=select([['','Erase'],...['w','b'].flatMap(c=>['k','q','r','b','n','p'].map(t=>[c+t,(c==='w'?'White ':'Black ')+({k:'king',q:'queen',r:'rook',b:'bishop',n:'knight',p:'pawn'}[t])]))],'wk');
    const fenInput=h('input',{value:state.node.fenAfter}),turn=select([['w','White'],['b','Black']],state.node.fenAfter.split(' ')[1]),castling=h('input',{value:state.node.fenAfter.split(' ')[2]}),ep=h('input',{value:state.node.fenAfter.split(' ')[3]});
    function sync(){const ranks=[];for(let r=8;r>=1;r--){let row='',empty=0;for(const f of 'abcdefgh'){const p=map[f+r];if(!p){empty++;continue;}if(empty){row+=empty;empty=0;}row+=p.color==='w'?p.type.toUpperCase():p.type;}if(empty)row+=empty;ranks.push(row);}fenInput.value=ranks.join('/')+' '+turn.value+' '+(castling.value||'-')+' '+(ep.value||'-')+' 0 1';b.setPieces(map);}
    holder.addEventListener('click',e=>{const square=b._keyAt(e);if(!square)return;if(piece.value)map[square]={color:piece.value[0],type:piece.value[1]};else delete map[square];sync();});
    for(const control of [turn,castling,ep])control.addEventListener('change',sync);
    body.append(h('p',{text:'Choose a piece and click squares, or paste a FEN. Applying creates a new study.'}),field('Piece',piece),holder,field('Side to move',turn),field('Castling rights (KQkq or -)',castling),field('En passant square (or -)',ep),field('FEN',fenInput),
      h('div.toolbar',[button('Clear board',()=>{map={};castling.value='-';ep.value='-';sync();}),button('Starting position',()=>{map=new Chess().piecesMap();turn.value='w';castling.value='KQkq';ep.value='-';sync();})]),
      h('div.dialog-actions',[button('Cancel',close),button('Apply position',()=>{
        const fen=fenInput.value.trim(),parts=fen.split(/\s+/),ranks=(parts[0]||'').split('/');
        if(parts.length!==6||ranks.length!==8||ranks.some(r=>!/^[prnbqkPRNBQK1-8]+$/.test(r)||[...r].reduce((n,c)=>n+(Number(c)||1),0)!==8)||!/^[wb]$/.test(parts[1])||!/^(-|K?Q?k?q?)$/.test(parts[2])||!/^(-|[a-h][36])$/.test(parts[3])||!/^\d+$/.test(parts[4])||! /^[1-9]\d*$/.test(parts[5]))throw new Error('Enter a valid six-field FEN.');
        if((parts[0].match(/K/g)||[]).length!==1||(parts[0].match(/k/g)||[]).length!==1||/[pP]/.test(ranks[0]+ranks[7]))throw new Error('Place one king of each color and no pawns on the first or eighth rank.');
        const g=new Chess(fen),pieces=g.piecesMap(),wk=Object.keys(pieces).find(k=>pieces[k].color==='w'&&pieces[k].type==='k'),bk=Object.keys(pieces).find(k=>pieces[k].color==='b'&&pieces[k].type==='k');
        if(Math.abs(wk.charCodeAt(0)-bk.charCodeAt(0))<=1&&Math.abs(Number(wk[1])-Number(bk[1]))<=1)throw new Error('Kings cannot be adjacent.');
        if(state.dirty&&!confirm('Discard unsaved analysis and use this position?'))return;
        state.selected=null;state.parsed=PGN.parse('[Event "Edited position"]\n[White "White"]\n[Black "Black"]\n[SetUp "1"]\n[FEN "'+g.fen()+'"]\n[Result "*"]\n\n*');state.node=state.parsed.root;state.dirty=true;close();go('analysis');
      },'primary')]));b.setPieces(map);
  });}
  function filterDialog(reload){modal('Find the games that matter',(body,close)=>{
    const f=state.filters,inputs={};
    function text(key,label,extra){const el=h('input',Object.assign({value:f[key]||''},extra||{}));inputs[key]=el;return field(label,el);}
    const player=h('input',{value:f.player||f.white||f.black||'',placeholder:'Fischer'});
    const colour=colourSelect(f.white?'white':f.black?'black':'');
    const outcome=outcomeSelect(f.outcome);
    const result=select([['','Any result'],'1-0','0-1','1/2-1/2','*'],f.result||'');
    const eco=h('input',{value:f.eco||'',placeholder:'E60','aria-label':'ECO from'}),ecoEnd=h('input',{value:f.eco_to||'',placeholder:'E99','aria-label':'ECO through'});
    const picker=openingPicker(hit=>{if(hit.eco_from){eco.value=hit.eco_from;ecoEnd.value=hit.eco_to||hit.eco_from;}},f.opening);
    body.append(h('p.muted',{text:'Every field narrows the same search. Colour and outcome are read from the player you name, and choosing an opening fills in the ECO range it covers in your library.'}),
      field('Player',player),h('div.toolbar',[field('Colour',colour),field('Outcome',outcome),field('Result',result)]),
      field('Opening',picker.input),picker.list,
      h('div.toolbar',[field('ECO from',eco),field('ECO through',ecoEnd)]),
      h('div.toolbar',[text('min_elo','Minimum rating',{type:'number',min:0}),text('max_elo','Maximum rating',{type:'number',min:0})]),
      text('event','Event'),text('year','Year'),
      h('div.toolbar',[text('min_length','Minimum plies',{type:'number',min:0}),text('max_length','Maximum plies',{type:'number',min:0})]),
      text('tag','Tag'),
      h('div.toolbar',[text('added_from','Added on or after',{type:'date'}),text('added_to','Added on or before',{type:'date'})]),
      text('position','Position FEN (indexed positions)'),
      h('div.dialog-actions',[
        button('Clear all fields',()=>{state.filters={};state.offset=0;close();go('database');}),
        button('Cancel',close),
        button('Apply',()=>{
          const next={};
          for(const [key,el] of Object.entries(inputs))if(String(el.value).trim())next[key]=String(el.value).trim();
          if(player.value.trim())next[colour.value||'player']=player.value.trim();
          if(picker.input.value.trim())next.opening=picker.input.value.trim();
          if(eco.value.trim())next.eco=eco.value.trim().toUpperCase();
          if(ecoEnd.value.trim())next.eco_to=ecoEnd.value.trim().toUpperCase();
          if(result.value)next.result=result.value;
          if(outcome.value)next.outcome=outcome.value;
          for(const keep of ['collection','q','sort'])if(f[keep])next[keep]=f[keep];
          state.filters=next;state.offset=0;close();return reload();},'primary')]));
  });}
  async function mentorSearch(){
    const player=h('input',{placeholder:'Fischer',value:'Fischer'});
    const eco=h('input',{value:'E60',placeholder:'E60','aria-label':'ECO from'}),ecoEnd=h('input',{value:'E99',placeholder:'E99','aria-label':'ECO through'});
    const picker=openingPicker(hit=>{if(hit.eco_from){eco.value=hit.eco_from;ecoEnd.value=hit.eco_to||hit.eco_from;}},'King’s Indian');
    const colour=colourSelect(''),outcome=outcomeSelect(''),results=h('div');
    function filtersFor(collection){
      const next={collection};
      if(player.value.trim())next[colour.value||'player']=player.value.trim();
      if(outcome.value)next.outcome=outcome.value;
      if(eco.value.trim())next.eco=eco.value.trim().toUpperCase();
      if(ecoEnd.value.trim())next.eco_to=ecoEnd.value.trim().toUpperCase();
      if(!eco.value.trim()&&picker.input.value.trim())next.opening=picker.input.value.trim();
      return next;
    }
    content.append(card('Search PGN Mentor player collections',h('div.card-pad',[
      field('Player surname',player),
      h('div.toolbar',[field('Colour',colour),field('Outcome',outcome)]),
      field('Opening name',picker.input),picker.list,
      h('div.toolbar',[field('ECO from',eco),field('ECO through',ecoEnd)]),
      h('div.toolbar',[
        button('Find collections',async()=>{
          results.textContent='Searching PGN Mentor…';
          const data=await api('masters/catalog?'+new URLSearchParams({q:player.value}));
          results.replaceChildren(...data.players.map(p=>h('div.context-item',[h('b',{text:p.name}),
            button('Import & find matching games',async()=>{
              const collection='Masters / '+p.name;
              watchImport();
              await api('import/source',{path:p.url,collection});
              state.filters=filtersFor(collection);state.offset=0;await go('database');
            })])));
          if(!data.players.length)results.textContent='No player collections found. Try a surname.';
        },'primary'),
        button('Clear all fields',()=>{player.value='';picker.input.value='';eco.value='';ecoEnd.value='';colour.value='';outcome.value='';results.replaceChildren();})]),
      h('p.muted',{text:'Downloads the selected collection, then combines your filters locally. Picking an opening fills the ECO range from the games you already have, which finds the same openings in PGNs that carry no opening name.'}),
      results])));
    const lookup=h('input',{placeholder:'Kasparov Topalov, Wijk aan Zee, Najdorf…','aria-label':'Find a game in your library'});
    const found=h('div');
    content.append(card('Find a game you already have',h('div.card-pad',[
      field('Player, event or opening',lookup),
      button('Search my library',async()=>{
        const term=lookup.value.trim();
        if(!term)throw new Error('Type a player, event or opening to look for.');
        found.textContent='Searching your library…';
        const data=await api('games?'+new URLSearchParams({q:term,limit:12,offset:0}));
        if(!data.total){found.textContent='Nothing in your library matches that yet. Import the collection first.';return;}
        found.replaceChildren(h('p.muted',{text:data.total.toLocaleString()+' matching games · opening one puts it on a new analysis tab'}),
          ...data.games.map(g=>h('div.context-item',[button(g.white+' — '+g.black,()=>openGame(g.id)),
            h('div.muted',{text:[g.event,g.date,g.result].filter(Boolean).join(' · ')})])),
          data.total>12?button('See all '+data.total.toLocaleString()+' in the database',()=>{state.filters={q:term};state.offset=0;return go('database');}):null);
      },'primary'),found])));
  }
  function applyPrefs() {
    Board.setPieceSet(state.prefs.pieceSet||'cburnett');
    for(const b of [board,preview,App.board])if(b)b.refreshPieceArt();
    document.body.classList.toggle('dark-theme',state.prefs.darkMode===true);
    document.body.classList.toggle('color-lines',state.prefs.colorLines===true);
    const p=state.prefs, colors=themes[p.theme]||themes.Sage;
    document.documentElement.style.setProperty('--light-sq',p.light||colors[0]);
    document.documentElement.style.setProperty('--dark-sq',p.dark||colors[1]);
    ['wood','slate','outline'].forEach(v=>document.body.classList.toggle('piece-'+v,p.pieces===v));
    document.body.classList.toggle('theme-coordinates-off',p.coordinates===false);
    document.documentElement.style.setProperty('--anim',p.animate===false?'0ms':'200ms');
    for(const b of [board,preview,App.board])if(b){b.setOrientation(p.orientation||'w');b.opts.animationMs=p.animate===false?0:200;b.container.querySelector('.cg-wrap').style.setProperty('--anim',b.opts.animationMs+'ms');}
  }
  async function savePrefs() {applyPrefs();await api('settings/appearance',{value:JSON.stringify(state.prefs)},'PUT');}
  function serialize(parsed) {
    // Harvested commands ride back into the same comment they were lifted from.
    function comment(n){const body=[...(n.commands||[]),n.comment||''].join(' ').trim();
      return (n.nags.length?' '+n.nags.join(' '):'')+(body?' {'+body.replace(/[{}]/g,'')+'}':'');}
    function token(n){const fen=n.parent.fenAfter.split(' ');return fen[5]+(fen[1]==='w'?'. ':'... ')+n.san+comment(n);}
    function branch(parent){if(!parent.children.length)return '';const first=parent.children[0];return token(first)+' '+parent.children.slice(1).map(n=>'('+token(n)+' '+branch(n)+')').join(' ')+' '+branch(first);}
    const esc=s=>String(s).replace(/\\/g,'\\\\').replace(/"/g,'\\"');
    return Object.entries(parsed.headers).map(([k,v])=>'['+k+' "'+esc(v)+'"]').join('\n')+'\n\n'+comment(parsed.root)+' '+branch(parsed.root)+' '+(parsed.headers.Result||'*')+'\n';
  }
  function newGame() {state.selected=null;state.parsed=PGN.parse('[Event "Study"]\n[White "White"]\n[Black "Black"]\n[Result "*"]\n\n*');state.node=state.parsed.root;state.dirty=false;activeBoard();}
  async function openGame(id) {
    const {game}=await api('games/'+id);const parsed=PGN.parse(game.pgn);
    if(parsed.errors.length)throw new Error('This PGN contains unrecognized moves: '+parsed.errors.slice(0,5).join(', '));
    // A tab already holding work of its own steps aside; an untouched one is reused.
    const current=activeBoard();stashBoard();
    if(current.selected||current.dirty||current.parsed?.root.children.length)state.boards.splice(++state.boardIndex,0,makeBoard());
    state.selected=game;state.parsed=parsed;state.node=parsed.root;state.dirty=false;stashBoard();
    await go('analysis');
  }
  /* ---------- analysis boards ---------- */
  // Every analysis tab owns its game and its own panel arrangement. Only one arrangement
  // is remembered for new tabs: the board closed last, or board one when the app exits
  // with several open.
  const PANELS=[['notation','Notation'],['engine','Stockfish · local analysis'],['tags','Game tags'],
    ['context','Position context'],['tablebase','Endgame tablebase']];
  const DEFAULT_LAYOUT={main:['notation','engine','tags'],side:['context','tablebase']};
  let boardSeq=0;
  function normalizeLayout(saved){
    const source=saved&&typeof saved==='object'?saved:DEFAULT_LAYOUT;
    const layout={main:[],side:[],hidden:[],heights:{...(source.heights||{})},cols:{...(source.cols||{})}},placed=new Set();
    for(const dock of ['main','side'])for(const id of Array.isArray(source[dock])?source[dock]:[])
      if(PANELS.some(p=>p[0]===id)&&!placed.has(id)){placed.add(id);layout[dock].push(id);}
    // A panel a later version adds joins the dock it was designed for rather than vanishing.
    for(const [id] of PANELS)if(!placed.has(id))layout[DEFAULT_LAYOUT.main.includes(id)?'main':'side'].push(id);
    layout.hidden=(Array.isArray(source.hidden)?source.hidden:[]).filter(id=>PANELS.some(p=>p[0]===id));
    return layout;
  }
  function makeBoard(){return {id:++boardSeq,parsed:null,node:null,selected:null,dirty:false,layout:normalizeLayout(state.prefs.analysisLayout)};}
  function activeBoard(){if(!state.boards.length){state.boards.push(makeBoard());state.boardIndex=0;}
    state.boardIndex=Math.max(0,Math.min(state.boardIndex,state.boards.length-1));return state.boards[state.boardIndex];}
  function stashBoard(){const b=activeBoard();b.parsed=state.parsed;b.node=state.node;b.selected=state.selected;b.dirty=state.dirty;}
  function adoptBoard(index){state.boardIndex=index;const b=activeBoard();
    state.selected=b.selected;state.dirty=b.dirty;
    if(b.parsed){state.parsed=b.parsed;state.node=b.node||b.parsed.root;}else newGame();}
  function boardTitle(b){const white=b.parsed?.headers?.White,black=b.parsed?.headers?.Black;
    return white&&white!=='White'?white+' — '+black:'New study';}
  async function closeBoard(index){
    if(index===state.boardIndex)stashBoard();
    const b=state.boards[index];
    if(b.dirty&&!confirm('Discard unsaved changes to '+boardTitle(b)+'?'))return;
    state.prefs.analysisLayout=b.layout;                 // the board closed last is the one remembered
    state.boards.splice(index,1);
    if(!state.boards.length)state.boards.push(makeBoard());
    adoptBoard(index<state.boardIndex?state.boardIndex-1:Math.min(state.boardIndex,state.boards.length-1));
    await savePrefs();
    await go('analysis');
  }
  function boardTabs(){
    const strip=h('div.board-tabs',{role:'tablist','aria-label':'Analysis boards'});
    state.boards.forEach((b,index)=>{
      const title=boardTitle(b);
      const tab=h('div.board-tab'+(index===state.boardIndex?'.active':''),[
        h('button.tab-label',{type:'button',role:'tab','aria-selected':String(index===state.boardIndex),text:title+(b.dirty?' *':''),
          onclick:act(async()=>{if(index===state.boardIndex)return;stashBoard();adoptBoard(index);await go('analysis');})})]);
      if(state.boards.length>1)tab.append(h('button.tab-close',{type:'button',text:'✕',title:'Close this board','aria-label':'Close '+title,onclick:act(()=>closeBoard(index))}));
      strip.append(tab);
    });
    strip.append(h('button.tab-new',{type:'button',text:'＋',title:'Open another analysis board','aria-label':'New analysis board',onclick:act(newBoard)}));
    return strip;
  }
  function newBoard(){stashBoard();state.boards.splice(++state.boardIndex,0,makeBoard());adoptBoard(state.boardIndex);return go('analysis');}
  async function go(view) {
    if(state.analysisCleanup){state.analysisCleanup();state.analysisCleanup=null;}
    clearInterval(poll);clearTimeout(liveTimer);const ticket=++state.route;state.view=view;
    document.body.classList.toggle('training',view==='training');document.getElementById('trainer').hidden=view!=='training';
    nav.querySelectorAll('button').forEach(b=>b.classList.toggle('active',b.dataset.view===view));
    crumb.textContent=(modules.find(m=>m[0]===view)||modules[0])[2];
    if(view==='training'){App.go(App.current?App.current.id:App.levels[0].id);return;}
    if(App.cleanup){App.cleanup();App.cleanup=null;App.peek.end();}
    location.hash='workspace/'+view;content.replaceChildren(h('p.muted',{text:'Opening your workspace…'}));
    try {await refreshMeta();if(ticket!==state.route)return;content.replaceChildren();
      await ({database:database,analysis:analysis,repertoire:repertoires,masters:masters,imports:imports,studies:studies,tactics:tactics,settings:settings}[view]||database)();
    }catch(err){if(ticket===state.route)content.replaceChildren(h('div.view-error',[h('h2',{text:'Could not open this view'}),h('p.error-message',{text:err.message}),button('Try again',()=>go(view))]));}
  }
  async function database() {
    content.append(heading('Your chess, collected','Game database','A home for every game and every idea worth keeping.',[
      button('New study',()=>{if(state.dirty&&!confirm('Discard unsaved analysis?'))return;newGame();go('analysis');}),button('＋ Import games',()=>go('imports'),'primary')]));
    const statGrid=h('div.stat-grid');content.append(statGrid);
    // The tiles are counts of the whole library, not of the current filter, so they have
    // to be re-read whenever the library itself changes rather than on every table load.
    let stats={games:0};
    async function refreshStats(){const [fresh,reps]=await Promise.all([api('stats'),api('repertoires')]);stats=fresh;
      statGrid.replaceChildren(...[[fresh.games,'Games in your library','Searchable, portable PGN'],[fresh.collections.length,'Collections','Organized your way'],[reps.repertoires.length,'Repertoires','Your opening preparation'],[state.folders.length,'Study folders','A place for your next idea']]
        .map(([n,t,sub])=>h('div.card.metric',[h('small',{text:t}),h('strong',{text:Number(n).toLocaleString()}),h('span',{text:sub})])));}
    await refreshStats();
    const q=h('input',{placeholder:'Search players, openings, events…',value:state.filters.q||'',type:'search','aria-label':'Search games'});
    let timer;q.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(()=>{state.filters.q=q.value;state.offset=0;loadGames();},250);});
    const cols=select([['','All collections'],...state.collections.map(c=>[String(c.id),c.name])],state.filters.collection||'',()=>{state.filters.collection=cols.value;state.offset=0;loadGames();});
    const sort=select([['added','Recently added'],['date','Newest played'],['date_asc','Oldest played'],['elo','Highest rated'],['white','White player'],['length','Longest games']],state.filters.sort||'date',()=>{state.filters.sort=sort.value;loadGames();});
    const rows=h('tbody'),count=h('span'),pager=h('div.pagination');
    const filters=h('div.filters',[q,cols,sort,button('Filters',()=>filterDialog(loadGames)),button('Delete matching games',()=>deleteMatching(async()=>{await refreshStats();await loadGames();}),'danger')]);
    const table=h('div.table-scroll',[h('table.games',[h('thead',[h('tr',['Players','Result','Opening','Date'].map(t=>h('th',{text:t})))]),rows])]);
    const list=h('section.card',[filters,table,pager]);
    const aside=h('div.library-aside.section-stack');
    const previewBody=h('div.preview',[h('div.eyebrow',{text:'At the board'}),h('h3',{text:'Your next discovery'}),h('p.muted',{text:'Select a game to preview. Double-click to analyze.'})]);
    const holder=h('div.board-holder');previewBody.append(holder);preview=new Board(holder,{viewOnly:true,animationMs:0});preview.setPosition(new Chess());applyPrefs();
    const previewDetails=h('div');previewBody.append(previewDetails);aside.append(h('section.card',[previewBody]),h('section.note-card',[h('div.eyebrow',{text:'A connected workspace'}),h('h3',{text:'Follow the position.'}),h('p',{text:'Analyze a game, keep the critical line in your repertoire, and rehearse it without seeing the pieces.'}),button('Organize your studies',()=>go('studies'))]));
    content.append(h('div.library-grid',[list,aside]));let request=0;
    async function loadGames(){const id=++request;const params=new URLSearchParams({...state.filters,limit:30,offset:state.offset});const data=await api('games?'+params);if(id!==request||state.view!=='database')return;rows.replaceChildren();
      data.games.forEach(g=>{const opening=openingLabel(g);const row=h('tr',{tabindex:0,ondblclick:act(()=>openGame(g.id)),onkeydown:act(e=>{if(e.key==='Enter')return openGame(g.id);}),onclick:()=>{rows.querySelectorAll('tr').forEach(r=>r.classList.remove('selected'));row.classList.add('selected');showPreview(g);}},[
        h('td',[h('div.player-name',{text:g.white+' — '+g.black}),h('div.subline',{text:[g.white_elo&&g.black_elo?g.white_elo+' · '+g.black_elo:'',g.event].filter(Boolean).join('  /  ')})]),
        h('td',[h('span.result-pill',{text:g.result})]),h('td',[h('div',[opening.eco?h('span.eco-code',{text:opening.eco}):null,opening.name]),h('div.subline',{text:Math.ceil(g.ply_count/2)+' moves'})]),h('td',{text:g.date||'Unknown'})]);rows.append(row);});
      if(!data.games.length)rows.append(h('tr',[h('td',{colspan:4},[empty('Make room for your chess',stats.games?'No games match these filters.':'Import a PGN or bring in your online games to start your library.',[button('Import games',()=>go('imports'),'primary')])])]));
      count.textContent=data.total?`${state.offset+1}–${Math.min(state.offset+30,data.total)} of ${data.total.toLocaleString()} games`:'0 games';
      const prev=button('← Previous',()=>{state.offset=Math.max(0,state.offset-30);return loadGames();});prev.disabled=state.offset===0;
      const next=button('Next →',()=>{state.offset+=30;return loadGames();});next.disabled=state.offset+30>=data.total;
      pager.replaceChildren(count,h('div.toolbar',[prev,next]));
    }
    let previewRequest=0;
    async function showPreview(g){const id=++previewRequest;try{const {game}=await api('games/'+g.id);if(id!==previewRequest)return;const parsed=PGN.parse(game.pgn);const line=PGN.mainline(parsed.root);preview.setPosition(line[line.length-1]?.fenAfter||parsed.startFen);previewDetails.replaceChildren(h('h3',{text:g.white+' — '+g.black}),h('p.muted',{text:g.event+' · '+g.date}),button('Open analysis →',()=>openGame(g.id),'primary'));}catch(err){App.toast(err.message);}}
    await loadGames();
  }
  async function analysis() {
    if(!state.parsed)newGame();
    stashBoard();
    const parsed=state.parsed, layout=activeBoard().layout;
    harvestCommands(parsed);
    const saveBtn=button(state.dirty?'Save changes *':'Save game',saveGame,'primary');
    content.append(heading('Understand every move',parsed.headers.White+' — '+parsed.headers.Black,[parsed.headers.Event,parsed.headers.Date].filter(Boolean).join(' · ')||'An open board for your ideas',[
      button('Panels',panelDialog),button('Reset board',()=>{if(state.dirty&&!confirm('Discard unsaved analysis and reset to the starting position?'))return;newGame();go('analysis');}),button('Board editor',boardEditor),button('Export PGN',()=>download(serialize(parsed),'caissa-study.pgn')),button('Add to repertoire',addToRepertoire),saveBtn]));
    content.append(boardTabs());
    const holder=h('div.board-holder'),moves=h('div.move-tree'),engineBody=h('div',[h('p.muted',{style:{padding:'16px'},text:'Analyze a position with your bundled Stockfish.'})]),contextBody=h('div.context-body');
    // Annotations belong to the game the moment they are typed; there is nothing to press.
    let commentTimer;
    const comment=h('textarea',{rows:3,placeholder:'What is the idea in this position?','aria-label':'Position comment',
      oninput:()=>{const target=state.node;clearTimeout(commentTimer);commentTimer=setTimeout(()=>{const text=comment.value.trim();
        if((target.comment||'')===text)return;target.comment=text||null;markDirty();renderMoves();},250);}});
    const nag=select([['','No annotation'],['$1','! Good move'],['$2','? Mistake'],['$3','!! Brilliant'],['$4','?? Blunder'],['$5','!? Interesting'],['$6','?! Inaccuracy']],'',
      ()=>{state.node.nags=nag.value?[nag.value]:[];markDirty();renderMoves();});
    let live=false,evalRequest=0,contextRequest=0,liveId=null,livePoll=null,closed=false,latestLines=[],tbRequest=0;
    const resources=h('p.muted',{text:'CPU and memory appear during live analysis.'});
    const arrows=h('input',{type:'checkbox',checked:state.prefs.bestArrows!==false,onchange:act(async()=>{state.prefs.bestArrows=arrows.checked;drawBest();await savePrefs();})});
    const colorLines=h('input',{type:'checkbox',checked:!!state.prefs.colorLines,onchange:act(async()=>{state.prefs.colorLines=colorLines.checked;await savePrefs();})});
    const liveBox=h('input',{type:'checkbox',onchange:()=>{live=liveBox.checked;if(live)evaluate();else {clearTimeout(liveTimer);clearTimeout(livePoll);++evalRequest;liveId=null;api('engine/live',null,'DELETE').catch(()=>{});}}});
    const pv=select(['1','2','3','5'],'3');
    const rowsBox=h('input',{type:'checkbox',checked:state.prefs.moveRows!==false,onchange:act(async()=>{state.prefs.moveRows=rowsBox.checked;renderMoves();await savePrefs();})});
    const contextTabs=h('div.context-tabs');['Library','Study','History'].forEach(t=>contextTabs.append(h('button',{text:t,onclick:()=>{state.context=t;renderContext();}})));
    const controls=h('div.board-navigation',[button('⏮',()=>jump(parsed.root)),button('←',()=>jump(state.node.parent||state.node)),button('→',()=>jump(state.node.children[0]||state.node)),button('⏭',()=>{let n=state.node;while(n.children.length)n=n.children[0];jump(n);}),button('Flip',()=>board.toggleOrientation())]);
    controls.querySelectorAll('button').forEach((b,i)=>b.setAttribute('aria-label',['First position','Previous move','Next move','Last move','Flip board'][i]));
    const fen=h('div.fen');const sanInput=h('input',{placeholder:'Enter a move, e.g. Nf3','aria-label':'Move in SAN'});
    const moveForm=h('form.toolbar',{onsubmit:act(e=>{e.preventDefault();play(sanInput.value);sanInput.value='';})},[sanInput,h('button.btn',{text:'Play move',type:'submit'})]);
    const tablebaseBody=h('div.card-pad');const tablebaseToggle=h('input',{type:'checkbox',onchange:()=>renderTablebase()});

    /* ---------- dockable panels ---------- */
    const built={};
    function panel(id,title,body,actions){
      const head=h('div.card-head',[h('h2',{text:title}),h('div.toolbar.panel-actions',actions||[])]);
      const box=h('div.panel-body',[body]);
      const handle=h('button.panel-grip',{type:'button',title:'Drag to set the height','aria-label':'Resize '+title});
      built[id]={id,title,head,box,handle,node:h('section.card.panel',{'data-panel':id},[head,box,handle])};
    }
    panel('notation','Notation',h('div',[moves,h('div.editor',[field('Position comment',comment),nag,h('div.toolbar',[
      button('Remove branch',()=>{const n=state.node;if(!n.parent)return;if(!confirm('Remove this move and everything following it in this branch?'))return;n.parent.children=n.parent.children.filter(c=>c!==n);state.node=n.parent;markDirty();render();})])])]),[h('label.toolbar',[rowsBox,'One move per line'])]);
    panel('engine','Stockfish · local analysis',h('div',[h('div.filters',[h('label.toolbar',[liveBox,'Live analysis']),field('Lines',pv),button('Analyze',evaluate),h('label.toolbar',[arrows,'Best move arrows']),h('label.toolbar',[colorLines,'Color variations'])]),resources,engineBody]),[button('Annotate game',annotate)]);
    panel('tags','Game tags',h('div.card-pad',[button('Edit tags',editTags),button('Delete game',deleteGame,'danger')]));
    panel('context','Position context',h('div',[contextTabs,contextBody]));
    panel('tablebase','Endgame tablebase',h('div',[h('label.toolbar.card-pad',[tablebaseToggle,'Show exact endgame results (online)']),tablebaseBody]));
    const tablebaseCard=built.tablebase.node;
    const dockMain=h('div.dock.dock-main'),dockSide=h('div.dock.dock-side');
    const splitter=h('div.dock-splitter',{title:'Drag to divide the two columns'});
    const grid=h('div.analysis-grid',[h('div.analysis-board',[
      h('div.player-strip',[h('b',{text:parsed.headers.Black||'Black'}),h('span.muted',{text:parsed.headers.BlackElo||''})]),holder,
      h('div.player-strip',[h('b',{text:parsed.headers.White||'White'}),h('span.muted',{text:parsed.headers.WhiteElo||''})]),controls,moveForm,h('div.toolbar',[button('Copy FEN',async()=>{await navigator.clipboard.writeText(state.node.fenAfter);App.toast('FEN copied');}),button('Clear arrows',()=>board.setShapes([]))]),h('p.muted',{text:'Wheel: moves · Right-drag or Shift-drag: arrow · Shift or Ctrl: red · Alt: blue · both: yellow · Click the board to clear'}),fen]),
      dockMain,splitter,dockSide]);
    content.append(grid);
    function panelControls(id){
      const where=layout.main.includes(id)?'main':'side',list=layout[where],at=list.indexOf(id),title=built[id].title;
      const step=delta=>{const to=at+delta;if(to<0||to>=list.length)return;list.splice(at,1);list.splice(to,0,id);applyLayout();};
      return h('div.toolbar.panel-controls',[
        h('button.panel-btn',{type:'button',text:'▲',title:'Move up','aria-label':'Move '+title+' up',onclick:()=>step(-1)}),
        h('button.panel-btn',{type:'button',text:'▼',title:'Move down','aria-label':'Move '+title+' down',onclick:()=>step(1)}),
        h('button.panel-btn',{type:'button',text:where==='main'?'▶':'◀',title:where==='main'?'Send to the right column':'Send to the left column','aria-label':'Move '+title+' to the other column',
          onclick:()=>{list.splice(at,1);layout[where==='main'?'side':'main'].push(id);applyLayout();}}),
        h('button.panel-btn',{type:'button',text:'✕',title:'Hide this panel','aria-label':'Hide '+title,
          onclick:()=>{if(!layout.hidden.includes(id))layout.hidden.push(id);applyLayout();}})]);
    }
    function applyLayout(){
      for(const where of ['main','side']){
        const dock=where==='main'?dockMain:dockSide;
        dock.replaceChildren(...layout[where].filter(id=>!layout.hidden.includes(id)).map(id=>built[id].node));
      }
      for(const [id] of PANELS){
        const spot=built[id];
        spot.box.style.height=layout.heights[id]?layout.heights[id]+'px':'';
        const stale=spot.head.querySelector('.panel-controls');if(stale)stale.remove();
        if(!layout.hidden.includes(id))spot.head.append(panelControls(id));
      }
      // An emptied column collapses rather than leaving a gap the board cannot use.
      grid.style.setProperty('--dock-main',dockMain.children.length?(layout.cols.main||0.85)+'fr':'0fr');
      grid.style.setProperty('--dock-side',dockSide.children.length?(layout.cols.side||0.65)+'fr':'0fr');
      splitter.hidden=!(dockMain.children.length&&dockSide.children.length);
    }
    function panelDialog(){modal('Analysis panels',(body,close)=>{
      body.append(h('p.muted',{text:'Choose what this board shows. The arrows in each panel head reorder it or send it across to the other column, and the grip along its bottom edge sets its height. Every tab keeps its own arrangement; the tab you close last is the one remembered for new boards.'}));
      for(const [id,title] of PANELS){
        const box=h('input',{type:'checkbox',checked:!layout.hidden.includes(id),onchange:()=>{
          if(box.checked)layout.hidden=layout.hidden.filter(x=>x!==id);
          else if(!layout.hidden.includes(id))layout.hidden.push(id);
          applyLayout();}});
        body.append(field(title,box));
      }
      body.append(h('div.dialog-actions',[button('Reset arrangement',()=>{Object.assign(layout,normalizeLayout(null));applyLayout();close();}),button('Done',close,'primary')]));
    });}
    function bindGrip(id){
      const spot=built[id];
      spot.handle.addEventListener('pointerdown',event=>{event.preventDefault();spot.handle.setPointerCapture(event.pointerId);
        const startY=event.clientY,startHeight=spot.box.getBoundingClientRect().height;
        const move=ev=>{const next=Math.max(90,Math.round(startHeight+ev.clientY-startY));layout.heights[id]=next;spot.box.style.height=next+'px';};
        const end=()=>{spot.handle.removeEventListener('pointermove',move);spot.handle.removeEventListener('pointerup',end);spot.handle.removeEventListener('pointercancel',end);};
        spot.handle.addEventListener('pointermove',move);spot.handle.addEventListener('pointerup',end);spot.handle.addEventListener('pointercancel',end);});
    }
    for(const [id] of PANELS)bindGrip(id);
    splitter.addEventListener('pointerdown',event=>{event.preventDefault();splitter.setPointerCapture(event.pointerId);
      const startX=event.clientX,mainWidth=dockMain.getBoundingClientRect().width,total=mainWidth+dockSide.getBoundingClientRect().width;
      const move=ev=>{const next=Math.max(150,Math.min(total-150,mainWidth+ev.clientX-startX));
        layout.cols.main=Number((next/total*1.5).toFixed(3));layout.cols.side=Number(((total-next)/total*1.5).toFixed(3));
        grid.style.setProperty('--dock-main',layout.cols.main+'fr');grid.style.setProperty('--dock-side',layout.cols.side+'fr');};
      const end=()=>{splitter.removeEventListener('pointermove',move);splitter.removeEventListener('pointerup',end);splitter.removeEventListener('pointercancel',end);};
      splitter.addEventListener('pointermove',move);splitter.addEventListener('pointerup',end);splitter.addEventListener('pointercancel',end);});
    applyLayout();
    board=new Board(holder,{viewOnly:false});applyPrefs();resizeBoard(holder);
    let wheelAt=0;holder.addEventListener('wheel',e=>{e.preventDefault();if(!e.deltaY||Date.now()-wheelAt<100)return;wheelAt=Date.now();jump(e.deltaY>0?(state.node.children[0]||state.node):(state.node.parent||state.node));},{passive:false});
    pv.addEventListener('change',()=>{if(live)evaluate();});
    function markDirty(){state.dirty=true;activeBoard().dirty=true;saveBtn.textContent='Save changes *';}
    const PV_PLIES=20;                       // ten moves of it, or the whole line if shorter
    function addEngineLine(fromFen,sans){
      const start=allNodes(parsed.root).find(n=>n.fenAfter===fromFen);
      if(!start)throw new Error('That position has left the board; analyze again to add this line.');
      const game=new Chess(fromFen);
      let node=start,first=null,added=0;
      for(const san of sans.slice(0,PV_PLIES)){
        const moved=game.move(san);
        if(!moved)break;
        let child=node.children.find(c=>c.san===moved.san);
        if(!child){child={san:moved.san,move:moved,parent:node,children:[],fenAfter:game.fen(),comment:null,nags:[],ply:node.ply+1};node.children.push(child);added++;}
        node=child;
        if(!first)first=child;
      }
      if(!first)throw new Error('This line has no moves to add.');
      if(added)markDirty();
      App.toast(added?added+' moves added as a variation':'That line was already on the board');
      jump(first);                           // land on its first move so the arrows walk it
    }
    function jump(n){if(n===state.node)return;state.node=n;board.setShapes([]);render();}
    function play(input){const g=new Chess(state.node.fenAfter);const moved=g.move(input);if(!moved)throw new Error('That move is not legal in this position.');let n=state.node.children.find(c=>c.san===moved.san);if(!n){n={san:moved.san,move:moved,parent:state.node,children:[],fenAfter:g.fen(),comment:null,nags:[],ply:state.node.ply+1};state.node.children.push(n);markDirty();}jump(n);}
    // Two notations over the same tree: a running paragraph, or one row per move
    // number with the variations broken out between the rows. ctx carries the row
    // a line is currently filling; clearing it starts the next move on a fresh row.
    function renderMoves(){const rows=state.prefs.moveRows!==false;moves.replaceChildren();moves.classList.toggle('by-move',rows);
      function nags(n){return n.nags.map(v=>NAG_SYMBOLS[v]||v).join('');}
      function place(n,target,ctx){const f=n.parent.fenAfter.split(' '),number=f[5],white=f[1]==='w';let into=target;
        if(rows){if(white||!ctx.row||ctx.number!==number){ctx.row=h('div.move-row',[h('span.move-no',{text:number+'.'})]);ctx.number=number;target.append(ctx.row);if(!white)ctx.row.append(h('span.move-skip',{text:'…'}));}into=ctx.row;}
        const move=h('button'+(n===state.node?'.current':''),{text:(rows?'':number+(white?'. ':'… '))+n.san+' '+nags(n),onclick:()=>jump(n)});
        const score=n.eval,label=evalLabel(score);
        const side=!label?'':(score.mate!=null?(score.mate<0?'.black-better':'.white-better'):score.cp>0?'.white-better':score.cp<0?'.black-better':'');
        const chip=label?h('small.move-eval'+side,{text:label,title:'Engine evaluation stored in the PGN'}):null;
        if(rows)into.append(h('span.move-cell',[move,chip]));
        else {into.append(move);if(chip)into.append(chip);}
        if(n.comment){if(rows){target.append(h('div.move-note',{text:n.comment}));ctx.row=null;}else target.append(h('span.move-comment',{text:n.comment}));}}
      function walk(parent,target,ctx){if(!parent.children.length)return;const n=parent.children[0];place(n,target,ctx);
        for(const alt of parent.children.slice(1)){const sub=h('div.variation'),branch={row:null,number:null};place(alt,sub,branch);walk(alt,sub,branch);target.append(sub);ctx.row=null;}
        walk(n,target,ctx);}
      walk(parsed.root,moves,{row:null,number:null});
      if(!parsed.root.children.length)moves.append(h('p.muted',{text:'Move a piece or enter SAN to begin. Alternative moves become saved variations.'}));}
    function render(){const g=new Chess(state.node.fenAfter);board.setPosition(g);board.setLastMove(state.node.move?[state.node.move.from,state.node.move.to]:null);board.setMovable({color:g.turnColor(),dests:g.destinationsMap(),onMove:(from,to)=>{const p=g.get(from);if(p?.type==='p'&&/[18]$/.test(to)){modal('Promote pawn',(body,close)=>body.append(h('div.toolbar',['q','r','b','n'].map(promo=>button(promo.toUpperCase(),()=>{close();play({from,to,promotion:promo});})))));}else play({from,to});}});comment.value=state.node.comment||'';nag.value=state.node.nags[0]||'';fen.textContent=state.node.fenAfter;latestLines=[];drawBest();renderTablebase();renderMoves();renderContext();clearTimeout(liveTimer);if(live)liveTimer=setTimeout(evaluate,350);}
    // One brand per engine line, so a line's arrow, its border and its score all
    // carry the same colour. Map before filtering: a line with no PV still owns its slot.
    function brandFor(i){return ['green','blue','red','yellow'][i%4];}
    function drawBest(){board.setShapes(arrows.checked?latestLines.map((l,i)=>l.pv?.[0]?{from:l.pv[0].slice(0,2),to:l.pv[0].slice(2,4),brand:brandFor(i),label:String(i+1)}:null).filter(Boolean):[],{answer:true});}
    function showEvaluation(data,position){latestLines=data.lines||[];drawBest();engineBody.replaceChildren(...latestLines.map((l,i)=>{const g=new Chess(position),sans=[];for(const m of l.pv||[]){const done=g.move(m);if(!done)break;sans.push(done.san);}const sign=position.split(' ')[1]==='w'?1:-1;const score=l.mate!=null?'M'+l.mate*sign:(sign*(l.cp||0)/100).toFixed(2);return h('div.engine-line',{style:{'--line-color':'var(--shape-'+brandFor(i)+')'}},[h('span.line-rank',{text:String(i+1)}),h('strong',{text:score}),h('span.line-depth',{text:'depth '+l.depth,title:'Search depth reached'}),h('span',{text:sans.join(' ')}),h('small',{text:' White perspective'}),button('Add to tree',()=>addEngineLine(position,sans),'line-add')]);}));if(data.cpu_percent!=null)resources.textContent='CPU '+data.cpu_percent.toFixed(1)+'% (100% = one core) · Memory '+data.memory_mb+' MB';else resources.textContent='Install psutil for measured CPU and memory usage.';}
    async function evaluate(){clearTimeout(livePoll);const id=++evalRequest,position=state.node.fenAfter;
      try{const data=await api('engine/live',{fen:position,multipv:Number(pv.value)});if(closed||id!==evalRequest)return;liveId=data.id;
        async function update(){try{const result=await api('engine/live');if(closed||id!==evalRequest||result.id!==liveId||state.node.fenAfter!==position)return;if(result.lines.length)showEvaluation(result,position);if(result.error)throw new Error(result.error);if(result.running)livePoll=setTimeout(update,250);}catch(err){if(!closed&&id===evalRequest)resources.textContent=err.message;}}
        live=true;liveBox.checked=true;await update();
      }catch(err){if(!closed&&id===evalRequest)resources.textContent=err.message;}}
    // The lichess tablebase stops at seven pieces, so above that the card has nothing
    // to offer and stays out of the way entirely.
    async function renderTablebase(){const id=++tbRequest,position=state.node.fenAfter;tablebaseBody.replaceChildren();
      tablebaseCard.hidden=Object.keys(new Chess(position).piecesMap()).length>7;
      if(tablebaseCard.hidden||!tablebaseToggle.checked)return;
      tablebaseBody.textContent='Looking up the endgame…';try{const data=await api('tablebase?'+new URLSearchParams({fen:position}));if(id!==tbRequest||closed)return;
        const invert={win:'loss',loss:'win',draw:'draw','cursed-win':'blessed-loss','blessed-loss':'cursed-win','maybe-win':'maybe-loss','maybe-loss':'maybe-win','syzygy-win':'syzygy-loss','syzygy-loss':'syzygy-win'};
        tablebaseBody.replaceChildren(h('b',{text:(position.split(' ')[1]==='w'?'White':'Black')+' to move: '+data.category}),h('p.muted',{text:'DTZ '+(data.dtz??'unknown')+' · Cursed wins and blessed losses draw under the 50-move rule.'}),...(data.moves||[]).map(m=>button(m.san+' · '+(invert[m.category]||m.category)+' · DTZ '+(m.dtz??'?'),()=>play(m.uci))));
      }catch(err){if(id===tbRequest&&!closed)tablebaseBody.textContent=err.message;}}
    async function renderContext(){const id=++contextRequest,position=state.node.fenAfter;contextTabs.querySelectorAll('button').forEach(b=>b.classList.toggle('active',b.textContent===state.context));contextBody.replaceChildren(h('p.muted',{text:'Finding connections…'}));try{const data=await api('study/position?'+new URLSearchParams({fen:position}));if(id!==contextRequest||state.view!=='analysis')return;contextBody.replaceChildren();
      if(state.context==='Library'){contextBody.append(h('p.muted',{text:data.indexed_games.toLocaleString()+' games position-indexed · first 24 plies'}));if(!data.moves.length)contextBody.append(h('p',{text:'No indexed continuations here. Index a collection from Study folders.'}));for(const m of data.moves)contextBody.append(h('div.context-item',[button(m.san,()=>play(m.san)),h('span.muted',{text:'  '+m.games+' games · '+m.white+' / '+m.draws+' / '+m.black})]));for(const g of data.games.slice(0,12))contextBody.append(h('div.context-item',[button(g.white+' — '+g.black,()=>openGame(g.id)),h('div.muted',{text:g.date+' · '+g.result})]));}
      if(state.context==='History'){const earliest=data.games.find(g=>g.date&&!g.date.startsWith('0000'));contextBody.append(h('div.eyebrow',{text:'First seen in your indexed library'}),h('h3',{text:earliest?earliest.white+' — '+earliest.black:'No dated games indexed'}),h('p.muted',{text:earliest?earliest.event+' · '+earliest.date:'Import historical games and index their collection to discover provenance.'}));if(earliest)contextBody.append(button('Open earliest game',()=>openGame(earliest.id)));const max=Math.max(1,...data.decades.map(d=>d.games));for(const d of data.decades)contextBody.append(h('div.timeline-bar',[h('span',{text:d.decade+'s'}),h('i',{style:{width:(d.games/max*110)+'px'}}),h('span',{text:d.games})]));contextBody.append(h('p.muted',{text:'Dates and counts come from your indexed PGNs; this is not a claim of the first game ever played.'}));}
      if(state.context==='Study'){contextBody.append(h('div.eyebrow',{text:'Your position notebook'}),button('＋ Pin a link or note',()=>pinDialog(position,renderContext)));for(const pin of data.pins)contextBody.append(h('div.context-item',[pin.url?link(pin.title,pin.url):h('b',{text:pin.title}),h('p.muted',{text:pin.note}),button('Remove',async()=>{await api('study/pins/'+pin.id,null,'DELETE');renderContext();})]));const opening=parsed.headers.Opening;contextBody.append(h('div.divider'),h('h3',{text:'Free study material'}));if(opening)contextBody.append(link('Wikipedia: '+opening,'https://en.wikipedia.org/wiki/'+encodeURIComponent(opening.split(':')[0].replace(/ /g,'_'))));const path=PGN.pathTo(state.node).map((n,i)=>((i%2===0?Math.floor(i/2)+1+'.':Math.floor(i/2)+1+'...')+n.san));contextBody.append(button('Find opening references',async()=>{const refs=await api('literature?'+new URLSearchParams({moves:JSON.stringify(PGN.pathTo(state.node).map(n=>n.san)),opening:opening||'',eco:parsed.headers.ECO||''}));const box=h('div');for(const ref of refs.links)box.append(h('div.context-item',[link(ref.title,ref.url)]));if(refs.message)box.append(h('p.muted',{text:refs.message}));contextBody.append(box);}));contextBody.append(h('p.muted',{text:'Online references need a connection. Your saved notes and PGNs are available offline.'}));}
    }catch(err){contextBody.replaceChildren(h('p.error-message',{text:err.message}));}}
    async function annotate(){await api('engine/annotate',{game_id:state.selected?.id,positions:[parsed.root,...PGN.mainline(parsed.root)].map(n=>({ply:n.ply,fen:n.fenAfter,san:n.san})),movetime:200});clearInterval(poll);poll=setInterval(act(async()=>{const status=await api('engine/annotate');engineBody.replaceChildren(h('p.muted',{style:{padding:'16px'},text:`Annotating ${status.done} / ${status.total} positions…`}),button('Stop annotation',()=>api('engine/stop',{})));if(!status.running){clearInterval(poll);if(status.error)throw new Error(status.error);const nodes=[parsed.root,...PGN.mainline(parsed.root)];status.results.forEach((r,i)=>{const n=nodes[i];if(!n)return;n.comment=((n.comment||'')+' '+(r.cp!==null?'[%eval '+(r.cp/100).toFixed(2)+']':'')).trim();if(r.played_judgment&&nodes[i+1])nodes[i+1].nags=[{'blunder':'$4','mistake':'$2','inaccuracy':'$6'}[r.played_judgment]];});markDirty();render();engineBody.replaceChildren(h('p.muted',{style:{padding:'16px'},text:'Annotation complete. Save changes to keep these evaluations in your PGN.'}));}}),700);}
    async function editTags(){if(!state.selected)throw new Error('Save this game first.');const data=await api('study/tags?game_id='+state.selected.id);modal('Organize this game',(body,close)=>{const input=h('input',{value:data.tags.join(', '),placeholder:'model game, tournament prep, endgame'});body.append(field('Tags, separated by commas',input),h('div.dialog-actions',[button('Cancel',close),button('Save tags',async()=>{await api('study/tags',{game_id:state.selected.id,tags:input.value.split(',')},'PUT');close();},'primary')]));});}
    async function deleteGame(){if(!state.selected)throw new Error('This game has not been saved.');if(confirm('Remove this game from your library index?')){await api('games/'+state.selected.id,null,'DELETE');newGame();go('database');}}
    render();
    const key=e=>{if(state.view!=='analysis'||/INPUT|TEXTAREA|SELECT/.test(e.target.tagName)||document.querySelector('dialog[open]'))return;if(e.key==='ArrowLeft'){e.preventDefault();jump(state.node.parent||state.node);}if(e.key==='ArrowRight'){e.preventDefault();jump(state.node.children[0]||state.node);}};
    document.addEventListener('keydown',key);const oldGoCleanup=()=>{closed=true;++evalRequest;++tbRequest;clearTimeout(livePoll);document.removeEventListener('keydown',key);api('engine/live',null,'DELETE').catch(()=>{});};state.analysisCleanup=oldGoCleanup;
  }
  async function saveGame(){if(state.selected){await api('games/'+state.selected.id,{pgn:serialize(state.parsed)},'PUT');state.dirty=false;App.toast('Annotations saved to PGN');return go('analysis');}
    // A datalist only suggests once the box is empty, so every collection is listed outright.
    modal('Save to your library',(body,close)=>{
      const existing=state.collections.map(c=>[c.name,c.name+' · '+c.games.toLocaleString()+' games']);
      const preferred=state.collections.some(c=>c.name==='My games')?'My games':(existing[0]||['__new'])[0];
      const choices=select([...existing,['__new','＋ New collection…']],preferred);
      const fresh=h('input',{placeholder:'e.g. Autumn tournament preparation'});
      const freshField=field('New collection name',fresh);
      const event=h('input',{value:state.parsed.headers.Event||'Study'});
      function sync(){freshField.hidden=choices.value!=='__new';}
      choices.addEventListener('change',sync);
      body.append(field('Study title / event',event),field('Collection',choices),freshField,
        h('div.dialog-actions',[button('Cancel',close),button('Save',async()=>{
          const name=(choices.value==='__new'?fresh.value:choices.value).trim();
          if(!name)throw new Error('Name the collection to save into.');
          state.parsed.headers.Event=event.value;
          const data=await api('games',{pgn:serialize(state.parsed),collection:name});
          state.dirty=false;close();
          App.toast(data.added?'Saved to '+name:'This game is already in your library');
          await refreshMeta();
          // Adopt the saved game into this same tab; opening it would spawn another.
          const found=await api('games?'+new URLSearchParams({collection:name,sort:'added',limit:1}));
          if(found.games.length)state.selected=found.games[0];
          stashBoard();await go('analysis');
        },'primary')]));
      sync();
    });}
  function pinDialog(fen,refresh){modal('Keep this idea',(body,close)=>{const title=h('input',{placeholder:'Why this position matters'}),url=h('input',{placeholder:'https://… (optional)'}),note=h('textarea',{rows:4,placeholder:'Your notes, available offline'});body.append(field('Title',title),field('Link',url),field('Note',note),h('div.dialog-actions',[button('Cancel',close),button('Save to position',async()=>{await api('study/pins',{fen,title:title.value,url:url.value,note:note.value});close();refresh();},'primary')]));});}
  async function addToRepertoire(){const path=PGN.pathTo(state.node);if(!path.length)throw new Error('Choose a position after at least one move.');const list=await api('repertoires');modal('Keep this line in your repertoire',(body,close)=>{const choices=select([['','Create a repertoire'],...list.repertoires.map(r=>[String(r.id),r.name])],'');const title=h('input',{value:'My White repertoire'}),side=select([['w','White'],['b','Black']],'w');body.append(field('Repertoire',choices),field('New repertoire name',title),field('Play as',side),h('p.muted',{text:PGN.lineToText(path)}),h('div.dialog-actions',[button('Cancel',close),button('Add line',async()=>{let rep={name:title.value,color:side.value,data:{lines:[]}};if(choices.value){rep=(await api('repertoires/'+choices.value)).repertoire;rep.data=JSON.parse(rep.data);}rep.data.lines=rep.data.lines||[];const sans=path.map(n=>n.san);if(!rep.data.lines.some(l=>l.moves.join(' ')===sans.join(' ')&&l.fen===state.parsed.startFen))rep.data.lines.push({moves:sans,fen:state.parsed.startFen,due:0,interval:0,successes:0});await api('repertoires'+(choices.value?'/'+choices.value:''),rep,choices.value?'PUT':'POST');close();App.toast('Line added to repertoire');},'primary')]));});}
  async function repertoires(){const data=await api('repertoires');content.append(heading('Prepare with purpose','Your repertoire','Keep your lines. Revisit the uncertain moves. Make the ideas yours.',[button('Build on the board',()=>go('analysis'),'primary')]));const grid=h('div.cards-grid');content.append(grid);if(!data.repertoires.length)grid.append(empty('Start with one good line','Open a game or build a line on the analysis board, then choose Add to repertoire.',[button('Open analysis board',()=>go('analysis'),'primary')]));for(const meta of data.repertoires){const rep=(await api('repertoires/'+meta.id)).repertoire;const data=JSON.parse(rep.data),lines=data.lines||[],due=lines.filter(l=>(l.due||0)<=Date.now());grid.append(h('section.card.study-card',[h('div.eyebrow',{text:meta.color==='w'?'White repertoire':'Black repertoire'}),h('h3',{text:meta.name}),h('p.muted',{text:lines.length+' lines · '+due.length+' due for review'}),h('div.toolbar',[button('Drill due lines',()=>{if(!due.length)throw new Error('All lines reviewed. Come back when they are due.');drillLine(due[0].moves,due[0].fen,rep,due[0]);},'primary'),button('Browse lines',()=>browseRepertoire(rep)),button('Export PGN',()=>{const pgn=lines.map(l=>'[Event "'+meta.name.replace(/"/g,'')+'"]\n[SetUp "1"]\n[FEN "'+l.fen+'"]\n[Result "*"]\n\n'+l.moves.map((m,i)=>(i%2===0?(Math.floor(i/2)+1)+'. ':'')+m).join(' ')+' *').join('\n\n');download(pgn,'repertoire.pgn');})])]));}}
  function browseRepertoire(rep){const data=JSON.parse(rep.data);modal(rep.name,(body,close)=>{for(const l of data.lines||[])body.append(h('div.context-item',[h('p',{text:l.moves.join(' ')}),button('Study line',()=>{if(state.dirty&&!confirm('Discard unsaved analysis?'))return;state.selected=null;state.parsed=PGN.parse('[Event "Repertoire study"]\n[White "White"]\n[Black "Black"]\n[SetUp "1"]\n[FEN "'+l.fen+'"]\n[Result "*"]\n\n'+l.moves.join(' ')+' *');state.node=state.parsed.root;state.dirty=false;close();go('analysis');}),button('Drill',()=>{close();drillLine(l.moves,l.fen,rep,l);})]));body.append(button('Close',close));});}
  function drillLine(nodes,fen,rep,line){const sans=nodes.map(n=>typeof n==='string'?n:n.san);if(!sans.length)throw new Error('This line has no moves yet.');modal('Recall the line',(body,close)=>{const holder=h('div.board-holder',{style:{width:'min(350px,100%)',margin:'15px auto'}}),prompt=h('div.drill-prompt'),feedback=h('div.status-message'),input=h('input',{placeholder:'Your next move','aria-label':'Recall move'}),blind=h('input',{type:'checkbox',checked:true,onchange:()=>b.setBlindfold(blind.checked?'pieces':'off')});let index=0,mistakes=0,g=new Chess(fen),completed=false;const b=new Board(holder,{viewOnly:true,blindfold:'pieces'});b.setPosition(g);const peek=button('Peek',()=>{});peek.addEventListener('pointerdown',()=>{b.setPeeking(true);App.stat('repertoire-peeks',{count:1});});['pointerup','pointerleave','pointercancel'].forEach(e=>peek.addEventListener(e,()=>b.setPeeking(false)));
    const form=h('form.toolbar',{onsubmit:act(e=>{e.preventDefault();if(completed)return;const test=new Chess(g.fen()),move=test.move(input.value);if(!move||move.san!==sans[index]){mistakes++;feedback.textContent='Try again. Recall the line you saved.';return;}g=test;index++;input.value='';feedback.textContent='Correct.';advance();})},[input,h('button.btn.primary',{type:'submit',text:'Check move'})]);
    const finish=button('Save review',async()=>{if(!completed)throw new Error('Finish the line first.');if(rep&&line){const data=JSON.parse(rep.data),item=data.lines.find(l=>l.fen===line.fen&&l.moves.join(' ')===line.moves.join(' '));item.successes=(item.successes||0)+(mistakes===0?1:0);item.interval=mistakes?1:Math.max(1,Math.round((item.interval||.4)*2.5));item.due=Date.now()+item.interval*86400000;await api('repertoires/'+rep.id,{name:rep.name,color:rep.color,data},'PUT');}App.stat('repertoire',{reviews:1,mistakes});close();if(state.view==='repertoire')go('repertoire');},'primary');finish.disabled=true;
    function advance(){if(rep)while(index<sans.length&&g.turnColor()!==rep.color){g.move(sans[index++]);}b.setPosition(g);completed=index===sans.length;prompt.textContent=completed?'Line complete':`Move ${index+1} of ${sans.length} · ${g.turnColor()==='w'?'White':'Black'} to move`;finish.disabled=!completed;input.disabled=completed;if(completed){b.setBlindfold('off');feedback.textContent=mistakes+' retries. '+(mistakes?'Review again tomorrow.':'A little more of the board is yours.');}}
    body.append(h('label.toolbar',[blind,'Blindfold mode']),holder,prompt,form,feedback,h('div.dialog-actions',[peek,button('Close',close),finish]));advance();});}
  async function studies(){content.append(heading('A place for your ideas','Study folders','Organize preparation into real folders, with portable PGNs behind every collection.',[button('Create collection',collectionDialog),button('＋ Study folder',()=>folderDialog(),'primary')]));content.append(h('p.muted',{text:state.studyRoot}));const grid=h('div.cards-grid');content.append(grid);if(!state.folders.length)grid.append(empty('Build your study space','Create a folder such as Tournament preparation, then add White repertoire, Black repertoire, Model games, and Endgames beneath it.',[button('Create study structure',async()=>{const root=await api('study/folders',{name:'Chess study'});for(const name of ['White repertoire','Black repertoire','Annotated games','Model games','Endgames','Tactics'])await api('study/folders',{name,parent_id:root.id});await go('studies');},'primary')]));
    for(const folder of state.folders){const collections=state.assignments.filter(a=>a.folder_id===folder.id).map(a=>state.collections.find(c=>c.id===a.collection_id)).filter(Boolean);grid.append(h('section.card.study-card',[h('div.folder-icon',{text:'▱'}),h('div.eyebrow',{text:folder.path}),h('h3',{text:folder.name}),h('p.muted',{text:collections.length+' collections · '+collections.reduce((n,c)=>n+c.games,0)+' games'}),...collections.map(c=>button(c.name+'  ('+c.games+')',()=>{state.filters={collection:String(c.id)};state.offset=0;go('database');})),h('div.toolbar',[button('Add collection',()=>assignDialog(folder)),button('Subfolder',()=>folderDialog(folder.id)),button('Delete',()=>deleteFolderDialog(folder),'danger')])]));}
    const collections=h('div.card-pad');for(const c of state.collections)collections.append(h('div.context-item',[h('b',{text:c.name+' · '+c.games+' games'}),h('div.toolbar',[button('Browse',()=>{state.filters={collection:String(c.id)};state.offset=0;go('database');}),button('Index positions',async()=>{await api('study/index',{collection:c.id});App.toast('Position indexing started');watchIndex();}),h('a.btn',{href:'/api/collections/'+c.id+'/pgn',download:c.name+'.pgn',text:'Export PGN'}),button('Delete',()=>collectionDeleteDialog(c),'danger')])]));const status=h('p.status-message');collections.append(status);content.append(h('div',{style:{marginTop:'24px'}},[card('Collections & position indexing',collections)]));
    function watchIndex(){clearInterval(poll);poll=setInterval(act(async()=>{const s=await api('study/index');status.textContent=s.running?`Indexing ${s.collection}: ${s.done} / ${s.total} games`:`Indexed ${s.done} games; ${s.errors} could not be indexed.`;if(s.error)status.textContent=s.error;if(!s.running)clearInterval(poll);}),700);}if((await api('study/index')).running)watchIndex();}
  function folderDialog(parent){modal('Create a study folder',(body,close)=>{const name=h('input',{placeholder:'e.g. Autumn tournament preparation'}),parents=select([['','Top level'],...state.folders.map(f=>[String(f.id),f.path])],parent?String(parent):'');body.append(field('Folder name',name),field('Inside',parents),h('div.dialog-actions',[button('Cancel',close),button('Create folder',async()=>{await api('study/folders',{name:name.value,parent_id:parents.value?Number(parents.value):null});close();go('studies');},'primary')]));});}
  function deleteFolderDialog(folder){
    const nested=state.folders.filter(f=>f.path===folder.path||f.path.startsWith(folder.path+'/'));
    const ids=new Set(nested.map(f=>f.id));
    const released=state.assignments.filter(a=>ids.has(a.folder_id)).map(a=>state.collections.find(c=>c.id===a.collection_id)).filter(Boolean);
    modal('Delete '+folder.name+'?',(body,close)=>{
      body.append(h('p',{text:nested.length>1?'This removes the folder and the '+(nested.length-1)+' folders nested inside it:':'This removes the folder:'}),
        ...nested.map(f=>h('p.muted',{text:f.path})),
        h('p',{text:released.length?'These collections stay in your library — they simply stop belonging to a folder:':'No collections are filed here.'}),
        ...released.map(c=>h('p.muted',{text:c.name+' · '+c.games+' games'})),
        h('p.muted',{text:'Games and PGN files are never touched, and any file you put in the folder yourself is left on disk.'}),
        h('div.dialog-actions',[button('Cancel',close),button('Delete folder',async()=>{
          const result=await api('study/folders/'+folder.id,null,'DELETE');close();
          App.toast(result.kept.length?result.deleted+' removed · '+result.kept.length+' kept on disk because they still hold your own files':result.deleted+(result.deleted===1?' folder removed':' folders removed'));
          await go('studies');},'danger')]));
    });
  }
  function collectionDialog(){modal('Create a collection',(body,close)=>{const name=h('input',{placeholder:'e.g. My annotated tournament games'});body.append(field('Collection name',name),h('div.dialog-actions',[button('Cancel',close),button('Create',async()=>{await api('collections',{name:name.value});close();go('studies');},'primary')]));});}
  function collectionDeleteDialog(c){
    modal('Delete '+c.name+'?',(body,close)=>{
      const files=h('input',{type:'checkbox'});
      body.append(h('p',{text:c.games?'This removes '+c.games.toLocaleString()+' games from your library index, the collection itself, and any position index built from it.':'This collection holds no games.'}),
        field('Also delete this collection\u2019s PGN files on disk',files),
        h('p.muted',{text:'Left unticked, the original PGN text stays in your library folder and only the index entries go. Study folders that referenced this collection are rewritten either way.'}),
        h('div.dialog-actions',[button('Cancel',close),button('Delete collection',async()=>{
          await api('collections/'+c.id+(files.checked?'?files=1':''),null,'DELETE');close();
          App.toast(c.name+' deleted');await go('studies');},'danger')]));
    });
  }
  function assignDialog(folder){modal('Add a collection to '+folder.name,(body,close)=>{const choices=select(state.collections.map(c=>[String(c.id),c.name]),String(state.collections[0]?.id||''));body.append(field('Collection',choices),h('p.muted',{text:'A collection belongs to one study folder. Its PGN remains in the library’s collections directory; the folder manifest records its location.'}),h('div.dialog-actions',[button('Cancel',close),button('Save',async()=>{if(!choices.value)throw new Error('Create a collection first.');await api('study/assign',{folder_id:folder.id,collection_id:Number(choices.value)});close();go('studies');},'primary')]));});}
  async function imports(){await importHistory();content.append(heading('Bring your chess home','Import games','PGN files, master collections, and your own online games — together in one library.'));const collection=h('input',{placeholder:'e.g. Tournament games'}),status=h('div.status-message'),pgn=h('textarea',{rows:9,placeholder:'Paste one game or an entire collection in PGN format…'}),files=h('input',{type:'file',accept:'.pgn',multiple:true});
    // The file names itself; a name you typed yourself is never overwritten.
    let namedByHand=false;collection.addEventListener('input',()=>{namedByHand=true;});
    files.addEventListener('change',()=>{if(!files.files.length)return;
      if(!namedByHand||!collection.value.trim())collection.value=files.files[0].name.replace(/\.[^.]*$/,'').trim()||'Imported games';});
    async function imported(data){status.textContent=`Added ${data.added} games · ${data.duplicates} duplicates · ${data.skipped||0} skipped`;await refreshMeta();await importHistory();}
    const paste=card('PGN files & clipboard',h('div.card-pad',[field('Collection name (required)',collection),field('Choose PGN files',files),pgn,h('div.toolbar',{style:{marginTop:'12px'}},[button('Import PGN',async()=>{if(!collection.value.trim())throw new Error('Name the collection these games should go into.');status.textContent='Importing…';watchImport();if(files.files.length){let totals={added:0,duplicates:0,skipped:0};for(const f of files.files){const result=await api('games',{pgn:await f.text(),collection:collection.value});for(const k of Object.keys(totals))totals[k]+=result[k]||0;}await imported(totals);}else await imported(await api('games',{pgn:pgn.value,collection:collection.value}));},'primary')]),status]));
    const source=select([['lichess','lichess'],['chesscom','chess.com']],'lichess'),online_collection=h('input',{value:'lichess imports'}),user=h('input',{placeholder:'Username'}),max=h('input',{type:'number',value:100,min:1,max:2000}),token=h('input',{type:'password',placeholder:'Optional lichess token',autocomplete:'off'}),onlineStatus=h('p.status-message');
    let onlineNamedByHand=false;online_collection.addEventListener('input',()=>{onlineNamedByHand=true;});
    source.addEventListener('change',()=>{if(!onlineNamedByHand)online_collection.value=source.value==='lichess'?'lichess imports':'chess.com imports';});
    const online=card('Your online games',h('div.card-pad',[field('Service',source),field('Collection name',online_collection),field('Username',user),field('Maximum games',max),field('lichess token',token),button('Import account games',async()=>{onlineStatus.textContent='Downloading games…';watchImport();if(!online_collection.value.trim())throw new Error('Name the collection these games should go into.');const result=await api('import/'+source.value,{user:user.value,max:Number(max.value),token:token.value,collection:online_collection.value.trim()});onlineStatus.textContent=`Added ${result.added} games · ${result.duplicates} duplicates`;},'primary'),onlineStatus,h('p.muted',{text:'Downloads need a connection. Imported games stay available offline.'})]));
    const path=h('input',{placeholder:'C:\\Chess\\TWIC or https://…/games.zip'}),pathStatus=h('p.status-message');const bulk=card('Archives, folders & URLs',h('div.card-pad',[field('Local path or URL',path),h('p.muted',{text:'Stream PGN, ZIP, GZ, BZ2 or optional ZST archives. A folder is scanned recursively. For CBH, CBV and SI4, export to PGN in the originating application.'}),button('Import source',async()=>{pathStatus.textContent='Reading source…';watchImport();const result=await api('import/source',{path:path.value,collection:collection.value});pathStatus.textContent=`Added ${result.added} games · ${result.duplicates} duplicates`;},'primary'),pathStatus]));content.append(h('div.settings-grid',[paste,h('div.section-stack',[online,bulk])]));}
  async function masters(){await mentorSearch();content.append(heading('Learn from the great games','Master games','Build your own reference library from freely available PGN collections.'));const week=h('input',{type:'number',placeholder:'TWIC issue number',min:1}),status=h('p.status-message');content.append(h('div.cards-grid',[
    h('section.card.study-card',[h('div.eyebrow',{text:'Weekly tournament games'}),h('h3',{text:'The Week in Chess'}),h('p.muted',{text:'Choose an issue to download its PGN archive into your Masters collection.'}),field('Issue number',week),button('Import issue',async()=>{if(!Number(week.value))throw new Error('Enter a TWIC issue number.');status.textContent='Downloading and importing…';watchImport();const r=await api('import/source',{path:'https://theweekinchess.com/zips/twic'+Number(week.value)+'g.zip',collection:'Masters / TWIC'});status.textContent=`${r.added} games added · ${r.duplicates} duplicates`;},'primary'),status,link('Browse TWIC issues','https://theweekinchess.com/twic')]),
    h('section.card.study-card',[h('div.eyebrow',{text:'Players & tournaments'}),h('h3',{text:'PGN Mentor'}),h('p.muted',{text:'Find a player or event collection, then paste its download URL in Online & imports.'}),link('Browse free PGN collections','https://www.pgnmentor.com/files.html'),button('Import a collection',()=>go('imports'))]),
    h('section.card.study-card',[h('div.eyebrow',{text:'Your offline reference'}),h('h3',{text:'Explore by position'}),h('p.muted',{text:'After import, index a collection from Study folders. The analysis board will show continuations, results, and the earliest dated games at each position.'}),button('Manage position indexes',()=>go('studies'))]) ]));}
  async function tactics(){content.append(heading('Recognize the opportunity','Tactics','Train online with Chess Tempo, or work through your own local problem sets.'));const grid=h('div.cards-grid');content.append(grid);grid.append(h('section.card.study-card',[h('div.eyebrow',{text:'Chess Tempo'}),h('h3',{text:'Your tactics trainer'}),h('p.muted',{text:'We recommend Chess Tempo as the best place to train tactics. Use your own account and training history. The native app opens the trainer in its own embedded window.'}),button('Open Chess Tempo',async()=>{if(window.pywebview?.api?.open_tactics)await window.pywebview.api.open_tactics();else window.open('https://chesstempo.com/chess-tactics/','_blank','noopener');},'primary')]));const puzzles=state.collections.filter(c=>c.kind==='puzzles'||/tactic|puzzle|problem/i.test(c.name));grid.append(h('section.card.study-card',[h('div.eyebrow',{text:'Offline problem sets'}),h('h3',{text:'Train your own positions'}),h('p.muted',{text:'Import your authorized PGN exports into a collection named Tactics. Open a problem and choose Train blindfolded to recall its solution.'}),button('Import problem set',()=>go('imports')),...puzzles.map(c=>button(c.name+' · '+c.games,()=>{state.filters={collection:String(c.id)};go('database');}))]));}
  async function settings(){content.append(heading('Make Caissa yours','Settings','Choose where your library lives and how your board looks.'));const holder=h('div.board-holder',{style:{maxWidth:'460px',margin:'auto'}});preview=new Board(holder,{viewOnly:true});preview.setPosition(new Chess());
    const swatches=h('div.swatches');Object.entries(themes).forEach(([name,colors])=>{const b=h('button.swatch'+((state.prefs.theme||'Sage')===name?'.active':''),{title:name,onclick:act(async()=>{state.prefs.theme=name;delete state.prefs.light;delete state.prefs.dark;await savePrefs();swatches.querySelectorAll('button').forEach(x=>x.classList.toggle('active',x===b));light.value=colors[0];dark.value=colors[1];})},[h('span',{style:{background:`conic-gradient(${colors[1]} 25%,${colors[0]} 0 50%,${colors[1]} 0 75%,${colors[0]} 0)`,backgroundSize:'31px 22px'}}),h('small',{text:name})]);swatches.append(b);});
    const colors=themes[state.prefs.theme]||themes.Sage,light=h('input',{type:'color',value:state.prefs.light||colors[0],oninput:act(async()=>{state.prefs.light=light.value;await savePrefs();})}),dark=h('input',{type:'color',value:state.prefs.dark||colors[1],oninput:act(async()=>{state.prefs.dark=dark.value;await savePrefs();})});
    // Both pickers preview real artwork: the set on a light/dark square pair, the
    // treatment on whichever set is currently chosen.
    const pieceSetName=()=>state.prefs.pieceSet||'cburnett';
    const pair=(set,extra)=>h('span.piece-pair'+(extra||''),[h('img',{src:Board.pieceArt(set,'w','k'),alt:'','data-piece':'wk',loading:'lazy'}),h('img',{src:Board.pieceArt(set,'b','q'),alt:'','data-piece':'bq',loading:'lazy'})]);
    const treatments=thumbPicker('Piece treatment',[['classic','Natural'],['outline','Crisp contrast'],['wood','Warm wood'],['slate','Soft graphite']]
      .map(([value,text])=>[value,text,pair(pieceSetName(),'.treat-'+value)]),state.prefs.pieces||'classic',async value=>{state.prefs.pieces=value;await savePrefs();});
    const pieceSet=thumbPicker('Piece set',Board.PIECE_SETS.map(([value,text])=>[value,text,pair(value)]),pieceSetName(),async value=>{
      state.prefs.pieceSet=value;
      treatments.querySelectorAll('img[data-piece]').forEach(img=>{img.src=Board.pieceArt(value,img.dataset.piece[0],img.dataset.piece[1]);});
      await savePrefs();});
    await storageSettings();
    const orientation=select([['w','White at the bottom'],['b','Black at the bottom']],state.prefs.orientation||'w',act(async()=>{state.prefs.orientation=orientation.value;await savePrefs();}));
    const coordinates=h('input',{type:'checkbox',checked:state.prefs.coordinates!==false,onchange:act(async()=>{state.prefs.coordinates=coordinates.checked;await savePrefs();})}),animate=h('input',{type:'checkbox',checked:state.prefs.animate!==false,onchange:act(async()=>{state.prefs.animate=animate.checked;await savePrefs();})});
    content.append(h('div.settings-grid',[card('Board & pieces',h('div.card-pad',[field('Board palette',swatches),h('div.toolbar',[field('Light squares',light),field('Dark squares',dark)]),field('Dark theme',h('input',{type:'checkbox',checked:!!state.prefs.darkMode,onchange:act(async e=>{state.prefs.darkMode=e.target.checked;await savePrefs();})})),field('Piece set',pieceSet),field('Piece treatment',treatments),field('Default orientation',orientation),field('Coordinates',coordinates),field('Animate moves',animate)])),card('Preview',h('div.card-pad',[holder,h('p.muted',{style:{marginTop:'20px'},text:'Your palette applies to analysis, previews, and all seven blindfold exercises.'})]))]));applyPrefs();}
  document.addEventListener('DOMContentLoaded',async()=>{
    await App.persistenceReady;
    const initial=location.hash;const originalGo=go; // App boots first so the original trainer stays intact.
    const root=document.getElementById('workspace');nav=h('nav.module-nav',{'aria-label':'Workspace'});
    modules.forEach(([id,icon,title])=>{const b=h('button',{onclick:()=>{if(state.analysisCleanup){state.analysisCleanup();state.analysisCleanup=null;}go(id);}},[h('span',{'aria-hidden':true,text:icon}),title]);b.dataset.view=id;nav.append(b);});
    crumb=h('strong',{text:'Database'});content=h('div.desk-body');root.append(h('aside.sidebar',[
      h('div.caissa-brand',[h('img',{src:'assets/caissa-128.png',alt:'Caissa, muse of chess'}),h('div',[h('strong',{text:'Caissa'}),h('small',{text:'THE CHESS STUDY'})])]),
      h('div',[h('div.nav-label',{text:'Workspace'}),nav]),h('div.sidebar-foot',[h('img',{src:'assets/caissa-128.png',alt:'Caissa',width:48,height:48}),h('b',{text:'Your chess. Your library.'}),h('span',{text:'Local files · portable PGN'})])]),
      h('div.desk',[h('header.desk-top',[h('div.crumb',['Workspace  /  ',crumb]),h('span.local-badge',{text:'Local library'})]),content]));
    try{const pref=await api('settings/appearance');state.prefs=JSON.parse(pref.value||'{}');}catch(err){/* Defaults remain usable if settings are unavailable. */}applyPrefs();
    window.Caissa={state,api,go,serialize,openGame};window.addEventListener('beforeunload',e=>{
      if(state.boards.length){stashBoard();state.prefs.analysisLayout=state.boards[0].layout;
        fetch('/api/settings/appearance',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({value:JSON.stringify(state.prefs)}),keepalive:true}).catch(()=>{});}
      if(state.dirty||state.boards.some(b=>b.dirty)){e.preventDefault();e.returnValue='';}});
    watchImport();
    await go(initial.startsWith('#workspace/')?initial.split('/')[1]:'database');
  });
})();

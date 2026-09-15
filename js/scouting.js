/* Player reports and practice, using local game evidence. */
(function () {
  'use strict';
  const FETCH_LABEL={lichess:'Lichess',chesscom:'Chess.com'};
  window.ScoutingView = async function (content, ctx) {
    const {h, button, field, select, api, heading, openGame, analyzeFen, openExplorer} = ctx;
    content.append(heading('Understand the player','Player lab','Find recurring patterns, prepare for an opponent, and retest mistakes from your games.'));
    const player=h('input',{placeholder:'Exact PGN name or online handle',value:''});
    // Scouting somebody else is the obvious use, so it leads; turning the same report
    // on yourself is the same machinery read the other way round and is explained as such.
    const mode=select([['opponent','Opponent prep'],['self','My prep']],'opponent');
    const source=select([['local','Games already in my library'],['lichess','Fetch from Lichess'],['chesscom','Fetch from Chess.com']],'local');
    const accountHint=h('p.muted');
    const purpose=h('p.mode-purpose');
    const refreshAccount=CaissaAccount.fill(player,()=>mode.value==='self'&&source.value!=='chesscom');
    // The name belongs to the person, not to the place the games come from: switching
    // source used to swap in a different draft and wipe out what had just been typed.
    const drafts=new Map();let draftKey=mode.value;
    function changeContext(){
      if(mode.value!==draftKey){
        drafts.set(draftKey,player.value);
        draftKey=mode.value;
        player.value=drafts.get(draftKey)||'';
        player.dispatchEvent(new Event('input'));
      }
      refreshAccount();
      accountHint.textContent=mode.value==='opponent'
        ?'Enter the opponent name: exact PGN name or online handle. Scores in this report belong to the opponent.'
        :source.value==='chesscom'?'Enter your Chess.com handle. Your linked Lichess account is separate.'
        :'My prep fills in your linked Lichess username. For local PGNs, enter the exact White or Black name if it differs.';
      purpose.replaceChildren(h('b',{text:mode.value==='opponent'?'Preparing against someone: ':'Reviewing your own play: '}),
        h('span',{text:mode.value==='opponent'
          ?'the report is built from their games — what they open with as each colour, which lines they score worst in, and where their clock runs low. Every row lists the games behind it, so you can take a candidate line to the analysis board and prepare it.'
          :'the same report turned on yourself — the openings you actually play, the lines you lose in, the moves that cost the most centipawns, and the time trouble around them. Any mistake it finds can be saved as a practice position that comes back on a schedule until you play it right.'}));
      fetchFields.hidden=source.value==='local';
    }
    content.append(h('section.card.card-pad',[
      h('h2',{text:'Start here'}),
      h('p',{text:'The Player Lab replays one person’s games and reports what keeps happening in them. Name the player, choose where the games come from, and press Build report once: fetching, indexing and the report itself all happen in that single run. Nothing is guessed — every figure links to the games it came from.'}),
      purpose,
      h('ol',[
        h('li',{text:'Name the player. Opponent prep wants their exact PGN name or online handle; My prep fills in your linked Lichess username by itself.'}),
        h('li',{text:'Choose where the games come from. Fetching from Lichess or Chess.com takes the newest games in the chosen time control — the last 100 by default, any number you like, or every game on the profile.'}),
        h('li',{text:'Dates are optional. Leave both empty and the newest games are used; fill either one to restrict the fetch and the report to that window.'}),
        h('li',{text:'Build report. Openings, weak lines and mistakes arrive as boards you can click straight through to the analysis board, and the games just fetched are handed to the opening explorer.'})
      ]),
      h('p.muted',{text:'Score means wins plus half of draws for the named player, whoever that is. Minimum games controls which lines are eligible to be called weak; start with 5. Move-quality and clock sections need games carrying saved evaluations and clock times, which Lichess exports provide and most other sources do not.'})
    ]));
    const speed=select([['','All time controls'],['bullet','Bullet'],['blitz','Blitz'],['rapid','Rapid'],
                        ['classical','Classical'],['correspondence','Correspondence']],'');
    const since=h('input',{type:'date'}), until=h('input',{type:'date'});
    const count=h('input',{type:'number',min:1,max:100000,value:100});
    const everything=h('input',{type:'checkbox'});
    const countField=field('How many games',count);
    everything.addEventListener('change',()=>{countField.hidden=everything.checked;});
    const fetchFields=h('div.filters',[countField,h('label.toolbar',[everything,'Every game on the profile'])]);
    const minimum=h('input',{type:'number',min:2,max:100,value:5});
    const output=h('div.scouting-report',{'aria-live':'polite'});
    mode.addEventListener('change',changeContext);source.addEventListener('change',changeContext);
    changeContext();

    const pct=n=>n==null?'No scored games':n+'%';
    /* ---------- boards as evidence ---------- */
    // A SAN move list says what happened; a board shows it. The report keeps its board
    // count down — a handful per section — rather than deferring the work, because a
    // thumbnail that only appears if something else fires first is a thumbnail that can
    // fail to appear at all.
    function thumbnail(fen,options){
      const opts=options||{};
      const holder=h('div.scout-thumb');
      holder.dataset.fen=fen;
      const board=new Board(holder,{viewOnly:true,draggable:false,animationMs:0,coordinates:false,
        orientation:opts.orientation||'w'});
      board.setPosition(fen);
      if(opts.shapes&&opts.shapes.length)board.setShapes(opts.shapes);
      if(!opts.onClick)return holder;
      const wrap=h('button.scout-thumb-button',{type:'button',title:opts.title||'Open on the analysis board',
        onclick:async()=>{try{await opts.onClick();}catch(err){App.toast(err.message,5000);}}},[holder]);
      return wrap;
    }
    // The move that was played, drawn on the position it was played from.
    function moveShape(fen,san){
      try{const played=new Chess(fen).move(san);
        return played?[{from:played.from,to:played.to,brand:'red'}]:null;}
      catch(err){return null;}
    }
    let report=null;
    const label=id=>{const g=report&&report.games&&report.games[id];
      return g?(g.white||'?')+' — '+(g.black||'?')+(g.date&&!g.date.startsWith('0000')?' · '+g.date.replace(/\./g,'-'):''):'Game '+id;};
    const evidence=ids=>h('div.evidence-list',(ids||[]).slice(0,6).map(id=>
      h('button.linkish',{type:'button',title:'Open this game on the analysis board',text:label(id),
        onclick:async()=>{try{await openGame(id);}catch(err){App.toast(err.message,5000);}}})));
    const section=(title,children)=>h('section.card.scouting-section',[h('h2',{text:title}),...children]);

    let activePlayer='',prepCollection=null;
    async function practice() {
      const {drills}=await api('scouting/drills?'+new URLSearchParams({player:activePlayer}));
      const box=h('div');
      box.append(h('p.muted',{text:'Submit a move in SAN (Nf3) or coordinates (g1f3). Success schedules retests at 1, 3, 9, 27, then 30 days. A miss returns tomorrow. These are engine best-move exercises, not claims that a weakness is fixed.'}));
      if(!drills.length)box.append(h('p',{text:'Create a practice position from a recorded mistake below. Stockfish must be installed.'}));
      for(const d of drills) {
        const due=d.due*1000<=Date.now();
        const row=h('article.scouting-drill',[h('h3',{text:d.theme+' · '+label(d.game_id)}),h('p',{text:d.successes+'/'+d.attempts+' successful reviews · '+(due?'Due now':'Retest '+new Date(d.due*1000).toLocaleDateString())})]);
        if(due){
          const holder=h('div',{style:{width:'min(320px,100%)',aspectRatio:'1'}});
          const board=new Board(holder,{viewOnly:true,animationMs:0});board.setPosition(d.fen);
          const input=h('input',{placeholder:'Your move',autocomplete:'off'});
          const feedback=h('p',{role:'status'});
          const submit=button('Check move',async()=>{
            const out=await api('scouting/review/'+d.id,{move:input.value});
            feedback.textContent=(out.correct?'Correct.':'Engine choice: '+out.solution+'.')+' Retest '+new Date(out.due*1000).toLocaleDateString();
            submit.disabled=true;input.disabled=true;
          });
          input.addEventListener('keydown',e=>{if(e.key==='Enter')submit.click();});
          row.append(holder,field('Your move',input),submit,feedback);
        }
        box.append(row);
      }
      return box;
    }

    /* ---------- one run, three stages ---------- */
    const progress=h('ol.scouting-progress',{role:'status'});
    function stage(text,state){
      const item=h('li',{'data-state':state||'working'},[h('span.scouting-progress-mark',{'aria-hidden':'true'}),h('span',{text})]);
      progress.append(item);
      return done=>{item.dataset.state='done';if(done)item.lastChild.textContent=done;};
    }
    async function waitForIndex(){
      const started=Date.now();
      for(;;){
        const state=await api('study/index');
        if(!state.running)return state;
        if(Date.now()-started>15*60*1000)throw new Error('Indexing is taking unusually long; the report can be built again once it finishes.');
        await new Promise(resolve=>setTimeout(resolve,700));
      }
    }
    async function fetchGames(){
      const finish=stage('Fetching games from '+FETCH_LABEL[source.value]+'…');
      const body={user:activePlayer,collection:'Prep: '+activePlayer,
                  max:everything.checked?0:Math.max(1,Number(count.value)||100),
                  perf:speed.value||undefined,since:since.value||undefined,until:until.value||undefined};
      const result=await api('import/'+source.value,body);
      prepCollection=result.collection_id||null;
      finish((result.added||0)+' games added · '+(result.duplicates||0)+' already in the library'
             +(result.linked?' · '+result.linked+' linked from other collections':''));
      return result;
    }
    async function indexGames(){
      const finish=stage('Indexing positions so the opening explorer can read them…');
      try{await api('study/index',{collection:prepCollection});}
      catch(err){/* already running: waiting for it is the same thing */}
      const state=await waitForIndex();
      finish('Positions indexed'+(state.errors?' · '+state.errors+' games could not be indexed':''));
    }

    const run=button('Build report',async()=>{
      if(!player.value.trim())throw new Error('Enter the exact player name or handle.');
      run.disabled=true;
      activePlayer=player.value.trim();sessionStorage.setItem('caissa-scout-player',activePlayer);
      prepCollection=null;report=null;
      progress.replaceChildren();
      output.replaceChildren(progress);
      try {
        if(source.value!=='local')await fetchGames();
        if(prepCollection)await indexGames();
        const finish=stage('Replaying the games and building the report…');
        report=await api('scouting?'+new URLSearchParams({player:activePlayer,speed:speed.value,
          since:since.value,until:until.value,min_games:minimum.value}));
        finish(report.analyzed_games+' games replayed');
        render();
      }catch(err){output.append(h('p.error-message',{role:'alert',text:err.message}));throw err;}
      finally{run.disabled=false;}
    },'primary');

    function render(){
      const table=(headers,rows)=>h('div.table-scroll',[h('table',[h('thead',[h('tr',headers.map(text=>h('th',{scope:'col',text})))]),h('tbody',rows)])]);
      const heads=[];
      heads.push(section((mode.value==='opponent'?'Opponent prep: ':'Scouting report: ')+report.player,[
        h('p',{text:report.baseline.games+' completed games · '+pct(report.baseline.score_pct)+' score · '+report.evaluated_games+' games with usable evaluations · '+report.clock_games+' games with clocks'}),
        h('p.muted',{text:report.analyzed_games+' games replayed; '+report.skipped.length+' skipped. Minimum sample for a weak line: '+report.minimum_games+' games.'+
          (speed.value?' Time control: '+speed.options[speed.selectedIndex].text+'.':'')+
          ((since.value||until.value)?' Window: '+(since.value||'any start')+' to '+(until.value||'present')+'.':' No date window: the newest games available.')}),
        h('div.toolbar',[
          button('Open in the opening explorer',()=>openExplorer({collection:prepCollection,player:activePlayer})),
          button('Print prep sheet',()=>window.print())]),
        ...(!report.analyzed_games?[h('p',{text:'No matching games. Names match exactly, ignoring case. Import games or check the name in your database.'})]:[])
      ]));
      output.replaceChildren(progress,...heads);

      /* ---------- what they play ---------- */
      const byColour=side=>report.openings.filter(o=>o.color===side).slice(0,5);
      const openingCard=entry=>h('article.scout-line',[
        thumbnail(startFen(entry.moves),{orientation:entry.color,title:'Put this opening on the analysis board',
          onClick:()=>analyzeFen(startFen(entry.moves))}),
        h('div.scout-line-body',[
          h('h4',{text:(entry.eco?entry.eco+' · ':'')+entry.opening}),
          h('p',{text:entry.games+' games · '+pct(entry.frequency_pct)+' of their games with this colour · '+pct(entry.score_pct)+' score'}),
          h('p.muted',{text:entry.moves.slice(0,10).join(' ')}),
          evidence(entry.evidence)])]);
      output.append(section('What they open with',[
        h('p.muted',{text:'Openings named from the moves actually played, counted separately for each colour. The share is of their completed games with that colour, and the score is theirs. Click a board to take the line to the analysis board.'}),
        ...(report.openings.length?[
          h('h3',{text:'As White'}),
          ...(byColour('w').length?byColour('w').map(openingCard):[h('p.muted',{text:'No games as White in this selection.'})]),
          h('h3',{text:'As Black'}),
          ...(byColour('b').length?byColour('b').map(openingCard):[h('p.muted',{text:'No games as Black in this selection.'})])
        ]:[h('p',{text:'No opening could be named from these games.'})]),
        h('div.toolbar',[button('Walk these openings move by move',()=>openExplorer({collection:prepCollection,player:activePlayer}))])
      ]));

      /* ---------- where it goes wrong ---------- */
      const lineCard=entry=>h('article.scout-line',[
        thumbnail(entry.fen,{orientation:entry.color,title:'Put this line on the analysis board',
          onClick:()=>analyzeFen(entry.fen)}),
        h('div.scout-line-body',[
          h('h4',{text:(entry.color==='w'?'As White: ':'As Black: ')+(entry.name||entry.line)}),
          h('p',{text:pct(entry.score_pct)+' score in '+entry.games+' games'+(entry.frequency_pct!=null?' · '+pct(entry.frequency_pct)+' of their games with this colour':'')}),
          h('p.muted',{text:entry.line}),
          evidence(entry.evidence)])]);
      output.append(section(mode.value==='opponent'?'Lines to prepare against':'Lines to review',[
        h('p',{text:report.suggested_line
          ?'Candidate to investigate: '+(report.suggested_line.name||report.suggested_line.line)+' ('+pct(report.suggested_line.score_pct)+' for '+report.player+' in '+report.suggested_line.games+' games). Check its soundness on the analysis board before trusting it.'
          :'No line has enough completed games for a preparation suggestion. Lower the minimum, or fetch more games.'}),
        ...report.weakest_lines.slice(0,5).map(lineCard)
      ]));

      /* ---------- recurring positions ---------- */
      output.append(section('Recurring positions',[
        h('p.muted',{text:'Score is wins plus half of draws. Bounds show uncertainty in each score; overlapping groups and small samples are not proof of a weakness.'}),
        table(['Pattern','Games','Score','95% bounds','Versus overall','Evidence'],report.patterns.map(p=>h('tr',[
          h('td',{text:p.theme+(p.small_sample?' · small sample':'')}),h('td',{text:p.games}),h('td',{text:pct(p.score_pct)}),h('td',{text:p.interval_pct?p.interval_pct.join('–')+'%':'—'}),h('td',{text:p.difference_pp==null?'—':p.difference_pp+' pp'}),h('td',[evidence(p.evidence)])])))
      ]));

      /* ---------- move quality and the clock ---------- */
      output.append(section('Move quality and the clock',[
        ...report.accuracy.map(a=>h('p',{text:a.phase+': '+a.mean_cp_loss+' average centipawns lost across '+a.moves+' evaluated moves'})),
        h('p',{text:report.clocks.low_time_moves+' moves ended with under 30 seconds remaining out of '+report.clocks.moves+' clock-tagged moves. Thinking time could be measured for '+report.clocks.measured_thinks+' moves.'}),
        ...report.clocks.longest_thinks.slice(0,5).map(m=>h('p.scout-think',[
          h('span',{text:'Move '+m.move+' '+m.san+': '+Math.round(m.spent)+' seconds · '}),
          h('button.linkish',{type:'button',text:label(m.game_id),
            onclick:async()=>{try{await openGame(m.game_id,m.ply);}catch(err){App.toast(err.message,5000);}}})])),
        ...(!report.accuracy.length?[h('p.muted',{text:'No saved evaluations in these games. Lichess exports carry them; for other sources, annotate games on the analysis board and save them.'})]:[])
      ]));

      /* ---------- practice ---------- */
      const practiceSection=section('Scheduled practice',[h('p.muted',{text:'Loading practice positions…'})]);
      output.append(practiceSection);
      practice().then(box=>practiceSection.replaceChildren(h('h2',{text:'Scheduled practice'}),box))
        .catch(err=>practiceSection.replaceChildren(h('h2',{text:'Scheduled practice'}),h('p.error-message',{text:err.message})));

      output.append(section('Mistakes to revisit',report.mistakes.length?report.mistakes.slice(0,8).map(m=>h('article.scout-line',[
        thumbnail(m.fen,{orientation:m.color,shapes:moveShape(m.fen,m.san),
          title:'Open this game at the move before '+m.san,onClick:()=>openGame(m.game_id,m.ply)}),
        h('div.scout-line-body',[
          h('h4',{text:'Move '+m.move+' '+m.san+' · '+m.loss+' centipawns lost'}),
          h('p.muted',{text:m.phase+' · the arrow is the move played'}),
          evidence([m.game_id]),
          h('div.toolbar',[button('Create practice position',async()=>{
            await api('scouting/drills',{player:activePlayer,game_id:m.game_id,ply:m.ply});
            practiceSection.replaceChildren(h('h2',{text:'Scheduled practice'}),await practice());
            App.toast('Practice position saved');})])])
      ])):[h('p.muted',{text:'No mistake could be measured: that needs games carrying saved evaluations for consecutive moves.'})]));

      output.append(section('How to read this report',report.notes.map(text=>h('p.muted',{text}))));
      output.append(h('article.scouting-print',[
        h('h1',{text:(mode.value==='opponent'?'Opponent prep: ':'My prep: ')+report.player}),
        h('p',{text:report.baseline.games+' completed games · '+pct(report.baseline.score_pct)+' score · '+(speed.value||'All time controls')+' · '+(since.value||'Any start date')+' to '+(until.value||'present')}),
        h('h2',{text:'Openings played'}),
        ...['w','b'].flatMap(color=>report.openings.filter(o=>o.color===color).slice(0,4).map(o=>h('p',{text:(color==='w'?'White: ':'Black: ')+(o.eco?o.eco+' ':'')+o.opening+' — '+o.games+' games, '+pct(o.frequency_pct)+' of that colour, '+pct(o.score_pct)+' score'}))),
        h('h2',{text:'Lines to investigate'}),
        ...(report.weakest_lines.length?report.weakest_lines.slice(0,3).map(l=>h('p',{text:(l.name||l.line)+' — '+pct(l.score_pct)+' for '+report.player+' in '+l.games+' games; moves '+l.line})):[h('p',{text:'No line meets the minimum sample.'})]),
        h('h2',{text:'Clock and mistakes'}),
        h('p',{text:report.clocks.low_time_moves+' moves ended under 30 seconds out of '+report.clocks.moves+' clock-tagged moves in '+report.clock_games+' games.'}),
        ...report.mistakes.slice(0,3).map(m=>h('p',{text:label(m.game_id)+', move '+m.move+' '+m.san+': '+m.loss+' centipawns lost ('+m.phase+').'})),
        h('p',{text:'Local game evidence only. Wins count 1, draws ½. Minimum line sample: '+report.minimum_games+'. Selection and rating differences affect scores. Check suggested lines with the engine; no theory or population benchmark is inferred.'})
      ]));
    }
    // The position a named opening reaches, replayed from its own moves.
    function startFen(moves){
      const game=new Chess();
      for(const san of (moves||[]).slice(0,12)){try{if(!game.move(san))break;}catch(err){break;}}
      return game.fen();
    }

    content.append(accountHint,h('div.filters',[field('Player',player),field('Report',mode),field('Games',source),
      field('Time control',speed),field('From (optional)',since),field('Through (optional)',until),
      field('Minimum games for a weak line',minimum),run]),fetchFields,output);
    player.addEventListener('keydown',e=>{if(e.key==='Enter')run.click();});
  };
})();

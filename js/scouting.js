/* Player reports and practice, using local game evidence. */
(function () {
  'use strict';
  window.ScoutingView = async function (content, ctx) {
    const {h, button, field, select, api, heading, openGame} = ctx;
    content.append(heading('Understand the player','Player lab','Find recurring patterns, prepare for an opponent, and retest mistakes from your games.'));
    const player=h('input',{placeholder:'Exact PGN name or online handle',value:''});
    // Scouting somebody else is the obvious use, so it leads; turning the same report
    // on yourself is the same machinery read the other way round and is explained as such.
    const mode=select([['opponent','Opponent prep'],['self','My prep']],'opponent');
    const source=select([['local','Local games'],['lichess','Import latest 100 from Lichess'],['chesscom','Import latest 100 from Chess.com']],'local');
    const accountHint=h('p.muted');
    const purpose=h('p.mode-purpose');
    const refreshAccount=CaissaAccount.fill(player,()=>mode.value==='self'&&source.value!=='chesscom');
    const drafts=new Map();let draftKey=mode.value+':'+source.value;
    function changeContext(){
      drafts.set(draftKey,player.value);
      draftKey=mode.value+':'+source.value;
      player.value=drafts.get(draftKey)||'';
      player.dispatchEvent(new Event('input'));
      refreshAccount();
      accountHint.textContent=mode.value==='opponent'
        ?'Enter the opponent name: exact PGN name or online handle. Scores in this report belong to the opponent.'
        :source.value==='chesscom'?'Enter your Chess.com handle. Your linked Lichess account is separate.'
        :'My prep fills in your linked Lichess username. For local PGNs, enter the exact White or Black name if it differs.';
      purpose.replaceChildren(h('b',{text:mode.value==='opponent'?'Preparing against someone: ':'Reviewing your own play: '}),
        h('span',{text:mode.value==='opponent'
          ?'the report is built from their games — what they open with as each colour, which lines they score worst in, and where their clock runs low. Every row lists the games behind it, so you can take a candidate line to the analysis board and prepare it.'
          :'the same report turned on yourself — the openings you actually play, the lines you lose in, the moves that cost the most centipawns, and the time trouble around them. Any mistake it finds can be saved as a practice position that comes back on a schedule until you play it right.'}));
    }
    mode.addEventListener('change',changeContext);source.addEventListener('change',changeContext);
    content.append(h('section.card.card-pad',[
      h('h2',{text:'Start here'}),
      h('p',{text:'The Player Lab replays one person’s games and reports what keeps happening in them. It reads games already in your library, or imports the latest 100 from Lichess or Chess.com first. Nothing is guessed: every figure links to the games it came from.'}),
      purpose,
      h('ol',[
        h('li',{text:'Name the player. Opponent prep wants their exact PGN name or online handle; My prep fills in your linked Lichess username by itself.'}),
        h('li',{text:'Choose Local games to use what you have already imported, or an online source to fetch the latest 100 public games when you press Build report.'}),
        h('li',{text:'Build report, then open any evidence game to see the pattern on the board. Low-scoring lines are where to aim preparation; in My prep, save a mistake as a practice position.'})
      ]),
      h('p.muted',{text:'Score means wins plus half of draws for the named player, whoever that is. Minimum games controls opening suggestions; start with 5. Move-quality and clock sections need games carrying saved evaluations and clock times. The rating lookup below is a separate search of indexed local games.'})
    ]));
    changeContext();
    const speed=select([['','All speeds'],['bullet','Bullet'],['blitz','Blitz'],['rapid','Rapid'],['classical','Classical']],'');
    const since=h('input',{type:'date'}), until=h('input',{type:'date'});
    const minimum=h('input',{type:'number',min:2,max:100,value:5});
    const output=h('div.scouting-report',{'aria-live':'polite'});
    const pct=n=>n==null?'No scored games':n+'%';
    const evidence=ids=>h('div.toolbar',ids.slice(0,6).map(id=>button('Game '+id,()=>openGame(id))));
    const section=(title,children)=>h('section.card.scouting-section',[h('h2',{text:title}),...children]);
    let activePlayer='';
    async function practice() {
      const {drills}=await api('scouting/drills?'+new URLSearchParams({player:activePlayer}));
      const box=h('div');
      box.append(h('p.muted',{text:'Submit a move in SAN (Nf3) or coordinates (g1f3). Success schedules retests at 1, 3, 9, 27, then 30 days. A miss returns tomorrow. These are engine best-move exercises, not claims that a weakness is fixed.'}));
      if(!drills.length)box.append(h('p',{text:'Create a practice position from a recorded mistake below. Stockfish must be installed.'}));
      for(const d of drills) {
        const due=d.due*1000<=Date.now();
        const row=h('article.scouting-drill',[h('h3',{text:d.theme+' · game '+d.game_id}),h('p',{text:d.successes+'/'+d.attempts+' successful reviews · '+(due?'Due now':'Retest '+new Date(d.due*1000).toLocaleDateString())})]);
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
    const humanFen=h('input',{value:Chess.DEFAULT_FEN}),low=h('input',{type:'number',value:1400,min:0,max:4000}),high=h('input',{type:'number',value:1800,min:0,max:4000});
    const humanResult=h('div',{'aria-live':'polite'});
    const human=section('What people at a rating actually play',[
      h('p.muted',{text:'Paste a position FEN and choose the mover’s rating range. Import games and index their collection in the Database first. These are observed local frequencies, not engine predictions.'}),
      field('Position FEN',humanFen),h('div.toolbar',[field('Minimum rating',low),field('Maximum rating',high),button('Find human moves',async()=>{
        const data=await api('scouting/human?'+new URLSearchParams({fen:humanFen.value,min_elo:low.value,max_elo:high.value}));
        humanResult.replaceChildren(h('p',{text:data.games+' matching indexed games'}),...data.moves.map(m=>h('p',{text:m.san+' · '+m.frequency_pct+'% played · '+m.observations+' games · White score '+pct(m.white_score.score_pct)})),h('p.muted',{text:data.note}));
      })]),humanResult]);
    const run=button('Build report',async()=>{
      if(!player.value.trim())throw new Error('Enter the exact player name or handle.');
      run.disabled=true;output.replaceChildren(h('p',{role:'status',text:'Reading games and building evidence…'}));
      try {
        activePlayer=player.value.trim();sessionStorage.setItem('caissa-scout-player',activePlayer);
        if(source.value!=='local')await api('import/'+source.value,{user:activePlayer,max:100,collection:'Prep: '+activePlayer});
        const report=await api('scouting?'+new URLSearchParams({player:activePlayer,speed:speed.value,since:since.value,until:until.value,min_games:minimum.value}));
        if(!output.isConnected)return;
        output.replaceChildren(section((mode.value==='opponent'?'Opponent prep: ':'Scouting report: ')+report.player,[
          h('p',{text:report.baseline.games+' completed games · '+pct(report.baseline.score_pct)+' score · '+report.evaluated_games+' games with usable evaluations · '+report.clock_games+' games with clocks'}),
          h('p.muted',{text:report.analyzed_games+' games replayed; '+report.skipped.length+' skipped. Minimum sample: '+report.minimum_games+' games.'}),
          ...(!report.analyzed_games?[h('p',{text:'No matching games. Names match exactly, ignoring case. Import games or check the name in your database.'})]:[])
        ]));
        const table=(headers,rows)=>h('div.table-scroll',[h('table',[h('thead',[h('tr',headers.map(text=>h('th',{scope:'col',text})))]),h('tbody',rows)])]);
        output.append(section('Recurring positions',[
          h('p.muted',{text:'Score is wins plus half of draws. Bounds show uncertainty in each score; overlapping groups and small samples are not proof of a weakness.'}),
          table(['Pattern','Games','Score','95% bounds','Versus overall','Evidence'],report.patterns.map(p=>h('tr',[
            h('td',{text:p.theme+(p.small_sample?' · small sample':'')}),h('td',{text:p.games}),h('td',{text:pct(p.score_pct)}),h('td',{text:p.interval_pct?p.interval_pct.join('–')+'%':'—'}),h('td',{text:p.difference_pp==null?'—':p.difference_pp+' pp'}),h('td',[evidence(p.evidence)])])))
        ]));
        const lines=report.weakest_lines;
        output.append(section(mode.value==='opponent'?'Opponent preparation':'Openings to review',[
          h('p',{text:report.suggested_line?'Candidate to investigate: '+report.suggested_line.line+' ('+pct(report.suggested_line.score_pct)+' selected-player score, '+report.suggested_line.games+' games). Check its soundness on the analysis board.':'No line has enough completed games for a preparation suggestion.'}),
          ...lines.map(l=>h('article',[h('p',{text:(l.color==='w'?'As White: ':'As Black: ')+l.line+' · '+pct(l.score_pct)+' score in '+l.games+' games'}),evidence(l.evidence)])),
          h('h3',{text:'Frequently played lines'}),
          ...report.repertoire.slice(0,16).map(l=>h('p',{text:(l.color==='w'?'White: ':'Black: ')+l.line+' · '+l.games+' games · '+pct(l.frequency_pct)+' of completed games in this colour'}))
        ]));
        output.append(section('Move quality and the clock',[
          ...report.accuracy.map(a=>h('p',{text:a.phase+': '+a.mean_cp_loss+' average centipawns lost across '+a.moves+' evaluated moves'})),
          h('p',{text:report.clocks.low_time_moves+' moves ended with under 30 seconds remaining out of '+report.clocks.moves+' clock-tagged moves. Thinking time could be measured for '+report.clocks.measured_thinks+' moves.'}),
          ...report.clocks.longest_thinks.slice(0,5).map(m=>h('p',[h('span',{text:'Move '+m.move+' '+m.san+': '+Math.round(m.spent)+' seconds · '}),button('Game '+m.game_id,()=>openGame(m.game_id))])),
          ...(!report.accuracy.length?[h('p.muted',{text:'Annotate games on the analysis board and save them to enable move-quality patterns.'})]:[])
        ]));
        const practiceSection=section('Scheduled practice',[await practice()]);output.append(practiceSection);
        output.append(section('Mistakes to revisit',report.mistakes.slice(0,20).map(m=>h('article.scouting-drill',[
          h('p',{text:'Game '+m.game_id+' · move '+m.move+' '+m.san+' · '+m.loss+' centipawns lost · '+m.phase}),
          evidence([m.game_id]),button('Create practice position',async()=>{await api('scouting/drills',{player:activePlayer,game_id:m.game_id,ply:m.ply});practiceSection.replaceChildren(h('h2',{text:'Scheduled practice'}),await practice());App.toast('Practice position saved');})
        ]))));
        output.append(section('How to read this report',report.notes.map(text=>h('p.muted',{text}))));
        output.append(h('article.scouting-print',[
          h('h1',{text:(mode.value==='opponent'?'Opponent prep: ':'My prep: ')+report.player}),
          h('p',{text:report.baseline.games+' completed games · '+pct(report.baseline.score_pct)+' score · '+(speed.value||'All speeds')+' · '+(since.value||'Any start date')+' to '+(until.value||'present')}),
          h('h2',{text:'Repertoire'}),
          ...['w','b'].flatMap(color=>report.repertoire.filter(l=>l.color===color).slice(0,3).map(l=>h('p',{text:(color==='w'?'White: ':'Black: ')+l.line+' — '+l.games+' games, '+pct(l.score_pct)+' score'}))),
          h('h2',{text:'Lines to investigate'}),
          ...(report.weakest_lines.length?report.weakest_lines.slice(0,3).map(l=>h('p',{text:l.line+' — '+pct(l.score_pct)+' selected-player score in '+l.games+' games; evidence IDs '+l.evidence.slice(0,3).join(', ')})):[h('p',{text:'No line meets the minimum sample.'})]),
          h('h2',{text:'Clock and mistakes'}),
          h('p',{text:report.clocks.low_time_moves+' moves ended under 30 seconds out of '+report.clocks.moves+' clock-tagged moves in '+report.clock_games+' games.'}),
          ...report.mistakes.slice(0,3).map(m=>h('p',{text:'Game '+m.game_id+', move '+m.move+' '+m.san+': '+m.loss+' centipawns lost ('+m.phase+').'})),
          h('p',{text:'Local game evidence only. Wins count 1, draws ½. Minimum line sample: '+report.minimum_games+'. Selection and rating differences affect scores. Check suggested lines with the engine; no theory or population benchmark is inferred.'})
        ]));
        output.append(button('Print prep sheet',()=>window.print()));
      }catch(err){output.replaceChildren(h('p',{role:'alert',text:err.message}));throw err;}
      finally{run.disabled=false;}
    },'primary');
    content.append(accountHint,h('div.filters',[field('Player',player),field('Report',mode),field('Games',source),field('Speed',speed),field('From',since),field('Through',until),field('Minimum games',minimum),run]),output,human);
    player.addEventListener('keydown',e=>{if(e.key==='Enter')run.click();});
  };
})();

/* Move sounds.

   Three kinds of set, in order of preference:

   * **Bundled samples** in assets/sound/<set>/<event>.mp3, fetched by
     tools/fetch_sounds.py. The lichess sets ship with the app; chess.com's are
     downloaded on the user's own machine and are not redistributed, so the set
     list is read from the server rather than hard-coded here.
   * **Caissa presets** (wood, digital), synthesized with an oscillator. They need
     no files at all, which is what makes them the safe default.
   * **Your own files**, kept in library preferences as data URLs.

   No set has a sound for every event: lichess plays nothing for check in its
   standard set and has no castle sample anywhere. Rather than go silent, a missing
   sample falls back to the standard lichess set and then to the synthesized preset,
   so every event makes some sound. */
(function(){
  let context,prefs={},catalog=null,catalogRequest=null;
  const events=['start','move','opponent','capture','castle','check','promotion','end',
                'illegal','notify','lowtime','premove'];
  const EVENT_LABELS={start:'Game start',move:'Your move',opponent:'Opponent move',
    capture:'Capture',castle:'Castling',check:'Check',promotion:'Promotion',end:'Game end',
    illegal:'Illegal move',notify:'Notification',lowtime:'Low time',premove:'Pre-move'};
  const SYNTH=['wood','digital'];
  const cache=new Map();

  function eventFor(move,mine){
    if(!move)return mine===false?'opponent':'move';
    if(move.san?.endsWith('#'))return 'end';
    if(move.san?.endsWith('+'))return 'check';
    if(move.promotion)return 'promotion';
    if(/^O-O/.test(move.san||''))return 'castle';
    if(move.captured)return 'capture';
    return mine===false?'opponent':'move';
  }

  /* Which sets are actually installed. chess.com's are optional, so the answer
     comes from the server rather than from a list baked in here. */
  async function sets(){
    if(catalog)return catalog;
    if(!catalogRequest)catalogRequest=fetch('/api/sounds').then(r=>r.ok?r.json():{sets:[]})
      .then(data=>{catalog=data.sets||[];return catalog;})
      .catch(()=>{catalog=[];return catalog;});
    return catalogRequest;
  }

  function installed(name){return (catalog||[]).find(s=>s.name===name);}

  /* A sample for this event: your own file, then the chosen set, then lichess
     standard, then any installed set that has one. Lichess's standard set really is
     silent for check and checkmate, so stopping at it would leave those two events
     with no sound at all on the set most people will pick. */
  function sampleFor(pack,event){
    const custom=prefs.soundFiles?.[pack]?.[event];
    if(custom)return custom;
    const order=[installed(pack),installed('standard'),...(catalog||[])];
    for(const set of order)
      if(set&&set.events.includes(event))return '/assets/sound/'+set.name+'/'+event+'.mp3';
    return null;
  }

  function synthesize(pack,event,volume){
    context=context||new AudioContext();
    const notes={start:[330,440],move:[260],opponent:[240],capture:[180,100],castle:[260,330],
      check:[660,880],promotion:[440,660,880],end:[660,520,390],illegal:[110,90],
      notify:[880,660],lowtime:[880,880],premove:[300]}[event]||[260];
    return context.resume().then(()=>{
      notes.forEach((hz,i)=>{const osc=context.createOscillator(),gain=context.createGain(),at=context.currentTime+i*.09;
        osc.type=pack==='digital'?'sine':'triangle';
        osc.frequency.setValueAtTime(hz,at);osc.frequency.exponentialRampToValueAtTime(hz*.65,at+.09);
        gain.gain.setValueAtTime(Math.max(.001,volume*.35),at);gain.gain.exponentialRampToValueAtTime(.001,at+.12);
        osc.connect(gain).connect(context.destination);osc.start(at);osc.stop(at+.13);});
    });
  }

  async function play(event,preview=false){
    const pack=prefs.soundPack||'off';
    if(pack==='off'&&!preview)return;
    if(prefs.soundEvents?.[event]===false&&!preview)return;
    const volume=Number(prefs.soundVolume??0.45);
    if(volume<=0)return;
    if(pack!=='off'&&!SYNTH.includes(pack))await sets();
    const sample=SYNTH.includes(pack)?prefs.soundFiles?.[pack]?.[event]:sampleFor(pack,event);
    if(sample){
      // One Audio element per sample, cloned per play so quick moves overlap cleanly.
      let base=cache.get(sample);
      if(!base){base=new Audio(sample);base.preload='auto';cache.set(sample,base);}
      const audio=base.cloneNode();
      audio.volume=volume;
      try{await audio.play();return;}catch(err){/* fall through to the synthesized sound */}
    }
    await synthesize(SYNTH.includes(pack)?pack:'wood',event,volume);
  }

  function settings(ui,preferences,save){
    const {h,field,select,button}=ui;prefs=preferences;
    const pack=select([['off','Off'],['wood','Caissa wood (synthesized)'],['digital','Caissa digital (synthesized)']],prefs.soundPack||'off');
    const volume=h('input',{type:'range',min:0,max:1,step:.05,value:prefs.soundVolume??.45});
    const list=h('div');
    const note=h('p.muted',{text:'Caissa’s two presets are synthesized and always available. Sample sets are bundled with the app.'});
    const root=h('section.card.card-pad',[h('h2',{text:'Move sounds'}),field('Sound set',pack),
      field('Sound volume',volume),note,list]);

    sets().then(available=>{
      const bundled=available.filter(s=>s.name!=='chesscom');
      const chesscom=available.find(s=>s.name==='chesscom');
      for(const set of bundled)pack.append(h('option',{value:set.name,text:set.label}));
      if(chesscom)pack.append(h('option',{value:'chesscom',text:chesscom.label}));
      pack.append(h('option',{value:'custom',text:'My own audio files'}));
      pack.value=prefs.soundPack||'off';
      if(pack.value!==(prefs.soundPack||'off'))pack.value='off';
      note.textContent=available.length
        ?'Caissa’s two presets are synthesized. '+bundled.length+' sample sets are bundled from lichess'
          +(chesscom?', and the chess.com set you downloaded is available too.':'. Run "py tools/fetch_sounds.py --chesscom" to add the chess.com set to this machine.')
          +' An event a set has no sample for falls back to the lichess standard sound.'
        :'No sample sets are installed. Run "py tools/fetch_sounds.py" to bundle the lichess sets, and add --chesscom for the chess.com set.';
      render();
    });

    function render(){
      list.replaceChildren();
      const custom=pack.value==='custom';
      for(const event of events){
        const enabled=h('input',{type:'checkbox',checked:prefs.soundEvents?.[event]!==false,
          onchange:async()=>{prefs.soundEvents={...prefs.soundEvents,[event]:enabled.checked};await save();}});
        const row=h('div.sound-row',[field(EVENT_LABELS[event]||event,enabled),button('Preview',()=>play(event,true))]);
        const set=installed(pack.value);
        if(set&&!set.events.includes(event)){
          const source=sampleFor(pack.value,event);
          row.append(h('small.muted',{text:source?'Borrowed from the '+source.split('/')[3]+' set':'Synthesized'}));
        }
        if(custom||SYNTH.includes(pack.value)){
          const file=h('input',{type:'file',accept:'audio/*','aria-label':'Sound file for '+event});
          file.addEventListener('change',async()=>{const f=file.files[0],chosen=pack.value;if(!f)return;
            if(f.size>1024*1024){App.toast('Use a sound file smaller than 1 MB');return;}
            const reader=new FileReader();
            reader.onload=async()=>{prefs.soundFiles=prefs.soundFiles||{};
              prefs.soundFiles[chosen]={...prefs.soundFiles[chosen],[event]:reader.result};
              cache.clear();await save();render();};
            reader.readAsDataURL(f);});
          row.append(file,h('small',{text:prefs.soundFiles?.[pack.value]?.[event]?'Your own sample is saved':'Optional: replace this sound'}));
        }
        list.append(row);
      }
    }
    pack.addEventListener('change',async()=>{prefs.soundPack=pack.value;cache.clear();await save();render();});
    volume.addEventListener('change',async()=>{prefs.soundVolume=Number(volume.value);await save();});
    render();
    return root;
  }

  window.ChessSounds={configure(p){prefs=p;cache.clear();},play,eventFor,settings,sets,events,sampleFor};
})();

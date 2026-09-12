/* Original synthesized sounds; user-provided samples stay in library preferences. */
(function(){
  let context,prefs={};
  const events=['move','capture','castle','check','promotion','end','illegal'];
  function eventFor(move){return move?.san?.endsWith('#')?'end':move?.san?.endsWith('+')?'check':move?.promotion?'promotion':/^O-O/.test(move?.san||'')?'castle':move?.captured?'capture':'move';}
  async function play(event,preview=false){
    const pack=prefs.soundPack||'off';if(pack==='off'&&!preview)return;
    if(prefs.soundEvents?.[event]===false&&!preview)return;
    const volume=Number(prefs.soundVolume??0.45);
    if(volume<=0)return;
    const sample=prefs.soundFiles?.[pack]?.[event];
    if(sample){const audio=new Audio(sample);audio.volume=volume;await audio.play();return;}
    if(!['off','wood','digital'].includes(pack)){if(preview)throw new Error('Choose an audio file for '+event+' first.');return;}
    context=context||new AudioContext();await context.resume();
    const notes={move:[260],capture:[180,100],castle:[260,330],check:[660,880],promotion:[440,660,880],end:[660,520,390],illegal:[110,90]}[event]||[260];
    notes.forEach((hz,i)=>{const osc=context.createOscillator(),gain=context.createGain(),at=context.currentTime+i*.09;osc.type=pack==='digital'?'sine':'triangle';osc.frequency.setValueAtTime(hz,at);osc.frequency.exponentialRampToValueAtTime(hz*.65,at+.09);gain.gain.setValueAtTime(Math.max(.001,volume*.35),at);gain.gain.exponentialRampToValueAtTime(.001,at+.12);osc.connect(gain).connect(context.destination);osc.start(at);osc.stop(at+.13);});
  }
  function settings(ui,preferences,save){
    const {h,field,select,button}=ui;prefs=preferences;
    const pack=select([['off','Off'],['wood','Caissa wood'],['digital','Caissa digital'],['lichess','Lichess — your sound files'],['chesscom','Chess.com — your sound files'],['chessbase','ChessBase — your sound files'],['custom','Custom files']],prefs.soundPack||'off');
    const volume=h('input',{type:'range',min:0,max:1,step:.05,value:prefs.soundVolume??.45});
    const list=h('div');
    const root=h('section.card.card-pad',[h('h2',{text:'Move sounds'}),field('Sound set',pack),field('Sound volume',volume),h('p.muted',{text:'Caissa presets are included. Other profiles use audio files you select below; commercial sound packs are not bundled. Files are copied into your library preferences. Each event can be switched off.'}),list]);
    function render(){list.replaceChildren();for(const event of events){
      const enabled=h('input',{type:'checkbox',checked:prefs.soundEvents?.[event]!==false,onchange:async()=>{prefs.soundEvents={...prefs.soundEvents,[event]:enabled.checked};await save();}});
      const row=h('div.sound-row',[field(event[0].toUpperCase()+event.slice(1),enabled),button('Preview '+event,()=>play(event,true))]);
      if(!['off','wood','digital'].includes(pack.value)){
        const file=h('input',{type:'file',accept:'audio/*','aria-label':'Sound file for '+event});
        file.addEventListener('change',async()=>{const f=file.files[0],selectedPack=pack.value;if(!f)return;if(f.size>1024*1024){App.toast('Use a sound file smaller than 1 MB');return;}const reader=new FileReader();reader.onload=async()=>{prefs.soundFiles=prefs.soundFiles||{};prefs.soundFiles[selectedPack]={...prefs.soundFiles[selectedPack],[event]:reader.result};await save();render();};reader.readAsDataURL(f);});
        row.append(file,h('small',{text:prefs.soundFiles?.[pack.value]?.[event]?'Custom sample saved':'Choose a sample for this event'}));
      }list.append(row);
    }}
    pack.addEventListener('change',async()=>{prefs.soundPack=pack.value;await save();render();});
    volume.addEventListener('change',async()=>{prefs.soundVolume=Number(volume.value);await save();});render();return root;
  }
  window.ChessSounds={configure(p){prefs=p;},play,eventFor,settings};
})();

/* Window-level progress for imports and indexing, independent of the current view. */
(function () {
  'use strict';
  const jobs=new Map();
  let host;
  const routes={import:'import/status',index:'study/index'};
  function job(kind){
    if(!jobs.has(kind))jobs.set(kind,{kind,pending:0,revision:0,seen:false,timer:null,polling:false});
    return jobs.get(kind);
  }
  function show(j,s){
    if(!host){host=App.h('aside.job-progress',{'aria-label':'Background tasks'});document.body.append(host);}
    if(!j.card){
      j.title=App.h('strong');j.note=App.h('small',{role:'status'});
      j.bar=App.h('progress',{max:100,value:0,'aria-label':j.kind==='index'?'Indexing progress':'Import progress'});
      j.close=App.h('button',{type:'button',text:'×','aria-label':'Dismiss task notification',onclick:()=>{j.card.remove();j.card=null;}});
      j.card=App.h('section.job-progress-card',{'data-job':j.kind},[App.h('div.job-progress-heading',[j.title,j.close]),j.bar,j.note]);host.append(j.card);
    }
    clearTimeout(j.dismiss);
    const finished=!s.running;
    const done=Math.max(0,Number(s.done)||0),total=Math.max(0,Number(s.total)||0);
    const percent=total?Math.min(100,Math.floor(done/total*100)):0;
    const name=j.kind==='index'?'Indexing':'Importing';
    j.title.textContent=(finished?(s.error?name+' failed':j.kind==='index'?'Indexing complete':'Import complete'):name)+' · '+(s.collection||s.label||'Your library');
    j.close.hidden=!finished;
    j.bar.hidden=!!s.error||(!finished&&!total);
    j.bar.value=finished?100:percent;
    j.card.dataset.state=s.error?'error':finished?'complete':total?'progress':'waiting';
    if(s.error)j.note.textContent=s.error;
    else if(finished)j.note.textContent=j.kind==='index'?(done?done.toLocaleString()+' games processed'+(s.errors?' · '+s.errors+' could not be indexed':''):'All games are already indexed.'):
      (s.added||0).toLocaleString()+' added · '+(s.duplicates||0).toLocaleString()+' duplicates'+(s.skipped?' · '+s.skipped+' skipped':'');
    else if(total)j.note.textContent=done.toLocaleString()+' of '+total.toLocaleString()+' games · '+percent+'%'+(done>=total?' · Saving results…':'');
    else j.note.textContent=j.kind==='index'?'Counting games to index…':done?done.toLocaleString()+' games processed · Still receiving games; total not yet known.':'Fetching games… Progress will appear when the game count is known.';
    if(finished&&!s.error)j.dismiss=setTimeout(()=>{if(j.card){j.card.remove();j.card=null;}},8000);
  }
  function schedule(j){clearTimeout(j.timer);j.timer=setTimeout(()=>poll(j),700);}
  async function poll(j){
    if(j.polling)return;
    j.polling=true;
    const revision=j.revision;
    try{
      const response=await fetch('/api/'+routes[j.kind]);
      if(!response.ok)throw new Error('Could not check task progress');
      const s=await response.json();
      if(revision!==j.revision)return;
      if(s.running){j.seen=true;show(j,s);schedule(j);}
      else if(j.pending){schedule(j);}
      else if(j.seen){j.seen=false;show(j,s);window.dispatchEvent(new CustomEvent('caissa-task-complete',{detail:{kind:j.kind,status:s}}));}
    }catch(err){
      if(j.card){j.note.textContent='Progress connection interrupted. Retrying…';schedule(j);}
    }finally{j.polling=false;if(revision!==j.revision&&j.seen)schedule(j);}
  }
  window.JobProgress={
    watch(kind){poll(job(kind));},
    begin(kind,label){const j=job(kind);j.revision++;j.pending++;j.seen=true;show(j,{running:true,label});schedule(j);},
    end(kind,data,error){
      const j=job(kind);j.revision++;j.pending=Math.max(0,j.pending-1);
      if(error){j.seen=false;show(j,{running:false,error:error.message});return;}
      if(kind==='import'){j.seen=false;show(j,{...data,running:false});}
      else {j.seen=true;show(j,data);schedule(j);}
    }
  };
})();

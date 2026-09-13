/* Shared, keyboard-accessible suggestions backed by the existing local catalogs. */
(function () {
  let serial=0;const attached=new Map();
  function attach(input) {
    const source=input.getAttribute('list');
    if(!source||input.dataset.suggestions)return;
    input.dataset.suggestions=source;input.removeAttribute('list');input.autocomplete='off';
    input.setAttribute('role','combobox');input.setAttribute('aria-autocomplete','list');
    input.setAttribute('aria-expanded','false');
    const popup=document.createElement('div');popup.className='suggestions';popup.id='suggestions-'+(++serial);
    popup.setAttribute('role','listbox');popup.hidden=true;(input.closest('dialog')||document.body).append(popup);
    input.setAttribute('aria-controls',popup.id);
    let active=-1,options=[],chosen=false;
    function close(){popup.hidden=true;input.setAttribute('aria-expanded','false');input.removeAttribute('aria-activedescendant');}
    function choose(i){if(!options[i])return;input.value=options[i].value;input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));chosen=true;close();}
    function highlight(i){active=i;[...popup.children].forEach((el,n)=>{el.setAttribute('aria-selected',String(n===i));});if(popup.children[i]){input.setAttribute('aria-activedescendant',popup.children[i].id);popup.children[i].scrollIntoView({block:'nearest'});}}
    function show(){
      if(document.activeElement!==input||chosen)return;
      options=[...(document.getElementById(source)?.options||[])].filter(o=>o.value.toLowerCase().includes(input.value.toLowerCase())).slice(0,12);
      popup.replaceChildren();active=-1;
      options.forEach((o,i)=>{const row=document.createElement('div');row.id=popup.id+'-'+i;row.setAttribute('role','option');row.setAttribute('aria-selected','false');
        const name=document.createElement('strong');name.textContent=o.value;row.append(name);
        if(o.label&&o.label!==o.value){const detail=document.createElement('small');detail.textContent=o.label;row.append(detail);}
        row.addEventListener('pointerdown',e=>{e.preventDefault();choose(i);});popup.append(row);});
      const rect=input.getBoundingClientRect();popup.style.left=rect.left+'px';popup.style.top=rect.bottom+5+'px';popup.style.width=rect.width+'px';
      popup.hidden=!options.length;input.setAttribute('aria-expanded',String(!!options.length));
    }
    const refresh=()=>{chosen=false;show();};
    input.addEventListener('focus',refresh);input.addEventListener('input',refresh);input.addEventListener('blur',close);
    input.addEventListener('keydown',e=>{
      if(e.key==='Escape'){close();return;}
      if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();chosen=false;if(popup.hidden)show();highlight(Math.max(0,Math.min(options.length-1,active+(e.key==='ArrowDown'?1:-1))));}
      if(e.key==='Enter'&&!popup.hidden&&active>=0){e.preventDefault();e.stopPropagation();choose(active);}
    });
    const watch=new MutationObserver(show);
    const sourceList=document.getElementById(source);
    if(sourceList)watch.observe(sourceList,{childList:true});
    attached.set(input,()=>{watch.disconnect();popup.remove();});
  }
  new MutationObserver(()=>{
    document.querySelectorAll('input[list]').forEach(attach);
    for(const [input,dispose] of attached)if(!input.isConnected){dispose();attached.delete(input);}
  }).observe(document.documentElement,{childList:true,subtree:true});
  document.addEventListener('scroll',e=>{if(e.target.closest?.('.suggestions'))return;document.querySelectorAll('input[role=combobox]').forEach(i=>{i.setAttribute('aria-expanded','false');const p=document.getElementById(i.getAttribute('aria-controls'));if(p)p.hidden=true;});},true);
})();

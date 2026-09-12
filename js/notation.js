/* Ordered variation trees, with notes inside score-sheet cells. */
(function(){
  const folded=new WeakMap();
  window.Notation={render({h,root,current,jump,rows,nags,evalLabel,contextMenu}){
    const view=h('div.notation-lines'),path=new Set(PGN.pathTo(current));
    function cell(node,prefix){
      const score=evalLabel(node.eval),drawings=node.shapes||[];
      const move=h('button'+(node===current?'.current':''),{type:'button',text:prefix+node.san+nags(node),onclick:()=>jump(node),'aria-current':node===current?'step':'false'});
      move.addEventListener('contextmenu',event=>{event.preventDefault();contextMenu(node);});
      const item=h('span.move-cell',[h('span.move-token',[move,score?h('small.move-eval',{text:score,title:'Stored evaluation, White perspective'}):null])]);
      if(drawings.length)item.append(h('span.move-drawings',drawings.map(s=>h('span',{text:s.square?'○ '+s.square:'↗ '+s.from+'–'+s.to,style:{color:'var(--shape-'+s.brand+')'},title:s.brand+' '+(s.square?'circle':'arrow')}))));
      if(node.comment)item.append(h('span.move-note',{text:node.comment}));
      return item;
    }
    function line(start,target,depth=0){
      let node=start,row=null,number=null,previousWhite=false;
      while(node){
        const fields=node.parent.fenAfter.split(' '),white=fields[1]==='w',num=fields[5];
        if(rows){
          if(white||!row||num!==number){row=h('div.move-row',[h('span.move-no',{text:num+'.'})]);number=num;target.append(row);if(!white)row.append(h('span.move-skip',{text:'…'}));}
          row.append(cell(node,''));
        }else target.append(cell(node,white?num+'. ':previousWhite?'':num+'… '));
        previousWhite=white;
        if(node===node.parent.children[0])for(const alt of node.parent.children.slice(1)){
          const details=h('details.variation',{open:path.has(alt)||(folded.has(alt)?!folded.get(alt):depth===0)}),branch=h('div.variation-line');
          details.append(h('summary',{text:'Alternative '+num+(white?'. ':'… ')+alt.san}),branch);
          details.firstChild.addEventListener('contextmenu',event=>{event.preventDefault();contextMenu(alt);});
          details.addEventListener('toggle',()=>folded.set(alt,!details.open));
          line(alt,branch,depth+1);target.append(details);row=null;previousWhite=false;
        }
        node=node.children[0];
      }
    }
    if(root.comment)view.append(h('p.move-note',{text:root.comment}));
    if(root.shapes?.length)view.append(h('p.move-drawings',{text:'Starting position drawings: '+root.shapes.map(s=>s.square||s.from+'–'+s.to).join(', ')}));
    if(root.children.length)line(root.children[0],view);
    return view;
  }};
})();

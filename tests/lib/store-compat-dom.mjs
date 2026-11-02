// Read-only observations/element resolution for normal mouse input in tests.
export function storeAddControl(returnElement=false) {
  const short=value=>String(value??'').trim().replace(/\s+/g,' ').slice(0,240);
  const elements=[...document.querySelectorAll('button,[role="button"]')].filter(element=>/^add to (chrome|chromium)$/i.test(short(element.getAttribute('aria-label')||element.innerText||element.textContent)));
  if(returnElement)return elements.length===1?elements[0]:null;
  const candidates=elements.slice(0,8).map(element=>{
    const rect=element.getBoundingClientRect(),style=getComputedStyle(element),x=rect.x+rect.width/2,y=rect.y+rect.height/2,hit=document.elementFromPoint(x,y);
    return {label:short(element.getAttribute('aria-label')||element.innerText||element.textContent),enabled:!element.matches(':disabled')&&!element.hasAttribute('disabled')&&element.getAttribute('aria-disabled')!=='true',
      visible:rect.width>0&&rect.height>0&&style.display!=='none'&&style.visibility!=='hidden'&&Number(style.opacity)>0,pointerEvents:style.pointerEvents,
      x,y,insideViewport:x>=0&&y>=0&&x<innerWidth&&y<innerHeight,hitTargetMatches:hit===element||element.contains(hit),rect:{left:rect.left,top:rect.top,width:rect.width,height:rect.height}};
  });
  return {url:location.href,title:short(document.title),readyState:document.readyState,count:elements.length,candidates,viewport:{width:innerWidth,height:innerHeight},scroll:{x:scrollX,y:scrollY,width:document.scrollingElement?.scrollWidth,height:document.scrollingElement?.scrollHeight}};
}

export function extensionRemoveControl(expectedId,expectedName,returnElement=false) {
  const short=value=>String(value??'').trim().replace(/\s+/g,' ').slice(0,240);
  let visited=0,truncated=false;
  const walk=root=>{
    const found=[],queue=[{root,depth:0}];
    while(queue.length&&visited<3000){
      const {root:current,depth}=queue.shift();
      for(const element of current.querySelectorAll('*')){
        visited++;if(visited>3000){truncated=true;break;}found.push(element);
        if(element.shadowRoot){if(depth<12)queue.push({root:element.shadowRoot,depth:depth+1});else truncated=true;}
      }
    }
    if(queue.length)truncated=true;return found;
  };
  const items=walk(document).filter(element=>element.localName==='extensions-item'&&(element.id===expectedId||element.getAttribute('id')===expectedId||element.data?.id===expectedId));
  const item=items.length===1?items[0]:null;
  const name=item?short(item.shadowRoot?.querySelector('#name')?.textContent??item.data?.name):null;
  const buttons=item&&name===expectedName?walk(item.shadowRoot??item).filter(element=>['button','cr-button'].includes(element.localName)&&short(element.innerText||element.textContent||element.getAttribute('aria-label'))==='Remove'):[];
  if(returnElement)return !truncated&&items.length===1&&buttons.length===1?buttons[0]:null;
  const candidates=buttons.slice(0,8).map(element=>{
    const rect=element.getBoundingClientRect(),style=getComputedStyle(element),x=rect.x+rect.width/2,y=rect.y+rect.height/2;
    let hit=document.elementFromPoint(x,y);for(let depth=0;depth<16&&hit?.shadowRoot;depth++){const next=hit.shadowRoot.elementFromPoint(x,y);if(!next||next===hit)break;hit=next;}
    let matches=false;for(let node=hit,depth=0;node&&depth<24;depth++){if(node===element){matches=true;break;}node=node.parentNode??node.getRootNode?.().host??null;}
    return {label:'Remove',enabled:element.disabled!==true&&!element.hasAttribute('disabled')&&element.getAttribute('aria-disabled')!=='true',
      visible:rect.width>0&&rect.height>0&&style.display!=='none'&&style.visibility!=='hidden'&&Number(style.opacity)>0,pointerEvents:style.pointerEvents,
      x,y,insideViewport:x>=0&&y>=0&&x<innerWidth&&y<innerHeight,hitTargetMatches:matches,rect:{left:rect.left,top:rect.top,width:rect.width,height:rect.height}};
  });
  return {url:location.href,readyState:document.readyState,targetId:expectedId,targetName:name,itemCount:items.length,count:buttons.length,candidates,truncated,visited,viewport:{width:innerWidth,height:innerHeight},scroll:{x:scrollX,y:scrollY}};
}

#!/usr/bin/env node
// Inspect the real normal Store permission dialog; NEVER accept installation.
import { mkdir, readFile, writeFile, stat } from 'node:fs/promises';
import path from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { launchOwnedStoreBrowser, probeOwnedStoreUi, storeOperation } from './lib/owned-store-browser.mjs';
import { DEFAULT_STORE_TARGET, getStoreTarget, matchesStoreTargetUrl } from './lib/store-targets.mjs';

const options={browser:process.env.CHROME_PATH,output:null,target:DEFAULT_STORE_TARGET};
for(let i=2;i<process.argv.length;i++) {
  const key=process.argv[i].replace(/^--/,'');
  if(!Object.hasOwn(options,key)||!process.argv[i+1])throw Error(`Unknown/missing argument: ${process.argv[i]}`);
  options[key]=process.argv[++i];
}
if(!options.browser||!options.output)throw Error('Usage: node tests/store-dialog.mjs --browser PATH --output NEW_DIR [--target always-active|ubol]');
const target=getStoreTarget(options.target);
options.output=path.resolve(options.output);
await mkdir(path.dirname(options.output),{recursive:true});await mkdir(options.output,{mode:0o700});
const overallDeadline=Date.now()+180000;
const abort=new AbortController();let interrupted=null;
process.once('SIGINT',()=>{interrupted='SIGINT';abort.abort();});
process.once('SIGTERM',()=>{interrupted='SIGTERM';abort.abort();});
const report={schema:1,stage:'normal-store-dialog-inspection-NO-INSTALL-ACCEPTANCE',started:new Date().toISOString(),platform:process.platform,architecture:process.arch,target,
  tests:[],observations:{},inputEvents:[],installation:{addClickAttempted:false,addClicked:false,accepted:false,acceptInteractionPerformed:false,successfulInstallVerified:false,targetInstalledObserved:null},
  update:{checkAttempted:false,checkCompleted:false,result:null,versionTransitionVerified:false},
  permissionTextPolicy:'Capture actual text from the verified selected-target native prompt; no target-specific permission phrase is presumed.',
  limits:{actionBudgetMs:180000,cleanupBudgetMs:18000,listingMs:60000,scrollAttemptMs:7000,maxScrollAttempts:1,dialogMs:45000,nativeUiProbeMs:15000,maxDialogProbes:4,dialogProbeScheduledOffsetsMs:[500,10000,20000,30000],maxNativeUiBytes:65536,maxProfilePreferenceBytes:8388608,maxCandidateRecords:8,maxTextLength:240},
  limitations:[
    'This is an inspection of the real permission UI, not a completed extension install/restart/update/removal gate.',
    'Only CDP Input mouse events may click the actual enabled Store Add button; no element.click, private install API, auto-confirm, security bypass, extension load, or emulation is used.',
    'The native helper is read-only. No native permission button is invoked, and closing the owned browser cancels the unaccepted prompt.',
    'Original CFT validates inspection mechanics only. Native binary compatibility remains unverified until the same checks run on built packages.',
    'Only finite JSON summaries are publishable; profiles, browser logs, full DOM, and full native trees are excluded.'
  ]};
let browser,sessionId;
function check(name,passed,detail){report.tests.push({name,status:passed?'passed':'failed',...(detail===undefined?{}:{detail})});console.log(`${passed?'PASS':'FAIL'} Store dialog: ${name}`);return passed;}
function deadline(ms){return Math.min(overallDeadline,Date.now()+ms);}
const operate=(action,until,label,maxMs=5000)=>storeOperation(action,until,label,{maxMs,signal:abort.signal});

function readAddButton() {
  const short=v=>String(v??'').trim().replace(/\s+/g,' ').slice(0,240);
  const candidates=[...document.querySelectorAll('button,[role="button"]')].filter(element=>/^add to (chrome|chromium)$/i.test(short(element.getAttribute('aria-label')||element.innerText||element.textContent))).map((element,index)=>{
    const rect=element.getBoundingClientRect(),style=getComputedStyle(element),x=rect.x+rect.width/2,y=rect.y+rect.height/2;
    const hit=document.elementFromPoint(x,y);
    return {index,label:short(element.getAttribute('aria-label')||element.innerText||element.textContent),disabled:element.matches(':disabled')||element.hasAttribute('disabled')||element.getAttribute('aria-disabled')==='true',
      visible:rect.width>0&&rect.height>0&&style.display!=='none'&&style.visibility!=='hidden'&&Number(style.opacity)>0,
      pointerEvents:style.pointerEvents,hitTargetMatches:hit===element||element.contains(hit),x,y,
      rect:{x:rect.x,y:rect.y,top:rect.top,left:rect.left,right:rect.right,bottom:rect.bottom,width:rect.width,height:rect.height},
      insideViewport:x>=0&&y>=0&&x<innerWidth&&y<innerHeight};
  }).slice(0,8);
  return {url:location.href.slice(0,1600),title:short(document.title),readyState:document.readyState,webdriver:navigator.webdriver,
    viewport:{innerWidth,innerHeight,devicePixelRatio},
    scroll:{x:scrollX,y:scrollY,scrollingElement:{left:document.scrollingElement?.scrollLeft??null,top:document.scrollingElement?.scrollTop??null,
      width:document.scrollingElement?.scrollWidth??null,height:document.scrollingElement?.scrollHeight??null,
      clientWidth:document.scrollingElement?.clientWidth??null,clientHeight:document.scrollingElement?.clientHeight??null},
      body:{width:document.body?.scrollWidth??null,height:document.body?.scrollHeight??null}},candidates};
}

async function queryTargetInstalled(until) {
  return operate(()=>browser.cdp.evaluate(sessionId,`new Promise(resolve=>{
    if(typeof globalThis.chrome?.management?.getAll!=='function'){resolve({supported:false,reason:'management.getAll unavailable'});return;}
    const timer=setTimeout(()=>resolve({supported:true,completed:false,reason:'read-only registry query timed out'}),2500);
    chrome.management.getAll(items=>{clearTimeout(timer);const lastError=globalThis.chrome?.runtime?.lastError?.message??null;resolve({supported:true,completed:Array.isArray(items)&&!lastError,targetCount:Array.isArray(items)?items.filter(item=>item.id===${JSON.stringify(target.id)}).length:null,lastError});});
  })`),until,'Read-only target registry query',3500).catch(error=>({supported:false,error:error.message}));
}

function inspectPrompt(probe) {
  const inspection=probe.dialogInspection;
  const isNativeWindow=record=>['AXWindow','ControlType.Window'].includes(String(record?.role??''));
  const windowVerified=probe.identity?.verified===true&&probe.identity.pid===report.ownedPid&&
    isNativeWindow(inspection?.window)&&inspection.window.windowRoleVerified===true&&
    (process.platform!=='win32'||inspection.window.nativeWindowOwnershipVerified===true);
  const focusedChainFieldsVerified=inspection?.focused?.windowOwnershipVerified===true&&
    inspection.window?.windowOwnershipVerified===true&&
    ((isNativeWindow(inspection.focused)&&(inspection.ancestors??[]).length===0)||
      (inspection.ancestors??[]).some(record=>isNativeWindow(record)&&record.windowOwnershipVerified===true));
  // The unchanged Windows helper predates proofKind, but supplies the full
  // focused-chain proof. Never infer a window-only proof from observed status.
  const legacyFocusedKind=inspection?.proofKind==null&&focusedChainFieldsVerified;
  const proofKind=inspection?.proofKind??(legacyFocusedKind?'focused-ancestry':null);
  const focusedAncestryVerified=windowVerified&&proofKind==='focused-ancestry'&&focusedChainFieldsVerified;
  const ownedVisibleWindowSubtreeVerified=windowVerified&&process.platform==='darwin'&&proofKind==='owned-visible-window'&&
    probe.accessibility?.applicationHidden===false&&inspection.window.minimized===false&&inspection.window.ownWindowSubtreeVerified===true;
  const ownsRecord=record=>proofKind==='focused-ancestry'?record?.windowOwnershipVerified===true:
    proofKind==='owned-visible-window'?record?.ownWindowSubtreeVerified===true:false;
  const normalized=value=>String(value??'').trim().replace(/\s+/g,' ');
  const fields=record=>[record?.title,record?.description,record?.value].map(normalized).filter(Boolean);
  const isButton=record=>/button/i.test(String(record?.role??''));
  const candidates=(inspection?.containers??[]).slice(0,4).map((container,index)=>{
    const owner=container.owningWindow;
    const containerOwnershipVerified=ownsRecord(container)&&(proofKind==='focused-ancestry'?focusedAncestryVerified:
      ownedVisibleWindowSubtreeVerified&&owner?.ownerPID===report.ownedPid&&owner.windowRoleVerified===true&&
      owner.minimized===false&&owner.applicationHidden===false);
    const records=[container,...(container.controls??[])].slice(0,128).filter(ownsRecord);
    const strings=[...new Set(records.flatMap(fields))];
    const expectedHeading=`Add "${target.name}"?`;
    const targetMatched=strings.some(text=>text.replace(/[“”]/g,'"').toLowerCase()===expectedHeading.toLowerCase());
    const buttons=records.filter(isButton).map(record=>({role:record.role,subrole:record.subrole??null,title:normalized(record.title),description:normalized(record.description),value:normalized(record.value),enabled:record.enabled,identifier:record.identifier??record.automationId??null}));
    const add=buttons.filter(button=>[button.title,button.description,button.value].some(label=>/^add extension$/i.test(label)));
    const cancel=buttons.filter(button=>[button.title,button.description,button.value].some(label=>/^cancel$/i.test(label)));
    const permissionTexts=strings.filter(text=>/read|change|websites|permissions|it can/i.test(text)).slice(0,24);
    return {index,role:container.role,subrole:container.subrole??null,selectionReason:container.selectionReason??null,
      containerOwnershipVerified,owningWindow:owner??null,
      title:normalized(container.title),targetMatched,addButtons:add,cancelButtons:cancel,permissionTexts,
      substantivePermissionTextCaptured:permissionTexts.some(text=>/read|change|websites/i.test(text)),
      text:strings.slice(0,64),controls:buttons.slice(0,24)};
  });
  const matched=candidates.find(candidate=>candidate.containerOwnershipVerified&&candidate.targetMatched&&
    candidate.addButtons.some(button=>button.enabled===true)&&candidate.cancelButtons.some(button=>button.enabled===true)&&candidate.substantivePermissionTextCaptured);
  return {proofKind,proofKindSource:inspection?.proofKind?'explicit-helper-field':legacyFocusedKind?'legacy-focused-chain-fields':null,
    ownedNativeWindowVerified:windowVerified,ownedNativeWindowAncestryVerified:focusedAncestryVerified,focusedAncestryVerified,
    ownedVisibleWindowSubtreeVerified,helperStatus:probe.status,inspectionStatus:inspection?.status??'unavailable',
    targetPromptObserved:inspection?.status==='observed'&&Boolean(matched),matchedContainer:matched??null,candidates};
}

async function inspectProfileRegistry() {
  const parsed=[],errors=[],matches=[];
  for(const name of ['Preferences','Secure Preferences']) {
    const file=path.join(browser.profile,'Default',name);
    try {
      if((await stat(file)).size>8388608)throw Error('Owned preference file exceeds bounded read size');
      const data=JSON.parse(await readFile(file,'utf8'));parsed.push(name);
      if(Object.hasOwn(data.extensions?.settings??{},target.id))matches.push({file:name,targetId:target.id});
    } catch(error){if(error.code!=='ENOENT')errors.push({file:name,error:error.message.slice(0,500)});}
  }
  return {parsedFiles:parsed,errors,targetEntries:matches,targetAbsent:parsed.length>0&&errors.length===0&&matches.length===0};
}

try {
  browser=await launchOwnedStoreBrowser({executable:options.browser,output:options.output,signal:abort.signal});
  report.command={executable:browser.executable,args:browser.args};report.ownedPid=browser.child.pid;report.processIdentity=browser.identity;
  const setupUntil=deadline(15000);
  const send=(method,params={},sid=sessionId)=>operate(()=>browser.cdp.send(method,params,sid),setupUntil,method);
  report.observations.browserVersion=await send('Browser.getVersion',{},undefined);
  if(!check('browser matches pinned Chromium revision',report.observations.browserVersion.revision.replace(/^@/,'')==='fb096c0011f9d50f0a264a9376420cdea9c421e3'))throw Error('Unexpected browser revision; no Store input dispatched');
  const targets=await send('Target.getTargets',{},undefined);
  const page=targets.targetInfos.find(info=>info.type==='page'&&info.url==='about:blank');
  if(!page)throw Error('Owned blank Store page not found');
  sessionId=(await send('Target.attachToTarget',{targetId:page.targetId,flatten:true},undefined)).sessionId;
  for(const domain of ['Page','Runtime','Network'])await send(domain+'.enable',{});
  const topFrame=(await send('Page.getFrameTree',{})).frameTree.frame.id;
  report.observations.documentResponses=[];
  browser.cdp.on('Network.responseReceived',(params,sid)=>{
    if(sid===sessionId&&params.type==='Document'&&params.frameId===topFrame&&report.observations.documentResponses.length<8)report.observations.documentResponses.push({url:params.response.url.slice(0,1600),status:params.response.status,mimeType:params.response.mimeType});
  });
  browser.cdp.on('Page.javascriptDialogOpening',(params,sid)=>{if(sid===sessionId)report.observations.unexpectedJavascriptDialog={type:params.type,message:params.message.slice(0,1000)};});
  const listingUntil=deadline(60000);
  report.observations.navigation=await operate(()=>browser.cdp.send('Page.navigate',{url:target.url},sessionId),listingUntil,'Store listing navigation',10000);
  let add,completeAt,signature,stableAt;
  while(Date.now()<listingUntil) {
    add=await operate(()=>browser.cdp.evaluate(sessionId,`(${readAddButton.toString()})()`),listingUntil,'Observe actual Add button').catch(()=>null);
    if(add?.readyState==='complete'&&add.candidates.length) {
      completeAt??=Date.now();const next=JSON.stringify(add.candidates);
      if(next!==signature){signature=next;stableAt=Date.now();}
      if(Date.now()-completeAt>=3000&&Date.now()-stableAt>=1500)break;
    }
    if(abort.signal.aborted)throw Error('Inspection interrupted');
    await delay(300);
  }
  report.observations.addBeforeClick=add;
  const listingLoaded=matchesStoreTargetUrl(add?.url,target)&&add.title.toLowerCase().includes(target.name.toLowerCase())&&
    report.observations.documentResponses.some(response=>response.status===200&&matchesStoreTargetUrl(response.url,target));
  if(!check('actual audited Store listing loaded',Boolean(listingLoaded),report.observations.documentResponses))throw Error('Required actual listing is unavailable');
  let candidate=add.candidates.find(button=>!button.disabled&&button.visible&&button.pointerEvents!=='none'&&button.hitTargetMatches&&button.insideViewport);
  if(!candidate) {
    const observed=add.candidates.find(button=>!button.disabled&&button.visible&&button.pointerEvents!=='none');
    if(observed) {
      const scrollUntil=deadline(7000);
      report.observations.addScrollAttempt={attempted:true,method:'DOM.scrollIntoViewIfNeeded',before:add,targetIndex:observed.index};
      try {
        await operate(()=>browser.cdp.send('DOM.enable',{},sessionId),scrollUntil,'Enable DOM target observation');
        const element=await operate(()=>browser.cdp.send('Runtime.evaluate',{
          expression:`[...document.querySelectorAll('button,[role="button"]')].filter(element=>/^add to (chrome|chromium)$/i.test(String(element.getAttribute('aria-label')||element.innerText||element.textContent||'').trim().replace(/\\s+/g,' ')))[${observed.index}]??null`,
          returnByValue:false,objectGroup:'store-add-scroll-target'
        },sessionId),scrollUntil,'Resolve exact observed Add element');
        if(!element.result?.objectId||element.result.subtype!=='node')throw Error('Observed Add node is no longer available');
        const described=await operate(()=>browser.cdp.send('DOM.describeNode',{objectId:element.result.objectId},sessionId),scrollUntil,'Identify observed Add node');
        report.observations.addScrollAttempt.target={backendNodeId:described.node.backendNodeId,nodeName:described.node.nodeName};
        await operate(()=>browser.cdp.send('DOM.scrollIntoViewIfNeeded',{objectId:element.result.objectId},sessionId),scrollUntil,'One ordinary Add target scroll');
        await delay(250);
        add=await operate(()=>browser.cdp.evaluate(sessionId,`(${readAddButton.toString()})()`),scrollUntil,'Fresh Add geometry after scrolling');
        report.observations.addScrollAttempt.after=add;
      }catch(error){report.observations.addScrollAttempt.error=error.message;}
      finally {await operate(()=>browser.cdp.send('Runtime.releaseObjectGroup',{objectGroup:'store-add-scroll-target'},sessionId),deadline(2000),'Release observed Add reference',2000).catch(()=>{});}
      report.observations.addAfterScroll=add;
      candidate=add.candidates.find(button=>!button.disabled&&button.visible&&button.pointerEvents!=='none'&&button.hitTargetMatches&&button.insideViewport);
    }
  }
  if(!check('actual Add button is enabled and unobscured',Boolean(candidate),add.candidates))throw Error('Add button not safely clickable; no input dispatched');
  const prerequisites=await probeOwnedStoreUi(browser,{mode:'preflight',deadline:deadline(15000),signal:abort.signal});
  report.observations.nativeUiPrerequisites=prerequisites;
  if(!check('read-only native UI prerequisites ready before click',prerequisites.status==='ready'&&prerequisites.identity?.verified===true,{status:prerequisites.status,accessibility:prerequisites.accessibility}))throw Error('No native dialog inspection capability; no input dispatched');
  report.observations.targetRegistryBefore=await queryTargetInstalled(deadline(5000));
  if(report.observations.targetRegistryBefore.completed&&!check('target absent before install request',report.observations.targetRegistryBefore.targetCount===0,report.observations.targetRegistryBefore))throw Error('Target already installed in fresh profile');
  await operate(()=>browser.cdp.send('Target.activateTarget',{targetId:page.targetId}),deadline(5000),'Activate owned Store tab');
  const clickState=await operate(()=>browser.cdp.evaluate(sessionId,`(${readAddButton.toString()})()`),deadline(5000),'Recheck Add button before input');
  report.observations.addRecheckBeforeInput=clickState;
  const clickTarget=clickState.candidates.find(button=>!button.disabled&&button.visible&&button.pointerEvents!=='none'&&button.hitTargetMatches&&button.insideViewport);
  if(!clickTarget)throw Error('Add became disabled or obscured; no input dispatched');
  report.observations.addAtClick=clickTarget;
  const inputUntil=deadline(5000);
  for(const params of [
    {type:'mouseMoved',x:clickTarget.x,y:clickTarget.y},
    {type:'mousePressed',x:clickTarget.x,y:clickTarget.y,button:'left',clickCount:1},
    {type:'mouseReleased',x:clickTarget.x,y:clickTarget.y,button:'left',clickCount:1}
  ]) {
    const record={...params,status:'dispatched'};report.inputEvents.push(record);
    if(params.type==='mousePressed')report.installation.addClickAttempted=true;
    await operate(()=>browser.cdp.send('Input.dispatchMouseEvent',params,sessionId),inputUntil,'Normal Store Add mouse input');record.status='acknowledged';
  }
  report.installation.addClicked=true;
  report.observations.dialogAttempts=[];
  const dialogStarted=Date.now(),dialogUntil=deadline(report.limits.dialogMs);
  let probe,prompt;
  for(let attempt=0;attempt<report.limits.maxDialogProbes&&Date.now()<dialogUntil;attempt++) {
    const scheduledOffsetMs=report.limits.dialogProbeScheduledOffsetsMs[attempt];
    const waitMs=Math.min(dialogStarted+scheduledOffsetMs,dialogUntil)-Date.now();
    if(waitMs>0)await delay(waitMs,undefined,{signal:abort.signal});
    if(Date.now()>=dialogUntil)break;
    const startedOffsetMs=Date.now()-dialogStarted;
    probe=await probeOwnedStoreUi(browser,{mode:'dialog',deadline:dialogUntil,signal:abort.signal});
    prompt=inspectPrompt(probe);
    report.observations.dialogAttempts.push({attempt:attempt+1,scheduledOffsetMs,startedOffsetMs,completedOffsetMs:Date.now()-dialogStarted,
      status:probe.status,inspectionStatus:probe.dialogInspection?.status??null,proofKind:prompt.proofKind,
      ownedNativeWindowVerified:prompt.ownedNativeWindowVerified,focusedAncestryVerified:prompt.focusedAncestryVerified,
      ownedVisibleWindowSubtreeVerified:prompt.ownedVisibleWindowSubtreeVerified,targetPromptObserved:prompt.targetPromptObserved,
      notes:(probe.dialogInspection?.notes??[]).slice(0,8),truncated:probe.truncated??false});
    report.observations.nativeDialogProbe=probe;report.observations.prompt=prompt;
    if(prompt.targetPromptObserved)break;
    if(abort.signal.aborted)throw Error('Inspection interrupted');
  }
  check('actual owned target permission dialog captured',prompt?.targetPromptObserved===true,prompt);
  report.observations.targetRegistryWhilePrompt=await queryTargetInstalled(deadline(5000));
  if(report.observations.targetRegistryWhilePrompt.completed)check('target remains uninstalled while permission is unaccepted',report.observations.targetRegistryWhilePrompt.targetCount===0,report.observations.targetRegistryWhilePrompt);
  check('no install acceptance or native permission action performed',report.installation.accepted===false&&report.installation.acceptInteractionPerformed===false);
}catch(error){report.error=error.stack;check('dialog inspection completes',false,error.message);if(error.cleanup)report.cleanup=error.cleanup;}
finally {
  if(browser) {
    try {
      report.cleanup=await browser.close();
      check('only owned browser is cleaned up',report.cleanup.rootGone===true&&report.cleanup.processGroupGone!==false,report.cleanup);
      if(report.installation.addClickAttempted)check('unaccepted prompt is cancelled by normal browser close',report.cleanup.closedNormally===true,report.cleanup);
    }catch(error){report.cleanup={error:error.stack};check('only owned browser is cleaned up',false,error.message);}
    report.observations.targetProfileRegistryAfterClose=report.cleanup?.rootGone===true?await inspectProfileRegistry():{targetAbsent:false,reason:'Owned browser did not close; persisted state not authoritative'};
    check('target absent from persisted extension registry after close',report.observations.targetProfileRegistryAfterClose.targetAbsent===true,report.observations.targetProfileRegistryAfterClose);
    const observedPresent=(report.observations.targetRegistryBefore?.targetCount??0)>0||
      (report.observations.targetRegistryWhilePrompt?.targetCount??0)>0||
      (report.observations.targetProfileRegistryAfterClose.targetEntries?.length??0)>0;
    report.installation.targetInstalledObserved=observedPresent?true:report.observations.targetProfileRegistryAfterClose.targetAbsent===true?false:null;
  }
  report.finished=new Date().toISOString();report.interrupted=interrupted;
  report.status=!interrupted&&report.tests.length>0&&report.tests.every(test=>test.status==='passed')?'passed':'failed';
  await writeFile(path.join(options.output,'results.json'),JSON.stringify(report,null,2)+'\n');
}
console.log(JSON.stringify({status:report.status,stage:report.stage,target:report.target,installation:report.installation,update:report.update,promptObserved:report.observations.prompt?.targetPromptObserved??false,tests:report.tests.map(test=>({name:test.name,status:test.status}))}));
process.exitCode=report.status==='passed'?0:1;

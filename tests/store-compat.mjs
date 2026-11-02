#!/usr/bin/env node
// Normal Store compatibility test. Separate, required native action helper;
// never run this controller until its helper and actual prompts are reviewed.
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { constants } from 'node:fs';
import { access, mkdir, realpath, stat, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';
import { launchOwnedStoreBrowser, probeOwnedStoreUi, storeOperation } from './lib/owned-store-browser.mjs';
import { matchesStoreTargetUrl } from './lib/store-targets.mjs';
import { COMPAT_TARGET as target, BROWSER_REVISION, UBOL_AUDIT, inspectCompatPrompt, inspectTargetPreferences, summarizePreferences, verifyInstalledSources, validRulesetResponse, classifyActionReceipt, boundedNativeDialogTrace, requiredRemovalEvidenceVerified } from './lib/store-compat-policy.mjs';
import { storeAddControl, extensionRemoveControl } from './lib/store-compat-dom.mjs';
const execute=promisify(execFile);
const options={browser:process.env.CHROME_PATH,output:null};
for(let index=2;index<process.argv.length;index++){
  const key=process.argv[index].replace(/^--/,'');
  if(!Object.hasOwn(options,key)||!process.argv[index+1])throw Error(`Unknown/missing argument: ${process.argv[index]}`);
  options[key]=process.argv[++index];
}
if(!options.browser||!options.output)throw Error('Usage: node tests/store-compat.mjs --browser PATH --output NEW_DIR');
options.output=path.resolve(options.output);await mkdir(path.dirname(options.output),{recursive:true});await mkdir(options.output,{mode:0o700});
const phaseNames=['helpers','launch','listing','installPrompt','acceptInstall','installedRegistry','closeForSourceAudit','installedSourceAudit','resumeForExecution','executionInitial','restartPersistence','executionAfterRestart','ordinaryUpdateCheck','removeUi','removePrompt','confirmRemove','registryAbsent','restartRemovalAbsence','finalNormalClose','persistedRegistrationAbsent'];
const report={schema:1,stage:'normal-store-compatibility',target,started:new Date().toISOString(),platform:process.platform,architecture:process.arch,status:'running',
  phases:phaseNames.map(name=>({name,status:'not-reached'})),observations:{},inputEvents:[],generations:[],actions:[],
  installation:{addClicked:false,accepted:false,acceptanceOutcome:'not-attempted',normalInstallVerified:false,version:null,executionVerified:false,restartPersistenceVerified:false},
  update:{checkAttempted:false,checkCompleted:false,result:null,versionTransitionVerified:false,versionBefore:null,versionAfter:null,limit:'Check completion is separate from a successful server response or an audited installed version upgrade.'},
  removal:{requested:false,confirmed:false,confirmationOutcome:'not-attempted',liveRegistryAbsenceVerified:false,postRestartLiveRegistryAbsenceVerified:false,persistedRegistrationAbsenceVerified:false,targetIdentifierEntryAbsent:null},
  limits:{actionsMs:720000,finalCleanupMs:18000,restartMs:45000,listingMs:60000,nativeProbeOrActionMs:15000,dialogMs:45000,maxDialogProbes:4,maxNativeDialogTraceBytes:32768,oneUpdateCheckMs:60000,maxReportBytes:1048576},
  limitations:[
    'This test uses a CDP controller; native everyday operation without debugging is verified separately by no-debug.mjs.',
    'Installation and removal require a separately reviewed native action helper. No unpacked loader, Store private install API, privileged uninstall call, policy, auto-confirm, unsafe extension flag, or emulation is used.',
    'Selected installed-source verification is bounded to the audited manifest and four JavaScript files; it is not a complete extension security audit.',
    'A completed ordinary update check does not establish a genuine newer Store version transition. That gate remains separate and unverified unless audited newer installed-version evidence exists.',
    'Only finite results.json may be published; profiles, logs, extension package/source and full native trees are excluded.'
  ]};
const overallDeadline=Date.now()+report.limits.actionsMs,abort=new AbortController();
let browser,storeSession,registrySession,actionHelper,interrupted=null;
const timer=setTimeout(()=>abort.abort(),report.limits.actionsMs);
process.once('SIGTERM',()=>{interrupted='SIGTERM';abort.abort();});process.once('SIGINT',()=>{interrupted='SIGINT';abort.abort();});
const until=ms=>Math.min(overallDeadline,Date.now()+ms);
const op=(action,deadline,label,maxMs=5000)=>storeOperation(action,deadline,label,{maxMs,signal:abort.signal});
async function phase(name,action){
  const entry=report.phases.find(value=>value.name===name);entry.status='running';entry.started=new Date().toISOString();
  try{const value=await action();entry.status='passed';entry.finished=new Date().toISOString();console.log(`PASS Store compatibility: ${name}`);return value;}
  catch(error){entry.status='failed';entry.error=String(error.message).slice(0,2000);entry.finished=new Date().toISOString();throw error;}
}
function recordGeneration(){report.generations.push({generation:browser.generation??report.generations.length,ownedPid:browser.child.pid,identity:browser.identity,command:{executable:browser.executable,args:browser.args},logFile:path.basename(browser.logPath??'browser.log'),lastClose:browser.lastClose??null});}
async function attachPage(targetId,deadline){const {sessionId}=await op(()=>browser.cdp.send('Target.attachToTarget',{targetId,flatten:true}),deadline,'Attach owned page');for(const domain of ['Page','Runtime','DOM'])await op(()=>browser.cdp.send(`${domain}.enable`,{},sessionId),deadline,`Enable ${domain}`);return sessionId;}
async function openStorePage(deadline,{requireResponse=false}={}){
  const targets=(await op(()=>browser.cdp.send('Target.getTargets'),deadline,'Find owned page')).targetInfos;
  let page=targets.find(value=>value.type==='page'&&value.url==='about:blank');
  if(!page){const {targetId}=await op(()=>browser.cdp.send('Target.createTarget',{url:'about:blank'}),deadline,'Open owned Store page');page={targetId};}
  storeSession=await attachPage(page.targetId,deadline);
  registrySession=storeSession;
  const responses=[];
  await op(()=>browser.cdp.send('Network.enable',{},storeSession),deadline,'Observe listing response');
  const top=(await op(()=>browser.cdp.send('Page.getFrameTree',{},storeSession),deadline,'Read owned frame')).frameTree.frame.id;
  const listener=(event,sid)=>{if(sid===storeSession&&event.type==='Document'&&event.frameId===top&&responses.length<8)responses.push({url:event.response.url.slice(0,1600),status:event.response.status});};
  browser.cdp.on('Network.responseReceived',listener);
  try{
    await op(()=>browser.cdp.send('Page.navigate',{url:target.url},storeSession),deadline,'Open real Store listing',10000);
    while(Date.now()<deadline){
      const state=await op(()=>browser.cdp.evaluate(storeSession,`({url:location.href,title:document.title,ready:document.readyState==='complete',management:typeof globalThis.chrome?.management?.getAll})`),deadline,'Wait for real listing').catch(()=>null);
      if(state?.ready&&matchesStoreTargetUrl(state.url,target)&&state.title.includes(target.name)&&state.management==='function'){
        if(requireResponse&&!responses.some(response=>response.status===200&&matchesStoreTargetUrl(response.url,target)))throw Error('Actual Store listing response was not verified');
        return {targetId:page.targetId,...state,responses};
      }
      await delay(300,undefined,{signal:abort.signal});
    }
    throw Error('Actual target Store listing/registry context did not become ready');
  }finally{browser.cdp.removeListener('Network.responseReceived',listener);}
}
async function registry(deadline){
  const result=await op(()=>browser.cdp.evaluate(registrySession,`new Promise(resolve=>{
    if(typeof globalThis.chrome?.management?.getAll!=='function'){resolve({completed:false,error:'management unavailable'});return;}
    const timer=setTimeout(()=>resolve({completed:false,error:'registry timeout'}),2500);
    chrome.management.getAll(items=>{clearTimeout(timer);const error=globalThis.chrome?.runtime?.lastError?.message;
      resolve({completed:!error&&Array.isArray(items),error:error??null,items:Array.isArray(items)?items.filter(item=>item.id===${JSON.stringify(target.id)}).slice(0,2).map(item=>({id:item.id,name:item.name,version:item.version,enabled:item.enabled,installType:item.installType,type:item.type,updateUrl:item.updateUrl??null})):[]});});
  })`),deadline,'Read only selected installed target registry',3500);
  if(!result.completed)throw Error(result.error??'Registry query incomplete');return result;
}
async function waitRegistry(deadline,present){
  let latest;
  while(Date.now()<deadline){latest=await registry(deadline);if(present?latest.items.length===1:latest.items.length===0)return latest;await delay(300,undefined,{signal:abort.signal});}
  throw Error(`Target registry did not become ${present?'installed':'absent'}: ${JSON.stringify(latest)}`);
}
function requireInstalled(result){const item=result.items[0];if(result.items.length!==1||item.id!==target.id||item.name!==target.name||item.version!==UBOL_AUDIT.version||item.enabled!==true||item.installType!=='normal'||item.type!=='extension')throw Error('Installed target is not the audited enabled normal Store extension');return item;}
async function clickable(expression,deadline,label){
  let state;
  while(Date.now()<deadline){
    state=await op(()=>browser.cdp.evaluate(storeSession,`(${expression})(false)`),deadline,`Observe ${label}`);
    if(state?.count===1&&!state.truncated&&state.candidates.some(button=>button.enabled&&button.visible&&button.pointerEvents!=='none'))break;
    await delay(300,undefined,{signal:abort.signal});
  }
  const usable=value=>value?.count===1&&!value.truncated&&value.candidates?.find(button=>button.enabled&&button.visible&&button.pointerEvents!=='none'&&button.insideViewport&&button.hitTargetMatches);
  let selected=usable(state);
  if(!selected&&state?.count===1&&state.candidates.some(button=>button.enabled&&button.visible&&button.pointerEvents!=='none')){
    const before=state,group=`aa-compat-scroll-${randomUUID()}`;
    try{
      const element=await op(()=>browser.cdp.send('Runtime.evaluate',{expression:`(${expression})(true)`,returnByValue:false,objectGroup:group},storeSession),deadline,`Resolve exact ${label}`);
      if(element.result?.subtype!=='node'||!element.result.objectId)throw Error(`No exact ${label} element`);
      await op(()=>browser.cdp.send('DOM.scrollIntoViewIfNeeded',{objectId:element.result.objectId},storeSession),deadline,`Ordinary ${label} scroll`);
      await delay(250,undefined,{signal:abort.signal});state=await op(()=>browser.cdp.evaluate(storeSession,`(${expression})(false)`),deadline,`Recheck ${label}`);
      report.observations[`${label}Scroll`]={before,after:state,attempts:1};selected=usable(state);
    }finally{await op(()=>browser.cdp.send('Runtime.releaseObjectGroup',{objectGroup:group},storeSession),deadline,'Release observed control').catch(()=>{});}
  }
  if(!selected)throw Error(`${label} is not unique, enabled, visible, inside viewport and unobscured`);
  const fresh=await op(()=>browser.cdp.evaluate(storeSession,`(${expression})(false)`),deadline,`Fresh ${label} hit test`);selected=usable(fresh);
  if(!selected)throw Error(`${label} changed before input`);return {state:fresh,selected};
}
async function mouseClick(control,label,deadline){
  for(const params of [{type:'mouseMoved',x:control.x,y:control.y},{type:'mousePressed',x:control.x,y:control.y,button:'left',clickCount:1},{type:'mouseReleased',x:control.x,y:control.y,button:'left',clickCount:1}]){
    const record={label,...params,acknowledged:false};report.inputEvents.push(record);await op(()=>browser.cdp.send('Input.dispatchMouseEvent',params,storeSession),deadline,`Normal ${label} input`);record.acknowledged=true;
  }
}
async function capturePrompt(operation,deadline){
  const started=Date.now(),attempts=[],capture={operation,status:'observing',started:new Date().toISOString(),attempts:[]};
  report.observations.promptCaptures??={};report.observations.promptCaptures[operation]=capture;
  try{
    for(const offset of [500,10000,20000,30000]){
      const wait=Math.min(started+offset,deadline)-Date.now();if(wait>0)await delay(wait,undefined,{signal:abort.signal});if(Date.now()>=deadline)break;
      const probe=await probeOwnedStoreUi(browser,{mode:'dialog',deadline,signal:abort.signal});
      const prompt=inspectCompatPrompt(probe,{pid:browser.child.pid,operation}),attempt={offset,completedOffsetMs:Date.now()-started,status:probe.status,targetPromptObserved:prompt.targetPromptObserved};
      attempts.push(attempt);
      capture.attempts.push({...attempt,nativeDialogTrace:boundedNativeDialogTrace(probe,{maxBytes:report.limits.maxNativeDialogTraceBytes})});
      if(prompt.targetPromptObserved){capture.status='observed';return {identity:probe.identity,prompt,attempts};}
    }
    capture.status='not-found';throw Error(`Actual owned ${operation} prompt not verified after ${attempts.length} probes`);
  }catch(error){if(capture.status==='observing')capture.status='failed';capture.error=String(error.message).slice(0,1000);throw error;}
  finally{capture.finished=new Date().toISOString();}
}
async function nativeAction(operation,captured,deadline){
  const expectedStarted=browser.identity.started;
  const nativeIdentity=captured.identity;
  const command=process.platform==='win32'?'powershell.exe':actionHelper;
  const args=process.platform==='win32'?['-NoProfile','-NonInteractive','-File',actionHelper,'-PidValue',String(browser.child.pid),'-Profile',browser.profile,'-Executable',browser.executable,'-ExpectedStarted',expectedStarted,'-Target',target.key,'-Operation',operation]:
    ['--pid',String(browser.child.pid),'--profile',browser.profile,'--executable',browser.executable,'--expected-started',expectedStarted,'--expected-start-seconds',String(nativeIdentity.startSeconds),'--expected-start-microseconds',String(nativeIdentity.startMicroseconds),'--target',target.key,'--operation',operation];
  if(process.platform==='darwin'&&(!Number.isInteger(nativeIdentity.startSeconds)||!Number.isInteger(nativeIdentity.startMicroseconds)))throw Error('Precise native Mac creation identity unavailable; no action helper invoked');
  const timeout=Math.min(15000,deadline-Date.now());if(timeout<=0)throw Error('Native action deadline exceeded');
  const receipt={operation,target:target.key,status:'invoking',actionAttempted:null,actionPerformed:null,actionOutcomeUncertain:true};report.actions.push(receipt);
  try{
    const {stdout}=await execute(command,args,{timeout,killSignal:'SIGKILL',maxBuffer:65536,signal:abort.signal});const result=JSON.parse(stdout.replace(/^\uFEFF/,''));
    Object.assign(receipt,{schema:result.schema,status:result.status,operation:result.operation,target:result.target,actionAttempted:result.actionAttempted,actionPerformed:result.actionPerformed,actionType:result.actionType,identity:result.identity,prompt:result.prompt,focusAncestryDiagnostics:result.focusAncestryDiagnostics,errors:result.errors});
    const {verified,actionOutcomeUncertain}=classifyActionReceipt(result,{browser,operation,...(process.platform==='darwin'?{expectedNativeIdentity:nativeIdentity}:{})});
    receipt.actionOutcomeUncertain=actionOutcomeUncertain;
    if(!verified)throw Error(`Native helper did not prove the exact ${operation} action`);
    if(operation==='accept-install')report.installation.acceptanceOutcome='performed-with-verified-receipt';else report.removal.confirmationOutcome='performed-with-verified-receipt';
    return result;
  }catch(error){
    if(receipt.status==='invoking')receipt.status='transport-error';
    receipt.error=String(error.message).slice(0,2000);
    const outcome=receipt.actionOutcomeUncertain?'uncertain':'not-performed-with-verified-receipt';
    if(operation==='accept-install'){report.installation.acceptanceOutcome=outcome;report.installation.accepted=receipt.actionOutcomeUncertain?null:false;}
    else{report.removal.confirmationOutcome=outcome;report.removal.confirmed=receipt.actionOutcomeUncertain?null:false;}
    if(receipt.actionOutcomeUncertain){
      const observed=await registry(until(3500)).catch(queryError=>({completed:false,error:String(queryError.message).slice(0,500)}));
      report.observations.registryAfterUncertainAction??=[];report.observations.registryAfterUncertainAction.push({operation,...observed});
    }
    throw error;
  }
}
async function restart(deadline){
  if(typeof browser.restart!=='function')throw Error('Reviewed owned-profile restart interface is unavailable');
  const previous={pid:browser.child.pid,started:browser.identity.started,generation:browser.generation,profile:browser.profile,executable:browser.executable};
  const handle=await op(()=>browser.restart({signal:abort.signal}),deadline,'Restart exact owned profile',45000);
  if(handle!==browser||browser.profile!==previous.profile||browser.executable!==previous.executable||browser.child.pid===previous.pid||browser.identity.started===previous.started||browser.lastClose?.closedNormally!==true)throw Error('Owned restart did not prove a fresh normal generation');
  recordGeneration();await openStorePage(deadline);requireInstalled(await registry(deadline));
}
async function extensionPageProbe(deadline,declaredRulesets){
  const {targetId}=await op(()=>browser.cdp.send('Target.createTarget',{url:`chrome-extension://${target.id}/dashboard.html`}),deadline,'Open real installed options page');
  const session=await attachPage(targetId,deadline);
  let identity;
  while(Date.now()<deadline){
    identity=await op(()=>browser.cdp.evaluate(session,`({origin:location.origin,ready:document.readyState==='complete',id:globalThis.chrome?.runtime?.id,version:globalThis.chrome?.runtime?.getManifest?.().version})`),deadline,'Read own extension context').catch(()=>null);
    if(identity?.ready&&identity.origin===`chrome-extension://${target.id}`&&identity.id===target.id&&identity.version===UBOL_AUDIT.version)break;
    await delay(300,undefined,{signal:abort.signal});
  }
  if(identity?.ready!==true||identity.origin!==`chrome-extension://${target.id}`||identity.id!==target.id||identity.version!==UBOL_AUDIT.version)throw Error('Audited own-extension context unavailable without unsafe flags');
  let result;
  for(let attempt=0;attempt<3&&Date.now()<deadline;attempt++){
    result=await op(()=>browser.cdp.evaluate(session,`new Promise(resolve=>{const timer=setTimeout(()=>resolve({completed:false,error:'worker read timed out'}),4000);chrome.runtime.sendMessage({what:'getEnabledRulesets'},value=>{clearTimeout(timer);const error=chrome.runtime.lastError?.message;resolve({completed:!error,error:error??null,value:Array.isArray(value)&&value.length<=256?value:null});});})`),deadline,'Read actual uBOL worker enabled rulesets',5000);
    if(result.completed&&validRulesetResponse(result.value,declaredRulesets))return {session,identity,rulesets:result.value,attempts:attempt+1};
    await delay(300,undefined,{signal:abort.signal});
  }
  throw Error(`Real worker did not return valid declared ruleset IDs: ${JSON.stringify(result)}`);
}
async function updateCheck(session,deadline){
  const key=`__aa_store_compat_update_${randomUUID().replaceAll('-','')}`;
  report.update.checkAttempted=true;report.update.versionBefore=UBOL_AUDIT.version;
  try{
    await op(()=>browser.cdp.evaluate(session,`(()=>{const state={done:false};Object.defineProperty(globalThis,${JSON.stringify(key)},{value:state,configurable:true});try{Promise.resolve(chrome.runtime.requestUpdateCheck()).then(value=>{state.result={status:value?.status,version:value?.version??null};state.done=true;},error=>{state.error=String(error.message).slice(0,500);state.done=true;});}catch(error){state.error=String(error.message).slice(0,500);state.done=true;}return {requested:true};})()`),deadline,'One ordinary own-extension update request');
    while(Date.now()<deadline){
      const state=await op(()=>browser.cdp.evaluate(session,`globalThis[${JSON.stringify(key)}]??null`),deadline,'Observe one update result');
      if(state?.done){
        if(state.error)throw Error(`Ordinary update request failed: ${state.error}`);
        report.update.result=state.result;
        if(!['no_update','update_available'].includes(state.result?.status))throw Error(`Update check not completed: ${state.result?.status}`);
        if(state.result.version!==null&&(typeof state.result.version!=='string'||state.result.version.length>80))throw Error('Invalid update version result');
        report.update.checkCompleted=true;report.update.versionAfter=(await registry(deadline)).items[0]?.version??null;return state.result;
      }
      await delay(500,undefined,{signal:abort.signal});
    }
    throw Error('One ordinary update check exceeded its bounded wait');
  }finally{await op(()=>browser.cdp.evaluate(session,`delete globalThis[${JSON.stringify(key)}]`),until(2000),'Remove test-only update bookkeeping',2000).catch(()=>{});}
}

try{
  await phase('helpers',async()=>{
    if(!process.env.AA_STORE_ACTION_HELPER)throw Error('AA_STORE_ACTION_HELPER is required; no browser or Store action started');
    if(!process.env.AA_STORE_UI_HELPER)throw Error('AA_STORE_UI_HELPER is required; no browser or Store action started');
    actionHelper=await realpath(process.env.AA_STORE_ACTION_HELPER);if(!(await stat(actionHelper)).isFile())throw Error('Action helper is not a regular file');
    await access(actionHelper,process.platform==='win32'?constants.R_OK:constants.X_OK);report.observations.actionHelper={path:actionHelper,platform:process.platform,contract:'schema1-owned-target-native-action'};
  });
  await phase('launch',async()=>{browser=await launchOwnedStoreBrowser({executable:options.browser,output:options.output,signal:abort.signal});recordGeneration();const version=await op(()=>browser.cdp.send('Browser.getVersion'),until(5000),'Verify browser revision');report.observations.browserVersion=version;if(version.revision.replace(/^@/,'')!==BROWSER_REVISION)throw Error('Unexpected browser revision');});
  let installPrompt,audit,execution;
  await phase('listing',async()=>{
    report.observations.initialListing=await openStorePage(until(60000),{requireResponse:true});const before=await registry(until(5000));report.observations.registryBefore=before;if(before.items.length)throw Error('Target already installed in fresh owned profile');
    await op(()=>browser.cdp.send('Target.activateTarget',{targetId:report.observations.initialListing.targetId}),until(5000),'Activate owned Store listing');
    const ui=await probeOwnedStoreUi(browser,{mode:'preflight',deadline:until(15000),signal:abort.signal});if(ui.status!=='ready'||ui.identity?.pid!==browser.child.pid||ui.identity?.verified!==true)throw Error('Strict owned native UI prerequisites unavailable');report.observations.nativePrerequisites={status:ui.status,identity:ui.identity,accessibility:ui.accessibility};
    const control=await clickable(storeAddControl.toString(),until(10000),'StoreAdd');report.observations.storeAdd=control.state;await mouseClick(control.selected,'StoreAdd',until(5000));report.installation.addClicked=true;
  });
  await phase('installPrompt',async()=>{installPrompt=await capturePrompt('accept-install',until(45000));report.observations.installPrompt=installPrompt;});
  await phase('acceptInstall',async()=>{await nativeAction('accept-install',installPrompt,until(15000));report.installation.accepted=true;});
  await phase('installedRegistry',async()=>{const value=await waitRegistry(until(60000),true),item=requireInstalled(value);report.observations.installedRegistry=value;report.installation.normalInstallVerified=true;report.installation.version=item.version;});
  await phase('closeForSourceAudit',async()=>{const closed=await browser.close();report.observations.closeForSourceAudit=closed;if(!closed.closedNormally)throw Error('Normal owned shutdown required before source audit');});
  await phase('installedSourceAudit',async()=>{audit=await op(()=>verifyInstalledSources(browser.profile),until(10000),'Verify actual installed sources',10000);report.observations.installedAudit=audit;});
  await phase('resumeForExecution',async()=>{await restart(until(45000));});
  await phase('executionInitial',async()=>{execution=await extensionPageProbe(until(45000),audit.declaredRulesets);report.observations.initialExecution={identity:execution.identity,rulesets:execution.rulesets,attempts:execution.attempts};report.installation.executionVerified=true;});
  await phase('restartPersistence',async()=>{await restart(until(45000));});
  await phase('executionAfterRestart',async()=>{execution=await extensionPageProbe(until(45000),audit.declaredRulesets);report.observations.executionAfterRestart={identity:execution.identity,rulesets:execution.rulesets,attempts:execution.attempts};report.installation.restartPersistenceVerified=true;});
  await phase('ordinaryUpdateCheck',async()=>{await updateCheck(execution.session,until(60000));});
  await phase('removeUi',async()=>{
    const {targetId}=await op(()=>browser.cdp.send('Target.createTarget',{url:'chrome://extensions/'}),until(5000),'Open normal extensions UI');storeSession=await attachPage(targetId,until(10000));await op(()=>browser.cdp.send('Target.activateTarget',{targetId}),until(5000),'Activate normal extensions UI');
    const deadline=until(30000),expression=`(returnElement)=>(${extensionRemoveControl.toString()})(${JSON.stringify(target.id)},${JSON.stringify(target.name)},returnElement)`;
    const control=await clickable(expression,deadline,'TargetRemove');report.observations.removeControl=control.state;await mouseClick(control.selected,'TargetRemove',until(5000));report.removal.requested=true;
  });
  let removalPrompt;
  await phase('removePrompt',async()=>{removalPrompt=await capturePrompt('confirm-remove',until(45000));report.observations.removePrompt=removalPrompt;});
  await phase('confirmRemove',async()=>{await nativeAction('confirm-remove',removalPrompt,until(15000));report.removal.confirmed=true;});
  await phase('registryAbsent',async()=>{await openStorePage(until(30000));report.observations.registryAfterRemoval=await waitRegistry(until(30000),false);report.removal.liveRegistryAbsenceVerified=true;});
  await phase('restartRemovalAbsence',async()=>{
    if(typeof browser.restart!=='function')throw Error('Owned restart API unavailable');const previousPid=browser.child.pid,handle=await op(()=>browser.restart({signal:abort.signal}),until(45000),'Restart after normal removal',45000);
    if(handle!==browser||browser.child.pid===previousPid||browser.lastClose?.closedNormally!==true)throw Error('Post-removal restart was not verified');recordGeneration();await openStorePage(until(30000));report.observations.registryAfterRemovalRestart=await registry(until(5000));if(report.observations.registryAfterRemovalRestart.items.length)throw Error('Removed target returned after restart');report.removal.postRestartLiveRegistryAbsenceVerified=true;
  });
  await phase('finalNormalClose',async()=>{report.observations.finalNormalClose=await browser.close();if(!report.observations.finalNormalClose.closedNormally)throw Error('Final browser close was not normal');});
  await phase('persistedRegistrationAbsent',async()=>{
    if(!requiredRemovalEvidenceVerified(report))throw Error('Native removal, live/restarted absence, and normal final close must all be verified');
    const value=await inspectTargetPreferences(browser.profile);report.observations.persistedRegistration=summarizePreferences(value);report.removal.targetIdentifierEntryAbsent=value.targetAbsent;
    if(!value.targetRegistrationAbsent)throw Error('Persisted target registration remains or preference evidence is incomplete/nonempty');report.removal.persistedRegistrationAbsenceVerified=true;
  });
}catch(error){report.error=String(error.stack).slice(0,8000);if(error.cleanup)report.cleanup=error.cleanup;}
finally{
  clearTimeout(timer);
  const cleanupDeadline=Date.now()+18000;
  if(browser){
    try{report.cleanup=await browser.close();}catch(error){report.cleanup={error:String(error.message).slice(0,2000)};}
    if(report.cleanup?.rootGone===true&&Date.now()<cleanupDeadline){
      try{const value=await storeOperation(()=>inspectTargetPreferences(browser.profile),cleanupDeadline,'Read final owned persisted target state',{maxMs:3000});report.observations.persistedPreferenceStateAfterAnyClose={authoritativeNormalClose:report.cleanup.closedNormally===true,...summarizePreferences(value)};}
      catch(error){report.observations.persistedPreferenceStateAfterAnyClose={completed:false,error:String(error.message).slice(0,500)};}
    }
  }
  report.interrupted=interrupted;report.finished=new Date().toISOString();
  report.status=!interrupted&&report.phases.every(value=>value.status==='passed')&&report.cleanup?.closedNormally===true?'passed':'failed';
  report.coverage={normalInstall:report.installation.normalInstallVerified,workerExecution:report.installation.executionVerified,restartPersistence:report.installation.restartPersistenceVerified,ordinaryUpdateCheck:report.update.checkCompleted,genuineVersionTransition:report.update.versionTransitionVerified,normalRemovalWithPersistedRegistrationAbsence:requiredRemovalEvidenceVerified(report)&&report.removal.persistedRegistrationAbsenceVerified&&report.cleanup?.closedNormally===true};
  let text=JSON.stringify(report,null,2)+'\n';if(Buffer.byteLength(text)>1048576){report.observations={omitted:'Report exceeded finite evidence limit'};report.status='failed';report.error='Finite report size exceeded';text=JSON.stringify(report,null,2)+'\n';}
  await writeFile(path.join(options.output,'results.json'),text);
}
console.log(JSON.stringify({status:report.status,coverage:report.coverage,phases:report.phases.map(value=>({name:value.name,status:value.status}))}));process.exitCode=report.status==='passed'?0:1;

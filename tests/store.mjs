#!/usr/bin/env node
// READ-ONLY Store preflight. Never clicks Add, invokes installation APIs,
// accepts a dialog, or changes flags/policies/security settings.
import { spawn, execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { access, mkdir, open, readFile, realpath, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { CDP } from './lib/cdp.mjs';
import { DEFAULT_STORE_TARGET, getStoreTarget, matchesStoreTargetUrl } from './lib/store-targets.mjs';

const execute=promisify(execFile);
const revision='fb096c0011f9d50f0a264a9376420cdea9c421e3';
const options={browser:process.env.CHROME_PATH,output:null,'timeout-ms':'60000',target:DEFAULT_STORE_TARGET};
for(let i=2;i<process.argv.length;i++) {
  const key=process.argv[i].replace(/^--/,'');
  if(!Object.hasOwn(options,key)||!process.argv[i+1])throw Error(`Unknown/missing argument: ${process.argv[i]}`);
  options[key]=process.argv[++i];
}
if(!options.browser||!options.output)throw Error('Usage: node tests/store.mjs --browser PATH --output NEW_DIR [--timeout-ms 60000] [--target always-active|ubol]');
const target=getStoreTarget(options.target),listing=target.url;
options['timeout-ms']=Number(options['timeout-ms']);
if(!Number.isInteger(options['timeout-ms'])||options['timeout-ms']<5000||options['timeout-ms']>120000)throw Error('Invalid timeout-ms');
options.browser=await realpath(options.browser);
options.output=path.resolve(options.output);
await mkdir(path.dirname(options.output),{recursive:true});
await mkdir(options.output,{mode:0o700});
const profile=path.join(options.output,'profile');
await mkdir(profile,{mode:0o700});
const report={schema:1,stage:'read-only-store-preflight',started:new Date().toISOString(),platform:process.platform,architecture:process.arch,
  listing,target,expectedVersion:'156.0.8078.80',expectedRevision:revision,tests:[],observations:{},
  actions:['Launch a fresh owned browser profile','Navigate the owned page to the fixed public listing','Read bounded DOM/AX and capability types','Read optional owned-PID native UI prerequisites','Close only the owned browser'],
  installation:{attempted:false,addClicked:false,permissionDialogAccepted:false,verified:false},
  limits:{launchMs:20000,setupMs:15000,listingWaitMs:options['timeout-ms'],buttonSettleMs:3000,buttonStableMs:1500,finalCaptureMs:30000,cleanupMs:18000,readOperationMs:5000,nativeUiHelperMs:15000,maxButtonRecords:40,maxCandidateRecords:8,maxTextSnippet:1200,maxStringLength:240},
  limitations:[
    'CDP is used only as this preflight test controller; this is not evidence of native operation without debugging.',
    'No installation API is invoked, Add button clicked, native permission dialog accepted, security policy changed, or extension loaded.',
    'A passed preflight means the bounded observations were captured, not that installation, restart, update, removal, or a native binary has passed.',
    'Minimal remote-debugging flags may expose automation to the website; the observed navigator.webdriver value is recorded.',
    'Only finite summaries are publishable. The profile, browser log, full DOM, and full accessibility trees are excluded.'
  ]};
let child,cdp,initialIdentity,interrupted=null,interruptOperation;
const interruptPromise=new Promise((_,reject)=>{interruptOperation=reject;});
interruptPromise.catch(()=>{});
const abortReadHelper=new AbortController();
const stop=signal=>{interrupted=signal;abortReadHelper.abort();interruptOperation(Error(`Interrupted by ${signal}`));};
process.once('SIGINT',()=>stop('SIGINT'));
process.once('SIGTERM',()=>stop('SIGTERM'));
async function within(action,deadline,label,{maxMs=5000,interruptible=true}={}) {
  const timeoutMs=Math.min(maxMs,deadline-Date.now());
  if(timeoutMs<=0)throw Error(`${label} exceeded its phase deadline`);
  let timer;
  const timeout=new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error(`${label} timed out`)),timeoutMs);});
  try{return await Promise.race([Promise.resolve().then(action),timeout,...(interruptible?[interruptPromise]:[])]);}
  finally{clearTimeout(timer);}
}
function check(name,passed,detail) {
  report.tests.push({name,status:passed?'passed':'failed',...(detail===undefined?{}:{detail})});
  console.log(`${passed?'PASS':'FAIL'} Store preflight: ${name}`);
}

async function identity({timeoutMs=5000,signal}={}) {
  if(!child?.pid||child.exitCode!==null||child.signalCode!==null)return null;
  if(process.platform==='win32') {
    const script="$p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$env:AA_STORE_PID);if($null -eq $p){exit 0};[pscustomobject]@{pid=$p.ProcessId;executable=$p.ExecutablePath;command=$p.CommandLine;started=$p.CreationDate.ToUniversalTime().ToString('o')}|ConvertTo-Json -Compress";
    const {stdout}=await execute('powershell.exe',['-NoProfile','-NonInteractive','-Command',script],{timeout:timeoutMs,signal,maxBuffer:65536,env:{...process.env,AA_STORE_PID:String(child.pid)}});
    if(!stdout.trim())return null;
    const value=JSON.parse(stdout.replace(/^\uFEFF/,''));
    return {...value,verified:value.pid===child.pid&&value.executable?.toLowerCase()===options.browser.toLowerCase()&&value.command?.includes(`--user-data-dir=${profile}`)};
  }
  let stdout;
  try {({stdout}=await execute('ps',['-ww','-p',String(child.pid),'-o','pid=','-o','pgid=','-o','lstart=','-o','command='],{timeout:Math.min(timeoutMs,3000),signal,maxBuffer:65536}));}
  catch(error){if(error.code===1)return null;throw error;}
  const match=stdout.match(/^\s*(\d+)\s+(\d+)\s+(\S+\s+\S+\s+\d+\s+\S+\s+\d+)\s+(.+)\s*$/);
  if(!match)throw Error('Owned process identity could not be parsed.');
  return {pid:Number(match[1]),processGroup:Number(match[2]),started:match[3].trim().replace(/\s+/g,' '),command:match[4],
    verified:Number(match[1])===child.pid&&Number(match[2])===child.pid&&match[4].includes(options.browser)&&match[4].includes(`--user-data-dir=${profile}`)};
}

async function nativeUiPrerequisites(deadline) {
  const helper=process.env.AA_STORE_UI_HELPER;
  if(!helper)return {schema:1,status:'unsupported',reason:'AA_STORE_UI_HELPER is not configured',interactionPerformed:false};
  const command=process.platform==='win32'?'powershell.exe':helper;
  const args=process.platform==='win32'?['-NoProfile','-NonInteractive','-File',helper,'-PidValue',String(child.pid),'-Profile',profile,'-Executable',options.browser]:['--pid',String(child.pid),'--profile',profile,'--executable',options.browser];
  try {
    const timeout=Math.min(15000,deadline-Date.now());
    if(timeout<=0)throw Error('Native UI prerequisite phase deadline expired');
    const {stdout}=await execute(command,args,{timeout,signal:abortReadHelper.signal,maxBuffer:65536});
    const result=JSON.parse(stdout.replace(/^\uFEFF/,''));
    if(result.schema!==1||!['ready','untrusted','unsupported','error'].includes(result.status))throw Error('Unexpected helper schema/status');
    if(result.status==='ready'&&result.identity?.verified!==true)throw Error('Helper claimed ready without owned identity verification');
    return result;
  } catch(error) {return {schema:1,status:'error',reason:error.message.slice(0,1000),interactionPerformed:false};}
}

function domSummary() {
  const short=value=>String(value??'').trim().replace(/\s+/g,' ').slice(0,240);
  const expression=/\badd to (?:chrome|chromium)\b|^add extension$|^install(?: extension)?$/i;
  const buttons=[...document.querySelectorAll('button,[role="button"]')].map(element=>{
    const box=element.getBoundingClientRect();const style=getComputedStyle(element);
    const label=short(element.getAttribute('aria-label')||element.innerText||element.textContent);
    const disabled=element.matches(':disabled')||element.hasAttribute('disabled')||element.getAttribute('aria-disabled')==='true';
    return {label,enabled:!disabled,disabled,ariaDisabled:element.getAttribute('aria-disabled'),visible:box.width>0&&box.height>0&&style.display!=='none'&&style.visibility!=='hidden',pointerEvents:style.pointerEvents};
  });
  const candidates=buttons.filter(button=>expression.test(button.label)).slice(0,8);
  return {url:location.href.slice(0,1600),title:short(document.title),readyState:document.readyState,
    heading:short(document.querySelector('h1')?.textContent),webdriver:navigator.webdriver,
    addCandidates:candidates,buttons:buttons.slice(0,40),buttonCount:buttons.length,
    textSnippet:document.body?.innerText?.slice(0,1200)??'',
    capabilities:{chromeType:typeof globalThis.chrome,webstorePrivateType:typeof globalThis.chrome?.webstorePrivate,
      beginInstallWithManifest3Type:typeof globalThis.chrome?.webstorePrivate?.beginInstallWithManifest3,
      completeInstallType:typeof globalThis.chrome?.webstorePrivate?.completeInstall}};
}

function axSummary(nodes) {
  const short=value=>String(value??'').slice(0,240);
  const buttons=nodes.filter(node=>node.role?.value==='button'&&!node.ignored).map(node=>{
    const disabled=node.properties?.find(property=>property.name==='disabled')?.value?.value===true;
    return {role:'button',label:short(node.name?.value),enabled:!disabled,disabled};
  });
  const expression=/\badd to (?:chrome|chromium)\b|^add extension$|^install(?: extension)?$/i;
  return {root:{role:short(nodes[0]?.role?.value),name:short(nodes[0]?.name?.value)},
    addCandidates:buttons.filter(button=>expression.test(button.label)).slice(0,8),buttons:buttons.slice(0,40),buttonCount:buttons.length,
    nodeCount:nodes.length,fullTreeRetained:false};
}

async function cleanup() {
  const deadline=Date.now()+18000;
  const remaining=()=>{const value=deadline-Date.now();if(value<100)throw Error('Owned cleanup exceeded its 18-second deadline');return value;};
  const inspect=()=>identity({timeoutMs:Math.min(2000,remaining())});
  const groupIsGone=async()=>{
    const groupDeadline=Math.min(Date.now()+3000,deadline);
    while(Date.now()<groupDeadline) {
      try {process.kill(-child.pid,0);}
      catch(error){if(error.code==='ESRCH')return true;throw error;}
      await delay(100);
    }
    return false;
  };
  const result={ownedPid:child?.pid,signals:[]};
  if(!child?.pid)return {...result,rootGone:true};
  let current=await inspect();
  if(!current)return {...result,rootGone:true,method:'Owned root already exited',...(process.platform!=='win32'?{processGroupGone:await groupIsGone()}:{})};
  if(!initialIdentity&&current.verified){initialIdentity=current;result.firstVerifiedAtCleanup=true;}
  if(!current.verified||(initialIdentity&&current.started!==initialIdentity.started))throw Error('Refusing cleanup of an unverifiable or changed browser PID.');
  result.verifiedIdentity=current;
  result.method='Close owned CDP browser; verified exact PID/group fallback only';
  if(cdp) {await within(()=>cdp.send('Browser.close'),deadline,'Owned browser close',{interruptible:false,maxMs:5000}).catch(()=>{});cdp.close();}
  const closeDeadline=Math.min(Date.now()+3000,deadline);
  while(Date.now()<closeDeadline){if(!await inspect())break;await delay(100);}
  current=await inspect();
  if(current) {
    if(!current.verified||(initialIdentity&&current.started!==initialIdentity.started))throw Error('Refusing cleanup fallback after PID identity changed.');
    if(process.platform==='win32') {
      await execute('taskkill.exe',['/PID',String(child.pid),'/T','/F'],{timeout:Math.min(8000,remaining()),maxBuffer:65536});result.signals.push('taskkill /T /F');
    } else {process.kill(-child.pid,'SIGTERM');result.signals.push('SIGTERM');}
    const signalDeadline=Math.min(Date.now()+3000,deadline);
    while(Date.now()<signalDeadline){if(!await inspect())break;await delay(100);}
    current=await inspect();
    if(current&&process.platform!=='win32') {
      if(!current.verified||current.started!==initialIdentity.started)throw Error('Refusing unverified cleanup escalation.');
      process.kill(-child.pid,'SIGKILL');result.signals.push('SIGKILL');await delay(300);
    }
  }
  result.rootGone=(await inspect())===null;
  if(process.platform!=='win32')result.processGroupGone=await groupIsGone();
  return result;
}

try {
  const args=[`--user-data-dir=${profile}`,'--no-first-run','--no-default-browser-check','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','about:blank'];
  report.command={executable:options.browser,args};
  const log=await open(path.join(options.output,'browser.log'),'wx',0o600);
  let launchError;
  child=spawn(options.browser,args,{stdio:['ignore',log.fd,log.fd],detached:process.platform!=='win32'});
  child.once('error',error=>{launchError=error;});
  await log.close();report.ownedPid=child.pid;
  const launchDeadline=Date.now()+20000;
  while(Date.now()<launchDeadline) {
    if(interrupted)throw Error(`Interrupted by ${interrupted}`);
    if(launchError)throw launchError;
    if(child.exitCode!==null||child.signalCode!==null)throw Error('Owned browser exited during launch.');
    initialIdentity=await identity({timeoutMs:Math.max(1,Math.min(5000,launchDeadline-Date.now())),signal:abortReadHelper.signal});
    if(initialIdentity?.verified) {
      try {
        const [port,ws]= (await readFile(path.join(profile,'DevToolsActivePort'),'utf8')).trim().split(/\r?\n/);
        if(!/^\d+$/.test(port)||!ws?.startsWith('/devtools/browser/'))throw Error('Invalid owned endpoint');
        const endpoint=`ws://127.0.0.1:${port}${ws}`;
        const version=await (await fetch(`http://127.0.0.1:${port}/json/version`,{signal:AbortSignal.timeout(1000)})).json();
        if(version.webSocketDebuggerUrl!==endpoint)throw Error('Owned endpoint identity mismatch');
        // CDP.connect has its own 10-second bound; reserve it within launch.
        if(launchDeadline-Date.now()<10000)break;
        cdp=await CDP.connect(endpoint);break;
      }catch{}
    }
    await delay(100);
  }
  if(!cdp||!initialIdentity?.verified)throw Error('Owned browser/profile endpoint did not become ready.');
  report.processIdentity=initialIdentity;
  const setupDeadline=Date.now()+15000;
  const send=(method,params={},sessionId)=>within(()=>cdp.send(method,params,sessionId),setupDeadline,method);
  const version=await send('Browser.getVersion');report.observations.browserVersion=version;
  check('actual browser matches pinned reference revision',version.revision.replace(/^@/,'')===revision,version);
  const {targetInfos}=await send('Target.getTargets');
  let targetId=targetInfos.find(target=>target.type==='page'&&target.url==='about:blank')?.targetId;
  if(!targetId)({targetId}=await send('Target.createTarget',{url:'about:blank'}));
  const {sessionId}=await send('Target.attachToTarget',{targetId,flatten:true});
  await send('Page.enable',{},sessionId);
  await send('Runtime.enable',{},sessionId);
  await send('Network.enable',{},sessionId);
  await send('Accessibility.enable',{},sessionId);
  const {frameTree}=await send('Page.getFrameTree',{},sessionId);
  const documentResponses=[];
  cdp.on('Network.responseReceived',(params,source)=>{
    if(source===sessionId&&params.type==='Document'&&params.frameId===frameTree.frame.id&&documentResponses.length<10){
      documentResponses.push({url:params.response.url.slice(0,1600),status:params.response.status,mimeType:params.response.mimeType,fromServiceWorker:params.response.fromServiceWorker??false});
    }
  });
  const deadline=Date.now()+options['timeout-ms'];
  report.observations.navigation=await within(()=>cdp.send('Page.navigate',{url:listing},sessionId),deadline,'Store navigation',{maxMs:10000});
  let dom,ax,axError,completeAt,lastSignature,stableSince;
  while(Date.now()<deadline) {
    if(interrupted)throw Error(`Interrupted by ${interrupted}`);
    dom=await within(()=>cdp.evaluate(sessionId,`(${domSummary.toString()})()`),deadline,'Store DOM summary').catch(()=>null);
    if(dom?.readyState==='complete'&&dom.addCandidates.length>0) {
      completeAt??=Date.now();
      const signature=JSON.stringify(dom.addCandidates);
      if(signature!==lastSignature){lastSignature=signature;stableSince=Date.now();}
      if(Date.now()-completeAt>=3000&&Date.now()-stableSince>=1500)break;
    }
    await delay(500);
  }
  if(dom)report.observations.dom=dom;
  const finalDeadline=Date.now()+30000;
  try {ax=axSummary((await within(()=>cdp.send('Accessibility.getFullAXTree',{},sessionId),finalDeadline,'Store AX summary')).nodes);report.observations.ax=ax;}
  catch(error){axError=error.message;report.observations.ax={error:axError};}
  report.observations.documentResponses=documentResponses;
  report.observations.nativeUiPrerequisites=await within(()=>nativeUiPrerequisites(finalDeadline),finalDeadline,'Native UI prerequisites',{maxMs:15000});
  const rightListing=matchesStoreTargetUrl(dom?.url,target)&&dom.title.toLowerCase().includes(target.name.toLowerCase());
  const documentLoaded=documentResponses.some(response=>response.status>=200&&response.status<300&&matchesStoreTargetUrl(response.url,target));
  check('actual audited Store listing loaded',rightListing===true&&dom.readyState==='complete'&&documentLoaded,{url:dom?.url,readyState:dom?.readyState,documentResponses});
  check('finite DOM and AX summaries captured',Boolean(dom)&&Boolean(ax)&&!axError,{domCaptured:Boolean(dom),axCaptured:Boolean(ax),axError});
  check('Store Add button label and enabled state observed',Boolean(dom?.addCandidates.length||ax?.addCandidates.length),{dom:dom?.addCandidates??[],ax:ax?.addCandidates??[]});
  check('preflight performed no installation interaction',report.installation.attempted===false&&report.installation.addClicked===false&&report.installation.permissionDialogAccepted===false);
  report.readiness={addButtonEnabled:(dom?.addCandidates??[]).some(button=>button.visible&&button.enabled)||(ax?.addCandidates??[]).some(button=>button.enabled),
    webstorePrivateType:dom?.capabilities.webstorePrivateType??'unobserved',nativeUiStatus:report.observations.nativeUiPrerequisites.status,
    nativeWindowRoles:(report.observations.nativeUiPrerequisites.windows??[]).map(window=>window.role).slice(0,8),
    normalInstallPermissionGate:'NOT TESTED',nativeBinaryCompatibility:'NOT TESTED'};
} catch(error) {check('read-only preflight completes',false,error.stack);}
finally {
  try {report.cleanup=await cleanup();check('only verified owned browser is cleaned up',report.cleanup.rootGone===true&&report.cleanup.processGroupGone!==false,report.cleanup);}
  catch(error){report.cleanup={error:error.stack};check('only verified owned browser is cleaned up',false,error.message);}
  report.finished=new Date().toISOString();report.interrupted=interrupted;
  report.status=!interrupted&&report.tests.length>0&&report.tests.every(test=>test.status==='passed')?'passed':'failed';
  await writeFile(path.join(options.output,'results.json'),JSON.stringify(report,null,2)+'\n');
}
console.log(JSON.stringify({status:report.status,stage:report.stage,target:report.target,readiness:report.readiness,installation:report.installation,tests:report.tests.map(test=>({name:test.name,status:test.status}))}));
process.exitCode=report.status==='passed'?0:1;

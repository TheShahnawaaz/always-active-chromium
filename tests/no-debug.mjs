#!/usr/bin/env node
// Normal browser launch + passive HTTP observations. Deliberately no CDP,
// WebDriver, browser-control library, extension, or focus/lifecycle emulation.
import { spawn, execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { access, mkdir, open, readFile, realpath, writeFile } from 'node:fs/promises';
import { constants } from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';
import {captureOwnedWindow,failedStartupCaptureEnabled} from './lib/window-capture.mjs';
import {parseFailedWindowDiagnostic} from './lib/failed-window-diagnostic.mjs';
import {fileURLToPath} from 'node:url';
import {observePassiveTransport,controllerHealthGet} from './lib/passive-transport.mjs';

const execute=promisify(execFile);
const captureHelper=process.env.AA_WINDOW_CAPTURE_HELPER;
const captureMode=process.env.AA_WINDOW_CAPTURE_MODE??'native';
if(captureHelper&&!['native','control'].includes(captureMode))throw Error('Window capture mode must be native or control.');
const options={mode:'paired',output:path.resolve('.runtime/no-debug'),browser:process.env.CHROME_PATH,
  'expected-version':'156.0.8078.80','timeout-ms':'45000','settle-ms':'5000','stable-ms':'2500'};
for(let i=2;i<process.argv.length;i++) {
  const key=process.argv[i].replace(/^--/,'');
  if(!Object.hasOwn(options,key)||!process.argv[i+1])throw Error(`Unknown/missing argument: ${process.argv[i]}`);
  options[key]=process.argv[++i];
}
if(!options.browser||!['paired','control','native'].includes(options.mode))throw Error('Usage: node tests/no-debug.mjs --browser PATH --output NEW_DIR [--mode paired|control|native]');
const failedStartupCapture=failedStartupCaptureEnabled({optIn:process.env.AA_FAILED_STARTUP_CAPTURE,platform:process.platform,optionsMode:options.mode,captureMode,helper:captureHelper});
for(const key of ['timeout-ms','settle-ms','stable-ms']) {
  options[key]=Number(options[key]);
  if(!Number.isInteger(options[key])||options[key]<1000||options[key]>120000)throw Error(`Invalid ${key}`);
}
if(options['timeout-ms']<=options['settle-ms']+options['stable-ms'])throw Error('Timeout must exceed settle + stable intervals.');
if(!/^\d+\.\d+\.\d+\.\d+$/.test(options['expected-version']))throw Error('Expected version must be a full four-part version.');
options.browser=await realpath(options.browser);
options.output=path.resolve(options.output);
await access(options.browser,constants.X_OK);
// Refuse to repurpose any existing profile or report directory.
await mkdir(path.dirname(options.output),{recursive:true});
await mkdir(options.output,{recursive:false,mode:0o700});
const fixture=await readFile(new URL('./fixtures/no-debug.html',import.meta.url),'utf8');
const report={schema:1,started:new Date().toISOString(),platform:process.platform,architecture:process.arch,
  mechanism:'Normal browser CLI and passive loopback website HTTP reports',mode:options.mode,
  startupSelection:'Not assumed; control accepts whichever page supplies stable genuinely-hidden observations.',
  expectedVersion:options['expected-version'],expectedSourceRevision:'fb096c0011f9d50f0a264a9376420cdea9c421e3',
  versionObservation:'Website UA-CH fullVersionList; source revision is not observable without debugging and is not claimed by this test.',
  limits:{timeoutMs:options['timeout-ms'],settleMs:options['settle-ms'],stableMs:options['stable-ms'],maxSamplesPerPage:256,maxPostBytes:16384,maxRequestCounter:1000000,controllerHealthMs:2000,failedWindowsWindowDiagnosticMs:12000},
  runs:[],limitations:[
    'This verifies the test-owned normal launch and passive webpage observations, not a host-wide audit of unrelated processes.',
    'No remote-debugging, automation, load-extension, focus emulation, lifecycle override, or browser-control API is used.',
    'Built-in browser component extensions may exist; this test supplies no extension and uses a new profile.',
    'A native result is accepted in paired mode only when the same executable also proves a stable truly-hidden website with the master feature disabled.',
    'Source revision, UI pixels, OS sleep/freeze/discard behavior, and indefinite execution are outside this finite test.'
  ]};
let interrupted=null;
process.once('SIGINT',()=>{interrupted='SIGINT';});
process.once('SIGTERM',()=>{interrupted='SIGTERM';});

function addCheck(run,name,passed,detail) {
  run.tests.push({name,status:passed?'passed':'failed',...(detail===undefined?{}:{detail})});
  console.log(`${passed?'PASS':'FAIL'} ${run.mode}: ${name}`);
}

function stateMatches(sample,kind) {
  if(kind==='hidden')return sample.hidden===true&&sample.visibilityState==='hidden'&&sample.hasFocus===false&&sample.webkitHidden===true&&sample.webkitVisibilityState==='hidden';
  if(kind==='protected')return sample.hidden===false&&sample.visibilityState==='visible'&&sample.hasFocus===true&&sample.webkitHidden===false&&sample.webkitVisibilityState==='visible';
  return true;
}

function stableSuffix(samples,startedAt,kind) {
  const later=samples.filter(s=>s.receivedAtMs>=startedAt+options['settle-ms']&&s.elapsedMs>=options['settle-ms']);
  const suffix=[];
  for(let i=later.length-1;i>=0;i--) {
    if(!stateMatches(later[i],kind))break;
    suffix.unshift(later[i]);
  }
  const spanMs=suffix.length>1?suffix.at(-1).receivedAtMs-suffix[0].receivedAtMs:0;
  const recent=suffix.length>0&&Date.now()-suffix.at(-1).receivedAtMs<=2500;
  return {passed:suffix.length>=3&&spanMs>=options['stable-ms']&&recent,count:suffix.length,spanMs,
    latest:suffix.at(-1)??later.at(-1)??null};
}

async function processIdentity(child,profile,{timeoutMs=5000,windowsHide=false}={}) {
  if(child.exitCode!==null||child.signalCode!==null)return null;
  if(process.platform==='win32') {
    const script=`$p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$env:AA_NO_DEBUG_PID); if($null -eq $p){exit 0}; [pscustomobject]@{pid=$p.ProcessId; executable=$p.ExecutablePath; command=$p.CommandLine; started=$p.CreationDate.ToUniversalTime().ToString('o')} | ConvertTo-Json -Compress`;
    const {stdout}=await execute('powershell.exe',['-NoProfile','-NonInteractive','-Command',script],
      {timeout:timeoutMs,maxBuffer:65536,windowsHide,env:{...process.env,AA_NO_DEBUG_PID:String(child.pid)}});
    if(!stdout.trim())return null;
    const identity=JSON.parse(stdout.replace(/^\uFEFF/,''));
    const executableMatches=identity.executable?.toLowerCase()===options.browser.toLowerCase();
    return {...identity,owned:identity.pid===child.pid&&executableMatches&&identity.command?.includes(`--user-data-dir=${profile}`)};
  }
  let stdout;
  try {
    ({stdout}=await execute('ps',['-ww','-p',String(child.pid),'-o','pid=','-o','pgid=','-o','lstart=','-o','command='],{timeout:Math.min(timeoutMs,3000),maxBuffer:65536}));
  } catch(error) { if(error.code===1)return null; throw error; }
  const match=stdout.match(/^\s*(\d+)\s+(\d+)\s+(\S+\s+\S+\s+\d+\s+\S+\s+\d+)\s+(.+)\s*$/);
  if(!match)throw Error('Could not parse owned browser process identity.');
  const identity={pid:Number(match[1]),processGroup:Number(match[2]),started:match[3].trim().replace(/\s+/g,' '),command:match[4]};
  return {...identity,owned:identity.pid===child.pid&&identity.processGroup===child.pid&&identity.command.includes(options.browser)&&identity.command.includes(`--user-data-dir=${profile}`)};
}

async function failedWindowsWindowDiagnostic(child,profile,initial,args) {
  if(process.platform!=='win32')return {status:'unsupported'};
  try{
    const fresh=await processIdentity(child,profile,{timeoutMs:2000,windowsHide:true});
    const escape=value=>value.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
    const argument='--user-data-dir='+profile;
    const exactProfile=new RegExp(`(?:^|\\s)(?:"${escape(argument)}"|${escape(argument)})(?=\\s|$)`);
    if(!fresh?.owned||!initial?.owned||fresh.started!==initial.started||typeof fresh.command!=='string'||fresh.command.length>32768||!exactProfile.test(fresh.command))return {status:'unverified',reason:'fresh_owned_identity_unavailable'};
    const urls=args?.filter(arg=>/^http:\/\/127\.0\.0\.1:[0-9]{1,5}\/page\/(?:alpha|beta)\?run=[0-9a-f-]{36}$/.test(arg));
    if(urls?.length!==2)return {status:'unverified',reason:'expected_owned_urls_unavailable'};
    const script=fileURLToPath(new URL('./ui/failed-window-diagnostic.ps1',import.meta.url));
    const expected={pid:child.pid,started:initial.started};
    try{
      const {stdout}=await execute('powershell.exe',['-NoProfile','-NonInteractive','-File',script],{timeout:9500,killSignal:'SIGKILL',maxBuffer:16384,windowsHide:true,env:{...process.env,AA_NO_DEBUG_PID:String(child.pid),AA_NO_DEBUG_STARTED:fresh.started,AA_NO_DEBUG_EXECUTABLE:options.browser,AA_NO_DEBUG_COMMAND:fresh.command,AA_NO_DEBUG_URLS:JSON.stringify(urls)}});
      return parseFailedWindowDiagnostic(stdout,expected);
    }catch(error){
      // A sanitized child snapshot can survive a provider stall. It cannot prove UIA.
      if(error.killed===true&&typeof error.stdout==='string')return parseFailedWindowDiagnostic(error.stdout,expected,{timedOut:true});
      throw error;
    }
  }catch{return {status:'unavailable',reason:'bounded_owned_window_probe_failed'};}
}

async function cleanup(child,profile,initial) {
  const cleanupDeadline=Date.now()+18000;
  const remainingBudget=()=>{
    const remaining=cleanupDeadline-Date.now();
    if(remaining<100)throw Error('Owned browser cleanup exceeded its 18-second deadline; cleanup remains unverified.');
    return remaining;
  };
  const inspect=()=>processIdentity(child,profile,{timeoutMs:Math.min(2000,remainingBudget())});
  const result={ownedPid:child.pid,initialIdentity:initial,signals:[]};
  const current=await inspect();
  result.identityBeforeCleanup=current;
  if(!current) { result.rootGone=true; result.method='Owned root already exited; no signal sent'; return result; }
  // An early interrupt may precede the initial query; current executable,
  // unique profile, and owned child/group identity must still be verified.
  if(!initial&&current.owned){initial=current;result.firstVerifiedAtCleanup=true;}
  if(!initial?.owned||!current.owned||initial.started!==current.started)throw Error('Refusing cleanup: owned browser PID identity changed or could not be verified.');
  if(process.platform==='win32') {
    result.method='taskkill exact PID/tree after executable/profile/creation-time verification';
    await execute('taskkill.exe',['/PID',String(child.pid),'/T','/F'],{timeout:Math.min(8000,remainingBudget()),maxBuffer:65536});
    result.signals.push('taskkill /T /F');
  } else {
    result.method='Signals to the verified new owned process group';
    process.kill(-child.pid,'SIGTERM'); result.signals.push('SIGTERM');
  }
  const terminationDeadline=Math.min(Date.now()+5000,cleanupDeadline);
  while(Date.now()<terminationDeadline) {
    if(!await inspect())break;
    await delay(100);
  }
  let remaining=await inspect();
  if(remaining&&process.platform!=='win32') {
    if(!remaining.owned||remaining.started!==initial.started)throw Error('Refusing escalation: owned PID identity no longer matches.');
    process.kill(-child.pid,'SIGKILL'); result.signals.push('SIGKILL');
    const escalationDeadline=Math.min(Date.now()+3000,cleanupDeadline);
    while(Date.now()<escalationDeadline) { if(!await inspect())break; await delay(100); }
    remaining=await inspect();
  }
  result.rootGone=remaining===null;
  if(process.platform!=='win32') {
    // Do not signal a rootless group whose ownership can no longer be checked.
    const groupDeadline=Math.min(Date.now()+3000,cleanupDeadline);
    while(Date.now()<groupDeadline) {
      try { process.kill(-child.pid,0); result.processGroupGone=false; }
      catch(error) { if(error.code==='ESRCH'){result.processGroupGone=true;break;} throw error; }
      await delay(100);
    }
  }
  return result;
}

async function runMode(mode) {
  const startedAt=Date.now();
  const run={mode,started:new Date(startedAt).toISOString(),tests:[],pages:{alpha:[],beta:[]},received:{alpha:0,beta:0},rejectedPosts:0,
    requestCounts:{total:0,gets:0,posts:0,servedPageGets:{alpha:0,beta:0},reportPosts:0,invalidRequests:0,otherRequests:0,clientErrors:0,saturated:false}};
  const increment=(object,key)=>{if(object[key]<1000000)object[key]++;else run.requestCounts.saturated=true;};
  const count=key=>increment(run.requestCounts,key);
  report.runs.push(run);
  const token=randomUUID();
  const profile=path.join(options.output,`profile-${mode}`);
  await mkdir(profile,{mode:0o700});
  let child,identity,server,transport,appearanceAttempted=false;
  try {
    server=http.createServer(async(req,res)=>{
      if(transport.handlePrelaunchRequest(req,res))return;
      count('total');if(req.method==='GET')count('gets');if(req.method==='POST')count('posts');
      let url;
      try{if(typeof req.url!=='string'||req.url.length>2048)throw Error('invalid_request_url');url=new URL(req.url,'http://127.0.0.1');}
      catch{count('invalidRequests');res.writeHead(400).end();return;}
      if(req.method==='GET'&&url.pathname.startsWith('/page/')) {
        const pageName=url.pathname.slice('/page/'.length);
        if(!Object.hasOwn(run.pages,pageName)||url.searchParams.get('run')!==token){count('invalidRequests');res.writeHead(404).end();return;}
        increment(run.requestCounts.servedPageGets,pageName);
        res.setHeader('Content-Type','text/html; charset=utf-8'); res.setHeader('Cache-Control','no-store');
        res.end(fixture.replace('__NO_DEBUG_CONFIGURATION__',JSON.stringify({run:token,page:pageName})));return;
      }
      if(req.method==='POST'&&url.pathname==='/report') {
        count('reportPosts');
        let body='';
        try {
          for await(const chunk of req) {body+=chunk;if(Buffer.byteLength(body)>16384)throw Error('Report exceeds budget');}
          const sample=JSON.parse(body);
          if(sample.run!==token||!Object.hasOwn(run.pages,sample.page)||!Number.isInteger(sample.sequence)||!Number.isFinite(sample.elapsedMs)||typeof sample.hidden!=='boolean'||typeof sample.hasFocus!=='boolean')throw Error('Invalid report');
          delete sample.run;
          sample.receivedAtMs=Date.now();
          increment(run.received,sample.page);
          run.pages[sample.page].push(sample);
          if(run.pages[sample.page].length>256)run.pages[sample.page].shift();
          res.writeHead(204).end();
        } catch {if(run.rejectedPosts<1000000)run.rejectedPosts++;count('invalidRequests');res.writeHead(400).end();}
        return;
      }
      count('otherRequests');res.writeHead(404).end();
    });
    const healthPath=`/_controller-health/${token}`;
    transport=observePassiveTransport(server,{healthPath});
    server.on('clientError',(_error,socket)=>{if(!transport.isPrelaunchSocket(socket)){count('clientErrors');count('invalidRequests');}socket.destroy();});
    server.keepAliveTimeout=500;
    await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
    run.controllerHealth=await controllerHealthGet(server,transport,{healthPath});
    transport.startObservation();
    const origin=`http://127.0.0.1:${server.address().port}`;
    const urls=['alpha','beta'].map(pageName=>`${origin}/page/${pageName}?run=${token}`);
    const captureThisRun=Boolean(captureHelper)&&mode===captureMode;
    const args=[`--user-data-dir=${profile}`,'--no-first-run','--no-default-browser-check',...(mode==='control'?['--disable-features=AlwaysActive']:[]),...(captureThisRun?[process.platform==='darwin'?'--window-size=1000,700':'--window-size=1280,900']:[]),...urls];
    run.command={executable:options.browser,args};
    const log=await open(path.join(options.output,`${mode}-browser.log`),'wx',0o600);
    let spawnError;
    child=spawn(options.browser,args,{stdio:['ignore',log.fd,log.fd],detached:process.platform!=='win32'});
    child.once('error',error=>{spawnError=error;});
    await log.close();
    run.ownedPid=child.pid;
    const identityDeadline=Date.now()+10000;
    while(Date.now()<identityDeadline) {
      if(interrupted)throw Error(`Observation interrupted by ${interrupted}`);
      if(spawnError)throw spawnError;
      identity=await processIdentity(child,profile);
      if(identity?.owned)break;
      await delay(50);
    }
    if(!identity?.owned)throw Error('Could not verify executable/profile identity of the launched browser PID.');
    run.processIdentity=identity;
    let evaluation;
    while(Date.now()-startedAt<options['timeout-ms']) {
      if(interrupted)throw Error(`Observation interrupted by ${interrupted}`);
      if(spawnError)throw spawnError;
      if(child.exitCode!==null||child.signalCode!==null)throw Error('Owned browser exited before stable website reports.');
      const stable={alpha:stableSuffix(run.pages.alpha,startedAt,'any'),beta:stableSuffix(run.pages.beta,startedAt,'any')};
      const protectedPages={alpha:stableSuffix(run.pages.alpha,startedAt,'protected'),beta:stableSuffix(run.pages.beta,startedAt,'protected')};
      const hiddenPages={alpha:stableSuffix(run.pages.alpha,startedAt,'hidden'),beta:stableSuffix(run.pages.beta,startedAt,'hidden')};
      const genuinelyHidden=Object.keys(hiddenPages).filter(pageName=>hiddenPages[pageName].passed);
      const reportsStable=Object.values(stable).every(v=>v.passed);
      const behaviorPassed=mode==='control'?genuinelyHidden.length>0:Object.values(protectedPages).every(v=>v.passed);
      const latest=Object.values(run.pages).map(samples=>samples.at(-1));
      const versionStatuses=latest.map(sample=>sample?.versionStatus??'no-report');
      const versionsReady=latest.every(sample=>sample?.versionStatus==='resolved'&&(sample.fullVersionList??[]).some(value=>(value.brand==='Chromium'||value.brand==='Google Chrome')&&value.version===options['expected-version']));
      evaluation={stable,protectedPages,hiddenPages,genuinelyHidden,reportsStable,behaviorPassed,versionStatuses,versionsReady};
      if(reportsStable&&behaviorPassed&&versionsReady)break;
      await delay(100);
    }
    run.evaluation=evaluation;
    addCheck(run,'both websites provide stable later reports',evaluation?.reportsStable===true,evaluation?.stable);
    if(mode==='control')addCheck(run,'at least one control website is genuinely hidden and unfocused',evaluation?.genuinelyHidden.length>0,{acceptedHiddenPages:evaluation?.genuinelyHidden,hiddenPages:evaluation?.hiddenPages});
    else addCheck(run,'both websites stably report native visible and focused aliases',evaluation?.behaviorPassed===true,evaluation?.protectedPages);
    const latest=Object.values(run.pages).map(samples=>samples.at(-1));
    addCheck(run,'websites report no WebDriver automation',latest.every(s=>s?.webdriver===false),latest.map(s=>s?.webdriver??null));
    const observedVersions=latest.map(s=>(s?.fullVersionList??[]).filter(v=>v.brand==='Chromium'||v.brand==='Google Chrome').map(v=>v.version));
    addCheck(run,'website full versions match expected browser pin',latest.every(sample=>sample?.versionStatus==='resolved')&&observedVersions.every(v=>v.includes(options['expected-version'])),{observedVersions,versionStatuses:latest.map(sample=>sample?.versionStatus??'no-report')});
    let portFileExists=true;
    try {await access(path.join(profile,'DevToolsActivePort'));} catch(error) {if(error.code==='ENOENT')portFileExists=false;else throw error;}
    addCheck(run,'owned profile exposes no remote debugging port file',!portFileExists);
    addCheck(run,'normal launch has no debugging, automation, extension, or emulation flags',args.every(arg=>!/^--(?:remote-debugging|enable-automation|headless|load-extension|disable-extensions-except)/.test(arg)),args);
    if(captureThisRun){
      run.appearance={status:'not-captured',manualReview:'pending',uiEquivalenceVerified:false};
      if(run.tests.every(test=>test.status==='passed')){
        try{
          const current=await processIdentity(child,profile);
          if(current?.owned&&current.started===identity.started){appearanceAttempted=true;run.appearance=await captureOwnedWindow({helper:captureHelper,pid:child.pid,profile,executable:options.browser,started:identity.started,output:options.output});}
        }catch{run.appearance.error='capture_evidence_unavailable';}
      }
    }
  } catch(error) {
    addCheck(run,'normal-launch observation completes',false,error.stack);
  } finally {
    if(failedStartupCapture&&!appearanceAttempted&&child?.pid&&identity?.owned&&run.tests.some(test=>test.status==='failed')){
      run.appearance={status:'not-captured',captureContext:'startup-diagnostic',behaviorVerified:false,manualReview:'pending',uiEquivalenceVerified:false};
      try{
        const current=await processIdentity(child,profile,{timeoutMs:2000,windowsHide:true});
        if(current?.owned&&current.started===identity.started){appearanceAttempted=true;run.appearance=await captureOwnedWindow({helper:captureHelper,pid:child.pid,profile,executable:options.browser,started:identity.started,output:options.output,captureContext:'startup-diagnostic'});}
      }catch{run.appearance.error='capture_evidence_unavailable';}
    }
    if(process.platform==='win32'&&child?.pid&&run.tests.some(test=>test.status==='failed'))run.failedObservationWindow=await failedWindowsWindowDiagnostic(child,profile,identity,run.command?.args);
    if(child?.pid) {
      try {
        run.cleanup=await cleanup(child,profile,identity);
        addCheck(run,'verified owned browser process cleanup completes',run.cleanup.rootGone===true&&run.cleanup.processGroupGone!==false,run.cleanup);
      } catch(error) {run.cleanup={error:error.stack};addCheck(run,'verified owned browser process cleanup completes',false,error.message);}
    }
    if(server) {server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
    if(transport)run.transport=transport.snapshot();
    run.retainedSamples={alpha:run.pages.alpha.length,beta:run.pages.beta.length};
    run.finished=new Date().toISOString();
    run.status=run.tests.length>0&&run.tests.every(t=>t.status==='passed')?'passed':'failed';
    await writeFile(path.join(options.output,'results.json'),JSON.stringify(report,null,2)+'\n');
  }
}

for(const mode of options.mode==='paired'?['control','native']:[options.mode]) {
  if(interrupted)break;
  await runMode(mode);
}
report.finished=new Date().toISOString();
report.interrupted=interrupted;
report.status=!interrupted&&report.runs.length===(options.mode==='paired'?2:1)&&report.runs.every(run=>run.status==='passed')?'passed':'failed';
await writeFile(path.join(options.output,'results.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({status:report.status,mode:report.mode,runs:report.runs.map(run=>({mode:run.mode,status:run.status,checks:run.tests.length,hiddenPages:run.evaluation?.genuinelyHidden??[]}))}));
process.exitCode=report.status==='passed'?0:1;

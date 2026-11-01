#!/usr/bin/env node
import { mkdir, readFile, writeFile, cp } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';
import { launchBrowser, page } from './lib/browser.mjs';
import { serve } from './lib/site.mjs';

const here=path.dirname(fileURLToPath(import.meta.url));
const args={mode:'native',output:path.resolve('.runtime/oracle/run'),browser:process.env.CHROME_PATH};
for(let i=2;i<process.argv.length;i++) {
  const k=process.argv[i].replace(/^--/,'');
  if(!['browser','mode','output','extension','features','disable-features'].includes(k) || !process.argv[i+1]) throw Error(`Unknown/missing argument: ${process.argv[i]}`);
  args[k]=process.argv[++i];
}
if(!args.browser || !['native','baseline','oracle'].includes(args.mode)) throw Error('Usage: node tests/run.mjs --browser PATH --mode native|baseline|oracle --output DIR [--extension UNPACKED_ORACLE] [--features NAME]');
args.output=path.resolve(args.output);
if(args.mode==='oracle' && !args.extension) throw Error('Oracle mode requires the exact unpacked extension path.');
await mkdir(args.output,{recursive:true});
const profile=path.join(args.output,'profile');
// Every invocation owns a new profile. Do not accept an arbitrary existing one.
try { await mkdir(profile); } catch(e) { if(e.code==='EEXIST') throw Error(`Output already contains profile; choose a fresh output directory: ${args.output}`); throw e; }
const report={schema:1,started:new Date().toISOString(),platform:process.platform,architecture:process.arch,mode:args.mode,arguments:{features:args.features,disableFeatures:args['disable-features']},tests:[],observations:{},limitations:[
  'CDP is a test controller only; no focus emulation or lifecycle overrides are used.',
  'Headful real tabs are required. This does not substitute headless results for desktop behavior.',
  'The MV3 fixture covers unpacked extension APIs/reload/persistence/removal, not Chrome Web Store installation or automatic store updates.',
  'No claim of all-extension compatibility, DRM/private Google service compatibility, exact desktop UI pixels, OS sleep, or indefinite background execution.'
]};
let browser,site,failed=false;
const save=()=>writeFile(path.join(args.output,'results.json'),JSON.stringify(report,null,2)+'\n');
const check=(name,pass,detail)=> { report.tests.push({name,status:pass?'passed':'failed',detail}); if(!pass) failed=true; process.stdout.write(`${pass?'PASS':'FAIL'} ${name}\n`); };
const observe=(name,value)=>{report.observations[name]=value;};
const launchArgs=[...(args.features?[`--enable-features=${args.features}`]:[]),...(args['disable-features']?[`--disable-features=${args['disable-features']}`]:[]),...(args.extension?[`--load-extension=${path.resolve(args.extension)}`]:[])];
const start=()=>launchBrowser({executable:path.resolve(args.browser),profile,output:args.output,args:launchArgs});
async function worker(cdp,id) {
  for(let i=0;i<100;i++) {
    const {targetInfos}=await cdp.send('Target.getTargets');
    const target=targetInfos.find(t=>t.type==='service_worker' && t.url.startsWith(`chrome-extension://${id}/`));
    if(target) {
      const {sessionId}=await cdp.send('Target.attachToTarget',{targetId:target.targetId,flatten:true});
      await cdp.send('Runtime.enable',{},sessionId);
      for(let j=0;j<100;j++) {
        if(await cdp.evaluate(sessionId,'Boolean(globalThis.chrome?.runtime?.id && globalThis.chrome?.storage?.local)').catch(()=>false))return sessionId;
        await delay(30);
      }
      throw Error('Extension worker did not initialize its API context.');
    }
    await delay(50);
  }
  throw Error(`Extension service worker did not start: ${id}`);
}
async function oracleSetup(cdp) {
  const {targetInfos}=await cdp.send('Target.getTargets');
  let target=targetInfos.find(t=>t.type==='service_worker' && t.url.endsWith('/worker.js'));
  for(let i=0;!target && i<100;i++) { await delay(100); target=(await cdp.send('Target.getTargets')).targetInfos.find(t=>t.type==='service_worker' && t.url.endsWith('/worker.js')); }
  if(!target) throw Error('Oracle extension worker absent; this browser may reject --load-extension.');
  const id=new URL(target.url).hostname;
  const sessionId=await worker(cdp,id);
  observe('oracleId',id);
  observe('oracleInitialStorage',await cdp.evaluate(sessionId,'chrome.storage.local.get(null)'));
  await cdp.evaluate(sessionId,"chrome.storage.local.set({hosts:['*'],enabled:true,faqs:false,fullscreen:false,'mode-displayed':true})");
  for(let i=0;i<100;i++) {
    const scripts=await cdp.evaluate(sessionId,'chrome.scripting.getRegisteredContentScripts()');
    if(scripts.some(s=>s.id==='main') && scripts.some(s=>s.id==='isolated')) {
      // The shipped extension can open a separate onboarding popup on install.
      // Close that owned popup before making tabs, or CDP can choose different
      // normal windows and both "background" pages remain genuinely visible.
      await delay(300);
      await cdp.evaluate(sessionId,"(async()=>{for(const w of await chrome.windows.getAll()){if(w.type==='popup')await chrome.windows.remove(w.id);}})()");
      return {id,sessionId};
    }
    await delay(50);
  }
  throw Error('Oracle content script registration did not complete.');
}
async function extensionRequest(cdp,p,nonce) {
  await cdp.evaluate(p.sessionId,`window.mv3Reply=null; window.postMessage({source:'always-active-mv3-request',nonce:${JSON.stringify(nonce)}},location.origin)`);
  for(let i=0;i<100;i++) {
    const v=await cdp.evaluate(p.sessionId,'window.mv3Reply');
    if(v?.nonce===nonce) return v;
    await delay(30);
  }
  throw Error('MV3 content-script/worker message did not return.');
}
async function enableTestDeveloperMode(cdp) {
  const {targetId}=await cdp.send('Target.createTarget',{url:'chrome://extensions/'});
  const {sessionId}=await cdp.send('Target.attachToTarget',{targetId,flatten:true});
  for(let i=0;i<100;i++) {
    if(await cdp.evaluate(sessionId,'Boolean(globalThis.chrome?.developerPrivate?.updateProfileConfiguration)').catch(()=>false)) break;
    await delay(50);
  }
  await cdp.evaluate(sessionId,'chrome.developerPrivate.updateProfileConfiguration({inDeveloperMode:true})');
  const config=await cdp.evaluate(sessionId,'chrome.developerPrivate.getProfileConfiguration()');
  await cdp.send('Target.closeTarget',{targetId});
  if(!config?.inDeveloperMode) throw Error('Could not enable developer mode in the owned test profile.');
  observe('testProfileDeveloperMode',config.inDeveloperMode);
}
try {
  site=await serve();
  browser=await start();
  let cdp=browser.cdp;
  observe('browserVersion',await cdp.send('Browser.getVersion'));
  const oracle=args.mode==='oracle'?await oracleSetup(cdp):null;
  const p=await page(cdp,site.url+'/fixture?case=main');
  const foreground=await cdp.evaluate(p.sessionId,'({initial:initialProbe,current:readProbe()})');
  observe('foreground',foreground);
  check('first website script sees visible state',foreground.initial.hidden===false && foreground.initial.visibilityState==='visible',foreground.initial);
  await delay(500);
  await cdp.evaluate(p.sessionId,'probeEvents.length=0;startRaf()');
  await delay(250);
  const other=await page(cdp,site.url+'/fixture?case=cover');
  const mainWindow=await cdp.send('Browser.getWindowForTarget',{targetId:p.targetId});
  const coverWindow=await cdp.send('Browser.getWindowForTarget',{targetId:other.targetId});
  check('tab comparison uses one native window',mainWindow.windowId===coverWindow.windowId,{mainWindow,coverWindow});
  await cdp.send('Page.bringToFront',{},other.sessionId);
  await delay(700);
  if(oracle) {
    observe('oracleTabTopology',await cdp.evaluate(oracle.sessionId,'chrome.tabs.query({})'));
    observe('oracleWindowTopology',{main:await cdp.send('Browser.getWindowForTarget',{targetId:p.targetId}),cover:await cdp.send('Browser.getWindowForTarget',{targetId:other.targetId})});
  }
  const background=await cdp.evaluate(p.sessionId,'({current:readProbe(),events:probeEvents.slice(),preexistingRaf:stopRaf()})');
  observe('background',background);
  const protectedMode=args.mode!=='baseline';
  check('background website visibility matches mode',background.current.hidden===!protectedMode && background.current.visibilityState===(protectedMode?'visible':'hidden'),background.current);
  check('background document focus matches mode',background.current.hasFocus===protectedMode,background.current);
  if(args.mode==='oracle') check('oracle genuinely runs in a native hidden document',background.current.prototypeHidden===true,background.current);
  if(args.mode==='native') check('native tab loss does not deliver page blur/visibilitychange',!background.events.some(e=>['blur','visibilitychange','webkitvisibilitychange'].includes(e.type)&&e.trusted),background.events);
  else if(args.mode==='oracle') check('oracle blocks document listener visibility notifications',!background.events.some(e=>['visibilitychange','webkitvisibilitychange'].includes(e.type)&&e.trusted&&e.listener==='document'),background.events);
  else check('baseline genuinely lost tab visibility',background.events.some(e=>e.type==='visibilitychange'&&e.trusted),background.events);
  const frames=await cdp.evaluate(p.sessionId,'frameProbes()');
  observe('backgroundFrames',frames);
  check('same/cross/about:blank frame visibility',frames.length===3 && frames.every(f=>f.current.hidden===!protectedMode && f.current.visibilityState===(protectedMode?'visible':'hidden')),frames);
  if(protectedMode) check('same/cross/about:blank frame hasFocus',frames.every(f=>f.current.hasFocus===true),frames);
  await cdp.evaluate(p.sessionId,'startRaf()');
  await delay(1300);
  const raf=await cdp.evaluate(p.sessionId,'stopRaf()');
  observe('backgroundRafStartedWhileHidden',raf);
  check('background animation scheduling matches mode',protectedMode?raf.count>0:raf.count===0,{count:raf.count});
  check('animation callback timestamps are finite and monotonic',raf.times.every((v,i)=>Number.isFinite(v)&&(i===0||v>=raf.times[i-1])),{count:raf.count});
  await cdp.evaluate(p.sessionId,'window.cancelledRafFired=false;const cancelId=requestAnimationFrame(()=>window.cancelledRafFired=true);cancelAnimationFrame(cancelId);true');
  await delay(150);
  check('animation cancellation remains functional',await cdp.evaluate(p.sessionId,'window.cancelledRafFired')===false);
  const synthetic=await cdp.evaluate(p.sessionId,'syntheticProbe()');
  observe('syntheticEvents',synthetic);
  // Source-based tests are deliberately scoped to the extension filters. Ordinary
  // element focus/mouse events must remain available to websites.
  if(protectedMode) {
    check('document/window blur suppression',!synthetic.some(e=>e.type==='blur'&&e.target==='window'),synthetic);
    check('element focus and blur preserved',synthetic.some(e=>e.type==='focus'&&e.target==='input')&&synthetic.some(e=>e.type==='blur'&&e.target==='input'),synthetic);
    check('document-level mouseout suppression',!synthetic.some(e=>e.type==='mouseout'&&e.target==='fixture-body'),synthetic);
    check('element mouseout preserved',synthetic.some(e=>e.type==='mouseout'&&e.target==='input'),synthetic);
    check('lostpointercapture suppression',!synthetic.some(e=>e.type==='lostpointercapture'),synthetic);
  }
  await cdp.send('Page.bringToFront',{},p.sessionId);
  await delay(150);
  const ordinaryFocus=await cdp.evaluate(p.sessionId,"probeEvents.length=0;document.querySelector('#input').focus();document.querySelector('#second').focus();({active:document.activeElement.id,events:probeEvents.slice()})");
  observe('ordinaryElementFocus',ordinaryFocus);
  check('ordinary input focus transfer remains functional',ordinaryFocus.active==='second' && ordinaryFocus.events.some(e=>e.type==='blur'&&e.target==='input'&&e.trusted) && ordinaryFocus.events.some(e=>e.type==='focus'&&e.target==='second'&&e.trusted),ordinaryFocus);
  await cdp.send('Page.bringToFront',{},other.sessionId);
  await delay(150);
  const firstBackground=await page(cdp,site.url+'/fixture?case=created-background',{background:true});
  const newInitial=await cdp.evaluate(firstBackground.sessionId,'initialProbe');
  observe('newBackgroundInitial',newInitial);
  check('new background document protected before first website script',newInitial.hidden===!protectedMode && newInitial.visibilityState===(protectedMode?'visible':'hidden'),newInitial);
  const {windowId}=await cdp.send('Browser.getWindowForTarget',{targetId:p.targetId});
  await cdp.send('Browser.setWindowBounds',{windowId,bounds:{windowState:'minimized'}});
  await delay(500);
  const minimized=await cdp.evaluate(p.sessionId,'readProbe()');
  observe('minimized',minimized);
  check('minimized visibility matches mode',minimized.hidden===!protectedMode,minimized);
  await cdp.send('Browser.setWindowBounds',{windowId,bounds:{windowState:'normal'}});
  await cdp.send('Page.bringToFront',{},other.sessionId);
  // Default behavior should permit ordinary location redirects. The extension's
  // claim is broader than its reload-only implementation.
  await cdp.evaluate(p.sessionId,`location.href=${JSON.stringify(site.url+'/destination?case=background-redirect')};true`).catch(e=>{if(!e.message.includes('context'))throw e;});
  let redir;
  for(let i=0;i<50;i++) { redir=await cdp.evaluate(p.sessionId,'location.href').catch(()=>''); if(redir.includes('/destination?case=background-redirect'))break; await delay(100); }
  observe('backgroundRedirect',redir);
  check('ordinary background location redirect remains functional',redir.includes('/destination?case=background-redirect'),redir);
  const reloadBefore=site.requests.filter(r=>r.url==='/destination?case=background-redirect').length;
  const reloadDialogs=[];
  const dialogListener=(params,sessionId)=>{
    if(sessionId!==p.sessionId) return;
    reloadDialogs.push({type:params.type,message:params.message});
    cdp.send('Page.handleJavaScriptDialog',{accept:true},sessionId).catch(()=>{});
  };
  cdp.on('Page.javascriptDialogOpening',dialogListener);
  await cdp.evaluate(p.sessionId,'location.reload();true').catch(e=>{if(!e.message.includes('context'))throw e;});
  await delay(1400);
  cdp.off('Page.javascriptDialogOpening',dialogListener);
  const reloadAfter=site.requests.filter(r=>r.url==='/destination?case=background-redirect').length;
  const reloadBlocked=args.mode==='native' && (args.features??'').split(',').includes('AlwaysActiveBlockBackgroundReload');
  observe('backgroundReload',{before:reloadBefore,after:reloadAfter,dialogs:reloadDialogs});
  check('background reload matches optional policy',reloadBlocked?reloadAfter===reloadBefore:reloadAfter>reloadBefore,{reloadBefore,reloadAfter,reloadBlocked,dialogs:reloadDialogs});
  await cdp.send('Page.bringToFront',{},p.sessionId); await delay(150);
  await cdp.evaluate(p.sessionId,'location.reload();true').catch(e=>{if(!e.message.includes('context'))throw e;});
  await delay(700);
  const foregroundReload=site.requests.filter(r=>r.url==='/destination?case=background-redirect').length;
  check('foreground script reload remains functional',foregroundReload>reloadAfter,{before:reloadAfter,after:foregroundReload});
  await cdp.send('Page.bringToFront',{},other.sessionId); await delay(150);
  await cdp.send('Page.reload',{},p.sessionId); await delay(700);
  const browserReload=site.requests.filter(r=>r.url==='/destination?case=background-redirect').length;
  check('browser-initiated background reload remains functional',browserReload>foregroundReload,{before:foregroundReload,after:browserReload});

  // Fullscreen is an experimental optional feature in both the extension and
  // native implementation, so failure to enter is an explicit uncovered result.
  if(oracle) { await cdp.evaluate(oracle.sessionId,'chrome.storage.local.set({fullscreen:true})'); await delay(100); }
  const fs=await page(cdp,site.url+'/fixture?case=fullscreen');
  await cdp.send('Page.bringToFront',{},fs.sessionId);
  await delay(250);
  const entered=await cdp.evaluate(fs.sessionId,"document.documentElement.requestFullscreen().then(()=>({ok:true}),e=>({ok:false,error:e.message}))",{userGesture:true});
  observe('fullscreenEntry',entered);
  if(entered.ok) {
    await delay(500);
    const visible=await cdp.evaluate(fs.sessionId,'readProbe()');
    await cdp.send('Page.bringToFront',{},other.sessionId);
    await delay(500);
    const hidden=await cdp.evaluate(fs.sessionId,'({state:readProbe(),events:probeEvents.filter(e=>e.type.includes("fullscreen"))})');
    // Force a native API exit in the hidden document when the platform did not
    // already exit it. This tests observable state, not OS fullscreen pixels.
    const exit=await cdp.evaluate(fs.sessionId,'document.exitFullscreen().then(()=>"exited",e=>e.message)');
    await delay(200);
    const after=await cdp.evaluate(fs.sessionId,'({state:readProbe(),events:probeEvents.filter(e=>e.type.includes("fullscreen"))})');
    observe('fullscreen',{visible,hidden,exit,after});
    const optionalFullscreen=args.mode==='native' && (args.features??'').split(',').includes('AlwaysActiveFullscreen');
    if(optionalFullscreen) {
      check('optional fullscreen boolean aliases agree with element getter',after.state.fullscreen===Boolean(after.state.fullscreenElement) && after.state.webkitIsFullScreen===Boolean(after.state.fullscreenElement),after.state);
      if(after.state.fullscreenElement) check('optional fullscreen hidden snapshot retains original element',after.state.fullscreenElement===visible.fullscreenElement,{visible,after:after.state});
      else report.tests.push({name:'optional fullscreen hidden-exit snapshot',status:'not-covered',detail:'The browser cleared fullscreen during the tab switch. On macOS the baseline exits while still visible and focused, before the hidden transition. This is outside the safe hidden-exit snapshot scope; it must not be counted as a snapshot pass.'});
      const hiddenSynthetic=await cdp.evaluate(fs.sessionId,"probeEvents.length=0;for(const type of ['fullscreenchange','webkitfullscreenchange','fullscreenerror']){window.dispatchEvent(new Event(type));document.dispatchEvent(new Event(type,{bubbles:true}));}probeEvents.slice()");
      check('optional fullscreen suppresses events in hidden document',hiddenSynthetic.length===0,hiddenSynthetic);
      await cdp.send('Page.bringToFront',{},fs.sessionId); await delay(200);
      const visibleExit=await cdp.evaluate(fs.sessionId,"(async()=>{await document.documentElement.requestFullscreen();await document.exitFullscreen();return readProbe();})()",{userGesture:true});
      check('optional fullscreen preserves explicit foreground exit',visibleExit.fullscreenElement===null && visibleExit.fullscreen===false && visibleExit.webkitIsFullScreen===false,visibleExit);
    }
  } else report.limitations.push('Fullscreen could not be entered in this desktop session; fullscreen runtime behavior is unverified.');
  if(oracle) {
    // UI options which are saved but not consumed by v0.4.8's injection code.
    await cdp.evaluate(oracle.sessionId,'chrome.storage.local.set({hidden:false,visibilityState:false,fullscreen:false})');
    await delay(100);
    observe('disabledGetterPreferences',await cdp.evaluate(p.sessionId,'readProbe()'));
    await cdp.evaluate(oracle.sessionId,'chrome.storage.local.set({hosts:[]})');
    await delay(200);
    const late=await page(cdp,site.url+'/fixture?case=late');
    const before=await cdp.evaluate(late.sessionId,'readProbe()');
    await cdp.evaluate(oracle.sessionId,`(async()=>{const [tab]=await chrome.tabs.query({url:${JSON.stringify(site.url+'/fixture?case=late')}});return Promise.all([chrome.scripting.executeScript({target:{tabId:tab.id,allFrames:true},files:['data/inject/main.js'],world:'MAIN',injectImmediately:true}),chrome.scripting.executeScript({target:{tabId:tab.id,allFrames:true},files:['data/inject/isolated.js'],world:'ISOLATED',injectImmediately:true})]);})()`);
    await delay(200);
    await cdp.send('Page.bringToFront',{},other.sessionId);
    await delay(300);
    observe('lateInjection',{before,after:await cdp.evaluate(late.sessionId,'({current:readProbe(),events:probeEvents.slice()})')});
    await cdp.evaluate(oracle.sessionId,"chrome.storage.local.set({hosts:['*']})");
    await delay(200);
  }
  await save();
  // A separate, representative ordinary extension: content script -> service
  // worker -> storage -> reply, then reload, browser restart, and uninstall.
  const fixture=path.join(args.output,'mv3-fixture');
  await enableTestDeveloperMode(cdp);
  await cp(path.join(here,'fixtures/mv3'),fixture,{recursive:true});
  const loaded=await cdp.send('Extensions.loadUnpacked',{path:fixture});
  const extensionId=loaded.id;
  observe('mv3ExtensionId',extensionId);
  let ep=await page(cdp,site.url+'/fixture?case=mv3');
  const first=await extensionRequest(cdp,ep,'first');
  check('MV3 install/content-script/worker/storage messaging',first.count===1 && first.version==='1.0.0' && first.tabId,first);
  const manifest=JSON.parse(await readFile(path.join(fixture,'manifest.json'),'utf8'));
  manifest.version='1.0.1';
  await writeFile(path.join(fixture,'manifest.json'),JSON.stringify(manifest,null,2)+'\n');
  const workerSession=await worker(cdp,extensionId);
  await cdp.evaluate(workerSession,'setTimeout(()=>chrome.runtime.reload(),0);true');
  await delay(700);
  ep=await page(cdp,site.url+'/fixture?case=mv3-reload');
  const updated=await extensionRequest(cdp,ep,'updated');
  check('MV3 unpacked reload adopts changed manifest and preserves storage',updated.version==='1.0.1' && updated.count>first.count,updated);
  await browser.close(); browser=null;
  browser=await start(); cdp=browser.cdp;
  ep=await page(cdp,site.url+'/fixture?case=mv3-restart');
  const restarted=await extensionRequest(cdp,ep,'restart');
  check('MV3 survives browser restart with persistent storage',restarted.version==='1.0.1' && restarted.count>updated.count,restarted);
  await cdp.send('Extensions.uninstall',{id:extensionId});
  ep=await page(cdp,site.url+'/fixture?case=mv3-removed');
  await cdp.evaluate(ep.sessionId,"window.postMessage({source:'always-active-mv3-request',nonce:'removed'},location.origin)");
  await delay(700);
  const removed=await cdp.evaluate(ep.sessionId,'window.mv3Reply ?? null');
  check('MV3 removal stops content script execution in fresh documents',removed===null,removed);
} catch(error) {
  failed=true; report.tests.push({name:'harness completion',status:'failed',detail:error.stack});
  console.error(error.stack);
} finally {
  if(browser) await browser.close().catch(e=>report.limitations.push(`Browser cleanup: ${e.message}`));
  if(site) { observe('fixtureRequests',site.requests); await site.close(); }
  report.finished=new Date().toISOString(); report.status=failed?'failed':'passed';
  await save();
  console.log(JSON.stringify({status:report.status,resultsSha256:createHash('sha256').update(await readFile(path.join(args.output,'results.json'))).digest('hex'),tests:report.tests.length,browser:report.observations.browserVersion?.product,background:report.observations.background?.current,backgroundAnimationCount:report.observations.backgroundRafStartedWhileHidden?.count,backgroundRedirect:report.observations.backgroundRedirect,backgroundReload:report.observations.backgroundReload,fullscreen:report.observations.fullscreen,lateInjection:report.observations.lateInjection}));
  // Profiles can be useful locally for diagnosing a failed run but are never
  // uploaded by the documented CI artifact command.
}
process.exitCode=failed?1:0;

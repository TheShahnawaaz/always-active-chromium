#!/usr/bin/env node
import { mkdir, readFile, writeFile, cp } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';
import { launchBrowser, page } from './lib/browser.mjs';
import { serve } from './lib/site.mjs';
import { isExpectedWindowedWindow } from './lib/window-state.mjs';

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
function detachedDocumentProbe() {
  // These paths construct Documents without a LocalDOMWindow. They must remain
  // safe even when a native feature is disabled, since animation controllers
  // are constructed before feature eligibility is considered.
  const documents=[];
  const record=(kind,doc)=>documents.push({kind,defaultViewNull:doc.defaultView===null,
    hidden:doc.hidden,visibilityState:doc.visibilityState,hasFocus:doc.hasFocus(),
    ownsHidden:Object.hasOwn(doc,'hidden'),root:doc.documentElement?.nodeName??null});
  const html=document.implementation.createHTMLDocument('detached-title');
  html.body.innerHTML='<section id="detached-section"><span>detached html</span></section>';
  record('createHTMLDocument',html);
  const parsedHtml=new DOMParser().parseFromString('<!doctype html><title>parsed-title</title><p>parsed html</p>','text/html');
  record('DOMParser HTML',parsedHtml);
  const parsedXml=new DOMParser().parseFromString('<root><child>parsed xml</child></root>','application/xml');
  record('DOMParser XML',parsedXml);
  const xml=document.implementation.createDocument('urn:always-active-test','t:root',null);
  xml.documentElement.appendChild(xml.createElementNS('urn:always-active-test','t:child'));
  record('createDocument XML',xml);
  const clone=html.cloneNode(true);
  record('Document.cloneNode detached',clone);
  const liveClone=document.cloneNode(true);
  record('Document.cloneNode live',liveClone);
  const imported=xml.importNode(html.querySelector('section'),true);
  xml.documentElement.appendChild(imported);
  const template=document.createElement('template');
  template.innerHTML='<span data-regression="template">inert template</span><template><b>nested</b></template>';
  record('template.content ownerDocument',template.content.ownerDocument);
  const fragmentClone=template.content.cloneNode(true);
  const templateClone=template.cloneNode(true);
  const importedFragment=html.importNode(template.content,true);
  const importedTemplate=html.importNode(template,true);
  record('imported template.content ownerDocument',importedTemplate.content.ownerDocument);
  html.body.appendChild(importedFragment);
  const text=parsedHtml.importNode(document.createTextNode(' imported text'),true);
  parsedHtml.body.appendChild(text);
  const operations={
    htmlConstruction:html.title==='detached-title'&&html.querySelector('#detached-section span').textContent==='detached html',
    parsedHtml:parsedHtml.title==='parsed-title'&&parsedHtml.querySelector('p').textContent==='parsed html',
    parsedXml:parsedXml.querySelector('parsererror')===null&&parsedXml.querySelector('child').textContent==='parsed xml',
    xmlConstruction:xml.documentElement.namespaceURI==='urn:always-active-test'&&xml.documentElement.firstChild.localName==='child',
    documentClone:clone!==html&&clone.defaultView===null&&clone.querySelector('span').textContent==='detached html',
    liveDocumentClone:liveClone!==document&&liveClone.defaultView===null&&liveClone.documentElement.nodeName===document.documentElement.nodeName,
    importAcrossDocumentTypes:imported.ownerDocument===xml&&imported.querySelector('span').textContent==='detached html',
    templateOwnerIsInert:template.content.ownerDocument!==document&&template.content.ownerDocument.defaultView===null,
    fragmentClone:fragmentClone!==template.content&&fragmentClone.querySelector('span').textContent==='inert template',
    templateClone:templateClone!==template&&templateClone.content.querySelector('span').textContent==='inert template',
    fragmentImport:html.querySelector('[data-regression="template"]').ownerDocument===html,
    templateImport:importedTemplate.ownerDocument===html&&importedTemplate.content.querySelector('span').textContent==='inert template',
    nestedTemplateImport:importedTemplate.content.querySelector('template').content.querySelector('b').textContent==='nested',
    textImport:text.ownerDocument===parsedHtml&&parsedHtml.body.textContent.includes('imported text')
  };
  document.body.dataset.detachedRegressionComplete='yes';
  return {documents,operations};
}
function fullscreenFocusProbe() {
  const input=document.querySelector('#input');
  return {activeElement:document.activeElement?.id??null,actualFocus:input.matches(':focus'),
    value:input.value,selectionStart:input.selectionStart,selectionEnd:input.selectionEnd};
}
try {
  site=await serve();
  browser=await start();
  let cdp=browser.cdp;
  const browserVersion=await cdp.send('Browser.getVersion');
  observe('browserVersion',browserVersion);
  check('running browser matches pinned Chromium revision',browserVersion.revision.replace(/^@/,'')==='fb096c0011f9d50f0a264a9376420cdea9c421e3',browserVersion);
  const oracle=args.mode==='oracle'?await oracleSetup(cdp):null;
  const p=await page(cdp,site.url+'/fixture?case=main');
  const foreground=await cdp.evaluate(p.sessionId,'({initial:initialProbe,current:readProbe()})');
  observe('foreground',foreground);
  check('first website script sees visible state',foreground.initial.hidden===false && foreground.initial.visibilityState==='visible',foreground.initial);
  const detached=await cdp.evaluate(p.sessionId,`(${detachedDocumentProbe.toString()})()`);
  observe('detachedDocuments',detached);
  check('detached document creation, cloning, import, and templates complete',Object.values(detached.operations).every(Boolean),detached.operations);
  check('detached and inert owner documents keep null defaultView',detached.documents.length===8&&detached.documents.every(d=>d.defaultViewNull),detached.documents);
  check('detached documents retain normal hidden visibility',detached.documents.every(d=>d.hidden===true&&d.visibilityState==='hidden'&&!d.ownsHidden),detached.documents);
  if(args.mode!=='oracle') check('detached documents remain outside native focus spoofing',detached.documents.every(d=>d.hasFocus===false),detached.documents);
  check('renderer survives detached document operations',await cdp.evaluate(p.sessionId,"document.body.dataset.detachedRegressionComplete") === 'yes');
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
  // Measure this chain only after tab deactivation has settled. Its visible
  // callbacks accumulated earlier cannot establish continued hidden scheduling.
  const visibleStartedRafHiddenCount=await cdp.evaluate(p.sessionId,'raf.count');
  await delay(1300);
  const background=await cdp.evaluate(p.sessionId,'({current:readProbe(),cachedHasFocus:nativeHasFocus.call(document),events:probeEvents.slice(),preexistingRaf:stopRaf()})');
  observe('background',background);
  observe('visibleStartedRafHiddenProgress',{before:visibleStartedRafHiddenCount,after:background.preexistingRaf.count});
  const protectedMode=args.mode!=='baseline';
  check('background website visibility matches mode',background.current.hidden===!protectedMode && background.current.visibilityState===(protectedMode?'visible':'hidden'),background.current);
  check('background document focus matches mode',background.current.hasFocus===protectedMode,background.current);
  check('background prefixed visibility aliases match mode',background.current.webkitHidden===!protectedMode&&background.current.webkitVisibilityState===(protectedMode?'visible':'hidden'),background.current);
  const nativeBindings=args.mode==='native';
  check('cached prototype visibility getters match mode',background.current.prototypeHidden===!nativeBindings&&background.current.prototypeVisibilityState===(nativeBindings?'visible':'hidden'),background.current);
  check('cached document focus method matches mode',background.cachedHasFocus===protectedMode,{cachedHasFocus:background.cachedHasFocus});
  check('visible-started animation chain hidden progress matches mode',nativeBindings?background.preexistingRaf.count>visibleStartedRafHiddenCount:background.preexistingRaf.count===visibleStartedRafHiddenCount,{before:visibleStartedRafHiddenCount,after:background.preexistingRaf.count});
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

  // Optional native fullscreen must survive a natural tab switch at the binding
  // boundary, while actual fullscreen state and the OS window exit normally.
  const optionalFullscreen=args.mode==='native' && (args.features??'').split(',').includes('AlwaysActiveFullscreen');
  if(oracle) { await cdp.evaluate(oracle.sessionId,'chrome.storage.local.set({fullscreen:true})'); await delay(100); }
  const fs=await page(cdp,site.url+'/fixture?case=fullscreen');
  const fullscreenWindow=await cdp.send('Browser.getWindowForTarget',{targetId:fs.targetId});
  check('fullscreen tab comparison uses one native window',fullscreenWindow.windowId===coverWindow.windowId,{fullscreenWindow,coverWindow});
  observe('fullscreenWindowBeforeEntry',fullscreenWindow);
  // Target activation selects the tab/window without Page.bringToFront's extra
  // WebContents::Focus(), which would mask broken saved-focus restoration.
  await cdp.send('Target.activateTarget',{targetId:fs.targetId});
  await delay(250);
  await cdp.evaluate(fs.sessionId,"const sentinel=document.querySelector('#input');sentinel.value='fullscreen focus sentinel';sentinel.focus();sentinel.setSelectionRange(2,7);true",{userGesture:true});
  const focusExpression=`(${fullscreenFocusProbe.toString()})()`;
  const focusSentinel=await cdp.evaluate(fs.sessionId,focusExpression);
  observe('fullscreenFocusSentinel',focusSentinel);
  if(optionalFullscreen) check('optional fullscreen establishes real input focus sentinel',focusSentinel.activeElement==='input'&&focusSentinel.actualFocus===true&&focusSentinel.value==='fullscreen focus sentinel'&&focusSentinel.selectionStart===2&&focusSentinel.selectionEnd===7,focusSentinel);
  const entered=await cdp.evaluate(fs.sessionId,"document.documentElement.requestFullscreen().then(()=>({ok:true}),e=>({ok:false,error:e.message}))",{userGesture:true});
  observe('fullscreenEntry',entered);
  if(entered.ok) {
    await delay(500);
    const visible=await cdp.evaluate(fs.sessionId,'readProbe()');
    const visibleNative=await cdp.evaluate(fs.sessionId,"({cssFullscreen:document.documentElement.matches(':fullscreen'),cssFullscreenElement:document.querySelector(':fullscreen')?.id??null})");
    const visibleFocus=await cdp.evaluate(fs.sessionId,focusExpression);
    const visibleWindow=await cdp.send('Browser.getWindowForTarget',{targetId:fs.targetId});
    if(optionalFullscreen) check('optional fullscreen begins with a real active fullscreen element',visible.fullscreenElement==='fixture-root'&&visible.fullscreen===true&&visible.webkitIsFullScreen===true&&visibleNative.cssFullscreen===true,{visible,visibleNative,visibleWindow});
    if(optionalFullscreen) check('optional fullscreen keeps real input focus before deactivation',visibleFocus.activeElement===focusSentinel.activeElement&&visibleFocus.actualFocus===true&&visibleFocus.value===focusSentinel.value&&visibleFocus.selectionStart===focusSentinel.selectionStart&&visibleFocus.selectionEnd===focusSentinel.selectionEnd,{before:focusSentinel,duringFullscreen:visibleFocus});
    await cdp.evaluate(fs.sessionId,'probeEvents.length=0');
    await cdp.send('Target.activateTarget',{targetId:other.targetId});
    let hiddenNative,hiddenWindow;
    for(let i=0;i<50;i++) {
      hiddenNative=await cdp.evaluate(fs.sessionId,"({cssFullscreen:document.documentElement.matches(':fullscreen'),cssFullscreenElement:document.querySelector(':fullscreen')?.id??null})");
      hiddenWindow=await cdp.send('Browser.getWindowForTarget',{targetId:fs.targetId});
      if(!hiddenNative.cssFullscreen&&hiddenNative.cssFullscreenElement===null&&isExpectedWindowedWindow(hiddenWindow,fullscreenWindow.windowId))break;
      await delay(100);
    }
    await delay(100);
    const after=await cdp.evaluate(fs.sessionId,'({state:readProbe(),events:probeEvents.filter(e=>e.type.includes("fullscreen"))})');
    const hiddenFocus=await cdp.evaluate(fs.sessionId,focusExpression);
    observe('fullscreen',{transition:'natural-tab-switch',visible,visibleNative,visibleWindow,visibleFocus,after,hiddenNative,hiddenWindow,hiddenFocus});
    if(optionalFullscreen) {
      check('optional fullscreen natural tab switch retains original binding snapshot',after.state.fullscreenElement==='fixture-root'&&after.state.fullscreenElement===visible.fullscreenElement&&after.state.fullscreen===true&&after.state.webkitIsFullScreen===true,{visible,after:after.state});
      check('optional fullscreen natural tab switch suppresses exit notifications',after.events.length===0,after.events);
      check('optional fullscreen does not retain native CSS fullscreen state',hiddenNative.cssFullscreen===false&&hiddenNative.cssFullscreenElement===null,hiddenNative);
      check('optional fullscreen OS window exits to windowed state',isExpectedWindowedWindow(hiddenWindow,fullscreenWindow.windowId),hiddenWindow);
      check('optional fullscreen background input has no actual focus',hiddenFocus.actualFocus===false,hiddenFocus);
      const hiddenSynthetic=await cdp.evaluate(fs.sessionId,"probeEvents.length=0;for(const type of ['fullscreenchange','webkitfullscreenchange','fullscreenerror']){window.dispatchEvent(new Event(type));document.dispatchEvent(new Event(type,{bubbles:true}));}probeEvents.slice()");
      check('optional fullscreen suppresses events in hidden document',hiddenSynthetic.length===0,hiddenSynthetic);
      await cdp.send('Target.activateTarget',{targetId:fs.targetId});
      let returned,returnedWindow;
      for(let i=0;i<30;i++) {
        returned=await cdp.evaluate(fs.sessionId,`({state:readProbe(),cssFullscreen:document.documentElement.matches(':fullscreen'),focus:${focusExpression}})`);
        returnedWindow=await cdp.send('Browser.getWindowForTarget',{targetId:fs.targetId});
        if(returned.state.fullscreenElement===null&&returned.state.fullscreen===false&&returned.state.webkitIsFullScreen===false&&!returned.cssFullscreen&&returned.focus.activeElement===focusSentinel.activeElement&&returned.focus.actualFocus===true&&returned.focus.value===focusSentinel.value&&returned.focus.selectionStart===focusSentinel.selectionStart&&returned.focus.selectionEnd===focusSentinel.selectionEnd&&isExpectedWindowedWindow(returnedWindow,fullscreenWindow.windowId))break;
        await delay(100);
      }
      observe('fullscreenReturnedForeground',returned);
      observe('fullscreenReturnedWindow',returnedWindow);
      check('optional fullscreen returning foreground clears snapshot',returned.state.fullscreenElement===null&&returned.state.fullscreen===false&&returned.state.webkitIsFullScreen===false&&returned.cssFullscreen===false&&isExpectedWindowedWindow(returnedWindow,fullscreenWindow.windowId),{returned,returnedWindow});
      check('optional fullscreen tab activation restores real input focus without refocusing',returned.focus.activeElement==='input'&&returned.focus.activeElement===focusSentinel.activeElement&&returned.focus.actualFocus===true&&returned.focus.value===focusSentinel.value&&returned.focus.selectionStart===focusSentinel.selectionStart&&returned.focus.selectionEnd===focusSentinel.selectionEnd,{before:focusSentinel,duringFullscreen:visibleFocus,returned:returned.focus});
      await cdp.send('Target.activateTarget',{targetId:other.targetId}); await delay(200);
      const hiddenAgain=await cdp.evaluate(fs.sessionId,"({state:readProbe(),cssFullscreen:document.documentElement.matches(':fullscreen')})");
      observe('fullscreenHiddenAgain',hiddenAgain);
      check('optional fullscreen later hide does not resurrect snapshot',hiddenAgain.state.fullscreenElement===null&&hiddenAgain.state.fullscreen===false&&hiddenAgain.state.webkitIsFullScreen===false&&hiddenAgain.cssFullscreen===false,hiddenAgain);
      await cdp.send('Target.activateTarget',{targetId:fs.targetId}); await delay(150);
      const visibleExit=await cdp.evaluate(fs.sessionId,"(async()=>{await document.documentElement.requestFullscreen();await document.exitFullscreen();return readProbe();})()",{userGesture:true});
      check('optional fullscreen preserves explicit foreground exit',visibleExit.fullscreenElement===null && visibleExit.fullscreen===false && visibleExit.webkitIsFullScreen===false,visibleExit);
      let visibleExitNative,visibleExitWindow;
      for(let i=0;i<50;i++) {
        visibleExitNative=await cdp.evaluate(fs.sessionId,"document.documentElement.matches(':fullscreen')");
        visibleExitWindow=await cdp.send('Browser.getWindowForTarget',{targetId:fs.targetId});
        if(!visibleExitNative&&isExpectedWindowedWindow(visibleExitWindow,fullscreenWindow.windowId))break;
        await delay(100);
      }
      check('optional fullscreen explicit foreground exit clears actual fullscreen',visibleExitNative===false&&isExpectedWindowedWindow(visibleExitWindow,fullscreenWindow.windowId),{cssFullscreen:visibleExitNative,window:visibleExitWindow});

      // Exercise supported queued activation, not synthetic reentrant browser
      // observers. CDP.send writes ordered WebSocket frames synchronously; queue
      // both activations before awaiting acknowledgements, with no focus calls.
      const rapidEntry=await cdp.evaluate(fs.sessionId,"document.documentElement.requestFullscreen().then(()=>({ok:true}),e=>({ok:false,error:e.message}))",{userGesture:true});
      observe('fullscreenRapidEntry',rapidEntry);
      if(rapidEntry.ok) {
        let rapidBefore;
        for(let i=0;i<30;i++) {
          rapidBefore=await cdp.evaluate(fs.sessionId,`({state:readProbe(),cssFullscreen:document.documentElement.matches(':fullscreen'),focus:${focusExpression}})`);
          if(rapidBefore.cssFullscreen&&rapidBefore.state.fullscreenElement==='fixture-root')break;
          await delay(100);
        }
        check('rapid tab activation starts from real fullscreen and focused input',rapidBefore.cssFullscreen===true&&rapidBefore.state.fullscreenElement==='fixture-root'&&rapidBefore.focus.activeElement===focusSentinel.activeElement&&rapidBefore.focus.actualFocus===true&&rapidBefore.focus.value===focusSentinel.value&&rapidBefore.focus.selectionStart===focusSentinel.selectionStart&&rapidBefore.focus.selectionEnd===focusSentinel.selectionEnd,{rapidBefore,focusSentinel});
        await cdp.evaluate(fs.sessionId,'probeEvents.length=0');
        const rapidStarted=Date.now();
        const activateCover=cdp.send('Target.activateTarget',{targetId:other.targetId});
        const activateOriginal=cdp.send('Target.activateTarget',{targetId:fs.targetId});
        await Promise.all([activateCover,activateOriginal]);
        const activationElapsedMs=Date.now()-rapidStarted;
        let rapidAfter,rapidWindow;
        for(let i=0;i<50;i++) {
          rapidAfter=await cdp.evaluate(fs.sessionId,`({state:readProbe(),cssFullscreen:document.documentElement.matches(':fullscreen'),focus:${focusExpression},events:probeEvents.filter(e=>e.type.includes('fullscreen'))})`);
          rapidWindow=await cdp.send('Browser.getWindowForTarget',{targetId:fs.targetId});
          if(!rapidAfter.cssFullscreen&&rapidAfter.state.fullscreenElement===null&&rapidAfter.state.fullscreen===false&&rapidAfter.state.webkitIsFullScreen===false&&rapidAfter.focus.activeElement===focusSentinel.activeElement&&rapidAfter.focus.actualFocus&&rapidAfter.focus.value===focusSentinel.value&&rapidAfter.focus.selectionStart===focusSentinel.selectionStart&&rapidAfter.focus.selectionEnd===focusSentinel.selectionEnd&&isExpectedWindowedWindow(rapidWindow,fullscreenWindow.windowId))break;
          await delay(100);
        }
        observe('fullscreenRapidActivation',{before:rapidBefore,after:rapidAfter,window:rapidWindow,activationElapsedMs});
        check('rapid tab activation exits actual fullscreen and clears foreground snapshot',rapidAfter.cssFullscreen===false&&rapidAfter.state.fullscreenElement===null&&rapidAfter.state.fullscreen===false&&rapidAfter.state.webkitIsFullScreen===false&&isExpectedWindowedWindow(rapidWindow,fullscreenWindow.windowId),{rapidAfter,rapidWindow});
        check('rapid tab activation preserves actual input focus and selection',rapidAfter.focus.activeElement===focusSentinel.activeElement&&rapidAfter.focus.actualFocus===true&&rapidAfter.focus.value===focusSentinel.value&&rapidAfter.focus.selectionStart===focusSentinel.selectionStart&&rapidAfter.focus.selectionEnd===focusSentinel.selectionEnd,{before:focusSentinel,after:rapidAfter.focus});
        await cdp.send('Target.activateTarget',{targetId:other.targetId}); await delay(200);
        const rapidHiddenAgain=await cdp.evaluate(fs.sessionId,"({state:readProbe(),cssFullscreen:document.documentElement.matches(':fullscreen')})");
        observe('fullscreenRapidHiddenAgain',rapidHiddenAgain);
        check('rapid tab activation leaves no snapshot to resurrect on later hide',rapidHiddenAgain.state.fullscreenElement===null&&rapidHiddenAgain.state.fullscreen===false&&rapidHiddenAgain.state.webkitIsFullScreen===false&&rapidHiddenAgain.cssFullscreen===false,rapidHiddenAgain);
        await cdp.send('Target.activateTarget',{targetId:fs.targetId});
      } else check('rapid tab activation scenario can enter real fullscreen',false,rapidEntry);
    } else {
      if(args.mode!=='oracle') check('default or master-disabled fullscreen preserves windowed exit state',after.state.fullscreenElement===null&&after.state.fullscreen===false&&after.state.webkitIsFullScreen===false&&hiddenNative.cssFullscreen===false&&hiddenNative.cssFullscreenElement===null&&isExpectedWindowedWindow(hiddenWindow,fullscreenWindow.windowId),{after,hiddenNative,hiddenWindow});
      // References only observe restoration here; their fullscreen contract is
      // not the new optional native snapshot contract.
      await cdp.send('Target.activateTarget',{targetId:fs.targetId}); await delay(200);
      observe('fullscreenReturnedForeground',await cdp.evaluate(fs.sessionId,`({state:readProbe(),cssFullscreen:document.documentElement.matches(':fullscreen'),focus:${focusExpression}})`));
      observe('fullscreenReturnedWindow',await cdp.send('Browser.getWindowForTarget',{targetId:fs.targetId}));
    }
  } else {
    report.limitations.push('Fullscreen could not be entered in this desktop session; fullscreen runtime behavior is unverified.');
    if(optionalFullscreen) check('optional fullscreen scenario can enter real fullscreen',false,entered);
  }
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

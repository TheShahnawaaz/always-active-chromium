// Test-only minimal Store launcher. No unsafe extension/debugging switches,
// emulation, test auto-confirm, policy changes, or app-name-wide cleanup.
import { spawn, execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdir, open, readFile, realpath } from 'node:fs/promises';
import path from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { CDP } from './cdp.mjs';
const execute=promisify(execFile);

export async function storeOperation(action,deadline,label,{maxMs=5000,signal}={}) {
  const timeoutMs=Math.min(maxMs,deadline-Date.now());
  if(timeoutMs<=0)throw Error(`${label}: phase deadline exceeded`);
  if(signal?.aborted)throw Error(`${label}: interrupted`);
  let timer,onAbort;
  const timeout=new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error(`${label}: timed out`)),timeoutMs);});
  const aborted=new Promise((_,reject)=>{onAbort=()=>reject(Error(`${label}: interrupted`));signal?.addEventListener('abort',onAbort,{once:true});});
  try{return await Promise.race([Promise.resolve().then(action),timeout,aborted]);}
  finally{clearTimeout(timer);signal?.removeEventListener('abort',onAbort);}
}

async function processIdentity(browser,timeoutMs=3000,signal) {
  const child=browser.child;
  if(!child?.pid||child.exitCode!==null||child.signalCode!==null)return null;
  if(process.platform==='win32') {
    const script="$p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$env:AA_OWNED_STORE_PID);if($null -eq $p){exit 0};[pscustomobject]@{pid=$p.ProcessId;executable=$p.ExecutablePath;command=$p.CommandLine;started=$p.CreationDate.ToUniversalTime().ToString('o')}|ConvertTo-Json -Compress";
    const {stdout}=await execute('powershell.exe',['-NoProfile','-NonInteractive','-Command',script],{timeout:timeoutMs,maxBuffer:65536,signal,env:{...process.env,AA_OWNED_STORE_PID:String(child.pid)}});
    if(!stdout.trim())return null;
    const identity=JSON.parse(stdout.replace(/^\uFEFF/,''));
    return {...identity,verified:identity.pid===child.pid&&identity.executable?.toLowerCase()===browser.executable.toLowerCase()&&identity.command?.includes(`--user-data-dir=${browser.profile}`)};
  }
  let stdout;
  try {({stdout}=await execute('ps',['-ww','-p',String(child.pid),'-o','pid=','-o','pgid=','-o','lstart=','-o','command='],{timeout:timeoutMs,maxBuffer:65536,signal}));}
  catch(error){if(error.code===1)return null;throw error;}
  const match=stdout.match(/^\s*(\d+)\s+(\d+)\s+(\S+\s+\S+\s+\d+\s+\S+\s+\d+)\s+(.+)\s*$/);
  if(!match)throw Error('Cannot parse owned Store process identity');
  return {pid:Number(match[1]),processGroup:Number(match[2]),started:match[3].trim().replace(/\s+/g,' '),command:match[4],
    verified:Number(match[1])===child.pid&&Number(match[2])===child.pid&&match[4].includes(browser.executable)&&match[4].includes(`--user-data-dir=${browser.profile}`)};
}

async function closeOwned(browser) {
  const deadline=Date.now()+18000;
  const remaining=()=>{const ms=deadline-Date.now();if(ms<100)throw Error('Owned Store cleanup exceeded 18 seconds');return ms;};
  const inspect=()=>processIdentity(browser,Math.min(2000,remaining()));
  const groupGone=async()=>{
    const until=Math.min(Date.now()+3000,deadline);
    while(Date.now()<until){try{process.kill(-browser.child.pid,0);}catch(error){if(error.code==='ESRCH')return true;throw error;}await delay(100);}
    return false;
  };
  const result={ownedPid:browser.child?.pid,signals:[],browserCloseRequested:false};
  if(!browser.child?.pid)return {...result,rootGone:true};
  let identity=await inspect();
  if(identity) {
    if(!browser.identity&&identity.verified)browser.identity=identity;
    if(!identity.verified||identity.started!==browser.identity?.started)throw Error('Refusing cleanup: Store PID/profile/start identity is unverified');
    result.verifiedIdentity=identity;
    if(browser.cdp) {
      result.browserCloseRequested=true;
      await storeOperation(()=>browser.cdp.send('Browser.close'),deadline,'Close owned Store browser',{maxMs:5000}).catch(error=>{result.browserCloseError=error.message;});
      browser.cdp.close();
    }
    const until=Math.min(Date.now()+3000,deadline);
    while(Date.now()<until){if(!await inspect())break;await delay(100);}
    identity=await inspect();
    if(identity) {
      if(!identity.verified||identity.started!==browser.identity.started)throw Error('Refusing fallback cleanup of changed Store PID');
      if(process.platform==='win32'){await execute('taskkill.exe',['/PID',String(browser.child.pid),'/T','/F'],{timeout:Math.min(8000,remaining()),maxBuffer:65536});result.signals.push('taskkill /T /F');}
      else {process.kill(-browser.child.pid,'SIGTERM');result.signals.push('SIGTERM');}
      const signalUntil=Math.min(Date.now()+3000,deadline);
      while(Date.now()<signalUntil){if(!await inspect())break;await delay(100);}
      identity=await inspect();
      if(identity&&process.platform!=='win32') {
        if(!identity.verified||identity.started!==browser.identity.started)throw Error('Refusing unverified Store cleanup escalation');
        process.kill(-browser.child.pid,'SIGKILL');result.signals.push('SIGKILL');await delay(200);
      }
    }
  }
  result.rootGone=(await inspect())===null;
  if(process.platform!=='win32')result.processGroupGone=await groupGone();
  result.closedNormally=result.browserCloseRequested&&result.signals.length===0&&result.rootGone===true&&result.processGroupGone!==false;
  return result;
}

export async function launchOwnedStoreBrowser({executable,output,signal}) {
  executable=await realpath(executable);
  const profile=path.join(output,'profile');await mkdir(profile,{mode:0o700});
  const args=[`--user-data-dir=${profile}`,'--no-first-run','--no-default-browser-check','--window-size=1280,900','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','about:blank'];
  const browser={executable,profile,args,async close(){return closeOwned(browser);}};
  const log=await open(path.join(output,'browser.log'),'wx',0o600);
  let launchError;
  browser.child=spawn(executable,args,{stdio:['ignore',log.fd,log.fd],detached:process.platform!=='win32'});
  browser.child.once('error',error=>{launchError=error;});await log.close();
  try {
    const deadline=Date.now()+20000;
    while(Date.now()<deadline) {
      if(signal?.aborted)throw Error('Store launch interrupted');
      if(launchError)throw launchError;
      browser.identity=await processIdentity(browser,Math.max(1,Math.min(3000,deadline-Date.now())),signal);
      if(browser.identity?.verified) {
        try {
          const [port,ws]=(await readFile(path.join(profile,'DevToolsActivePort'),'utf8')).trim().split(/\r?\n/);
          if(!/^\d+$/.test(port)||!ws?.startsWith('/devtools/browser/'))throw Error('Invalid owned endpoint');
          const endpoint=`ws://127.0.0.1:${port}${ws}`;
          const version=await (await fetch(`http://127.0.0.1:${port}/json/version`,{signal:AbortSignal.timeout(Math.max(1,Math.min(1000,deadline-Date.now())))})).json();
          if(version.webSocketDebuggerUrl!==endpoint)throw Error('Owned endpoint identity mismatch');
          if(deadline-Date.now()<10000)break;
          browser.cdp=await CDP.connect(endpoint);
          return browser;
        }catch{}
      }
      await delay(100);
    }
    throw Error('Owned Store browser endpoint did not become ready');
  }catch(error){try{error.cleanup=await browser.close();}catch(cleanupError){error.cleanup={error:cleanupError.message};}throw error;}
}

export async function probeOwnedStoreUi(browser,{mode='preflight',deadline,signal}={}) {
  const helper=process.env.AA_STORE_UI_HELPER;
  if(!helper)return {schema:1,status:'unsupported',reason:'AA_STORE_UI_HELPER not configured',mode};
  if(!['preflight','dialog'].includes(mode))throw Error('Unsupported read-only Store UI mode');
  const command=process.platform==='win32'?'powershell.exe':helper;
  const args=process.platform==='win32'?['-NoProfile','-NonInteractive','-File',helper,'-PidValue',String(browser.child.pid),'-Profile',browser.profile,'-Executable',browser.executable,'-Mode',mode]:['--pid',String(browser.child.pid),'--profile',browser.profile,'--executable',browser.executable,'--mode',mode];
  try {
    const timeout=Math.min(15000,deadline-Date.now());if(timeout<=0)throw Error('UI prerequisite phase deadline exceeded');
    const {stdout}=await execute(command,args,{timeout,maxBuffer:65536,signal});
    const result=JSON.parse(stdout.replace(/^\uFEFF/,''));
    if(result.schema!==1||!['ready','untrusted','unsupported','error'].includes(result.status))throw Error('Unexpected native UI helper response');
    if(result.status==='ready'&&result.identity?.verified!==true)throw Error('Native UI helper readiness lacks owned identity');
    return result;
  }catch(error){return {schema:1,status:'error',mode,error:error.message.slice(0,1000)};}
}

// Test-only minimal Store launcher. No unsafe extension/debugging switches,
// emulation, test auto-confirm, policy changes, or app-name-wide cleanup.
import { spawn, execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdir, open, readFile, realpath, lstat, unlink } from 'node:fs/promises';
import path from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { CDP } from './cdp.mjs';
const execute=promisify(execFile);
const ownedStates=new WeakMap();
const isWindows=process.platform==='win32';
const MAX_TRACKED_PROCESSES=128;

function immutable(value) {
  if(value&&typeof value==='object'&&!Object.isFrozen(value)) {
    for(const item of Object.values(value))immutable(item);
    Object.freeze(value);
  }
  return value;
}

function ownedState(handle) {
  const state=ownedStates.get(handle);
  if(!state)throw Error('An original launcher-created owned Store handle is required');
  return state;
}

async function directoryIdentity(directory) {
  const stat=await lstat(directory,{bigint:true});
  if(stat.isSymbolicLink()||!stat.isDirectory())throw Error('Owned Store directory is no longer a real directory');
  return `${stat.dev}:${stat.ino}`;
}

async function executableIdentity(executable) {
  const stat=await lstat(executable,{bigint:true});
  if(stat.isSymbolicLink()||!stat.isFile())throw Error('Owned Store executable is no longer a regular file');
  return `${stat.dev}:${stat.ino}:${stat.size}:${stat.mtimeNs}`;
}

async function assertOwnedProfile(state) {
  if(await realpath(state.output)!==state.output||await directoryIdentity(state.output)!==state.outputIdentity||
     await realpath(state.profile)!==state.profile||await directoryIdentity(state.profile)!==state.profileIdentity||
     await realpath(state.executable)!==state.executable||await executableIdentity(state.executable)!==state.executableIdentity)throw Error('Refusing reuse of a replaced owned Store directory or executable');
}

// Query only descendants of a verified current root. No all-process inventory
// or command lines from unrelated applications are collected.
const windowsTreeScript=String.raw`
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
$root=Get-CimInstance Win32_Process -Filter ('ProcessId='+$env:AA_OWNED_STORE_PID) -OperationTimeoutSec 2
if($null -eq $root -or $root.CreationDate.ToUniversalTime().ToString('o') -cne $env:AA_OWNED_STORE_STARTED){throw 'Owned root changed before descendant snapshot'}
$queue=New-Object 'System.Collections.Generic.Queue[object]';$queue.Enqueue(@{pid=$root.ProcessId;started=$env:AA_OWNED_STORE_STARTED;depth=0})
$seen=@{};$rows=New-Object 'System.Collections.Generic.List[object]';$complete=$true;$clock=[Diagnostics.Stopwatch]::StartNew()
$base=[IO.Path]::GetDirectoryName($env:AA_OWNED_STORE_EXECUTABLE).TrimEnd([IO.Path]::DirectorySeparatorChar)+[IO.Path]::DirectorySeparatorChar
while($queue.Count -gt 0){
 if($clock.ElapsedMilliseconds -gt 2500 -or $rows.Count -ge 64){$complete=$false;break}
 $parent=$queue.Dequeue();if($seen.ContainsKey([string]$parent.pid)){continue};$seen[[string]$parent.pid]=$true
 if($parent.depth -ge 8){$complete=$false;continue}
 $current=Get-CimInstance Win32_Process -Filter ('ProcessId='+$parent.pid) -OperationTimeoutSec 2
 if($null -eq $current -or $current.CreationDate.ToUniversalTime().ToString('o') -cne $parent.started){$complete=$false;continue}
 $children=@(Get-CimInstance Win32_Process -Filter ('ParentProcessId='+$parent.pid) -OperationTimeoutSec 2)
 foreach($child in $children){
  if($rows.Count -ge 64){$complete=$false;break}
  $started=$child.CreationDate.ToUniversalTime().ToString('o');$exe=[string]$child.ExecutablePath
  $verified=$exe.Length -gt 0 -and $exe.Length -le 4096 -and $exe.StartsWith($base,[StringComparison]::OrdinalIgnoreCase) -and $child.CreationDate -ge $root.CreationDate
  $rows.Add([pscustomobject]@{pid=[int]$child.ProcessId;parentPid=[int]$child.ParentProcessId;started=$started;executable=$(if($verified){$exe}else{''});verified=$verified})
  if(-not $verified){$complete=$false;continue}
  $queue.Enqueue(@{pid=$child.ProcessId;started=$started;depth=$parent.depth+1})
 }
}
[pscustomobject]@{complete=$complete;records=$rows.ToArray()}|ConvertTo-Json -Depth 6 -Compress
`;

const windowsRemainingScript=String.raw`
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
$json=[string]$env:AA_OWNED_STORE_TRACKED
if($json.Length -gt 32768 -or -not $json.TrimStart().StartsWith('[')){throw 'Owned tracked identities must be a bounded JSON array'}
$parsed=ConvertFrom-Json -InputObject $json
$expected=New-Object 'System.Collections.Generic.List[object]';$keys=@{}
foreach($item in $parsed){
 if($null -eq $item -or $item -is [System.Array] -or $item -isnot [pscustomobject]){throw 'Owned tracked record must be a flat object'}
 $names=@($item.PSObject.Properties.Name)
 if($names.Count -ne 2 -or -not ($names -ccontains 'pid') -or -not ($names -ccontains 'started')){throw 'Owned tracked record has unexpected fields'}
 $number=0
 if($item.pid -is [System.Array] -or -not [int]::TryParse([string]$item.pid,[ref]$number) -or $number -le 1){throw 'Owned tracked PID is invalid'}
 if($item.started -isnot [string] -or $item.started.Length -lt 1 -or $item.started.Length -gt 80){throw 'Owned tracked creation identity is invalid'}
 $key=[string]$number+'|'+$item.started
 if($keys.ContainsKey($key)){throw 'Owned tracked identity is duplicated'};$keys[$key]=$true
 $expected.Add([pscustomobject]@{pid=$number;started=$item.started})
 if($expected.Count -gt 128){throw 'Owned process identity bound exceeded'}
}
if($expected.Count -eq 0){throw 'Owned process identities are empty'}
$rows=New-Object 'System.Collections.Generic.List[object]'
if($expected.Count -gt 0){
 $clauses=New-Object 'System.Collections.Generic.List[string]'
 foreach($item in $expected){$clauses.Add('ProcessId='+$item.pid)}
 $filter=[string]::Join(' OR ',$clauses.ToArray())
 $current=@(Get-CimInstance Win32_Process -Filter $filter -OperationTimeoutSec 2)
 foreach($item in $expected){
  $process=$current|Where-Object {$_.ProcessId -eq $item.pid}|Select-Object -First 1
  if($null -eq $process){$state='gone'}elseif($process.CreationDate.ToUniversalTime().ToString('o') -cne $item.started){$state='reused'}else{$state='alive'}
  $rows.Add([pscustomobject]@{pid=[int]$item.pid;started=$item.started;state=$state})
 }
}
ConvertTo-Json -InputObject $rows.ToArray() -Compress
`;

async function windowsSnapshot(state,deadline) {
  const {stdout}=await execute('powershell.exe',['-NoProfile','-NonInteractive','-Command',windowsTreeScript],{
    timeout:Math.max(1,Math.min(5000,deadline-Date.now())),maxBuffer:524288,
    env:{...process.env,AA_OWNED_STORE_PID:String(state.ownedPid),AA_OWNED_STORE_STARTED:state.identity.started,AA_OWNED_STORE_EXECUTABLE:state.executable}});
  const snapshot=JSON.parse(stdout.replace(/^\uFEFF/,''));
  if(!Array.isArray(snapshot.records)||snapshot.records.length>64)throw Error('Invalid owned descendant snapshot');
  for(const record of snapshot.records) {
    if(!Number.isInteger(record.pid)||record.pid<=1||typeof record.started!=='string'||record.started.length>80)throw Error('Invalid owned descendant identity');
    state.tracked.set(`${record.pid}:${record.started}`,record);
  }
  if(state.tracked.size>=MAX_TRACKED_PROCESSES)throw Error('Owned descendant lifetime bound exceeded');
  const complete=snapshot.complete===true&&[...state.tracked.values()].every(record=>record.verified===true);
  if(!complete)state.treeEverIncomplete=true;
  state.treeComplete=complete&&!state.treeEverIncomplete;
  return {complete:state.treeComplete,observed:snapshot.records.length,tracked:state.tracked.size};
}

async function windowsRemaining(state,deadline) {
  const records=[{pid:state.ownedPid,started:state.identity?.started},...[...state.tracked.values()].map(({pid,started})=>({pid,started}))];
  if(records.some(record=>!record.started)||records.length>MAX_TRACKED_PROCESSES)throw Error('Owned process tracking is incomplete');
  const {stdout}=await execute('powershell.exe',['-NoProfile','-NonInteractive','-Command',windowsRemainingScript],{
    timeout:Math.max(1,Math.min(3000,deadline-Date.now())),maxBuffer:65536,
    env:{...process.env,AA_OWNED_STORE_TRACKED:JSON.stringify(records)}});
  const parsed=JSON.parse(stdout.replace(/^\uFEFF/,''));
  const rows=Array.isArray(parsed)?parsed:[parsed];
  if(rows.length!==records.length||rows.some((row,index)=>row.pid!==records[index].pid||row.started!==records[index].started||!['gone','reused','alive'].includes(row.state)))throw Error('Invalid owned shutdown identity probe');
  return {gone:rows.every(row=>row.state!=='alive'),alive:rows.filter(row=>row.state==='alive'),reusedPids:rows.filter(row=>row.state==='reused').map(row=>row.pid),checked:rows.length};
}

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
  const pid=browser.ownedPid;
  if(!pid||child.exitCode!==null||child.signalCode!==null)return null;
  if(process.platform==='win32') {
    const script="$p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$env:AA_OWNED_STORE_PID);if($null -eq $p){exit 0};[pscustomobject]@{pid=$p.ProcessId;executable=$p.ExecutablePath;command=$p.CommandLine;started=$p.CreationDate.ToUniversalTime().ToString('o')}|ConvertTo-Json -Compress";
    const {stdout}=await execute('powershell.exe',['-NoProfile','-NonInteractive','-Command',script],{timeout:timeoutMs,maxBuffer:65536,signal,env:{...process.env,AA_OWNED_STORE_PID:String(pid)}});
    if(!stdout.trim())return null;
    const identity=JSON.parse(stdout.replace(/^\uFEFF/,''));
    const escape=value=>value.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
    const profileArgument=`--user-data-dir=${browser.profile}`;
    const exactProfile=new RegExp(`(?:^|\\s)(?:"${escape(profileArgument)}"|${escape(profileArgument)})(?=\\s|$)`);
    return {...identity,verified:identity.pid===pid&&identity.executable?.toLowerCase()===browser.executable.toLowerCase()&&exactProfile.test(identity.command??'')};
  }
  let stdout;
  try {({stdout}=await execute('ps',['-ww','-p',String(pid),'-o','pid=','-o','pgid=','-o','lstart=','-o','command='],{timeout:timeoutMs,maxBuffer:65536,signal}));}
  catch(error){if(error.code===1)return null;throw error;}
  const match=stdout.match(/^\s*(\d+)\s+(\d+)\s+(\S+\s+\S+\s+\d+\s+\S+\s+\d+)\s+(.+)\s*$/);
  if(!match)throw Error('Cannot parse owned Store process identity');
  return {pid:Number(match[1]),processGroup:Number(match[2]),started:match[3].trim().replace(/\s+/g,' '),command:match[4],
    verified:Number(match[1])===pid&&Number(match[2])===pid&&match[4]===[browser.executable,...browser.args].join(' ')};
}

async function closeOwned(browser,{deadline:outerDeadline=Date.now()+18000}={}) {
  if(browser.closed)return browser.lastClose;
  const deadline=Math.min(Date.now()+18000,outerDeadline);
  const remaining=()=>{const ms=deadline-Date.now();if(ms<100)throw Error('Owned Store cleanup exceeded 18 seconds');return ms;};
  const inspect=()=>processIdentity(browser,Math.min(2000,remaining()));
  const groupGone=async()=>{
    const until=Math.min(Date.now()+3000,deadline);
    while(Date.now()<until){try{process.kill(-browser.ownedPid,0);}catch(error){if(error.code==='ESRCH')return true;throw error;}await delay(100);}
    return false;
  };
  const result={ownedPid:browser.ownedPid,generation:browser.generation,signals:[],browserCloseRequested:false};
  if(!browser.ownedPid)return {...result,rootGone:true,closedNormally:false};
  let identity=await inspect();
  if(identity) {
    if(!browser.identity&&identity.verified)browser.identity=identity;
    if(!identity.verified||identity.started!==browser.identity?.started)throw Error('Refusing cleanup: Store PID/profile/start identity is unverified');
    result.verifiedIdentity=identity;
    if(isWindows) {
      try {result.descendantSnapshot=await windowsSnapshot(browser,deadline);}
      catch(error){browser.treeComplete=false;browser.treeEverIncomplete=true;result.descendantSnapshot={complete:false,error:error.message};}
    }
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
      if(process.platform==='win32'){
        if(!browser.treeComplete)throw Error('Refusing Windows tree termination without a complete owned descendant snapshot');
        await execute('taskkill.exe',['/PID',String(browser.ownedPid),'/T','/F'],{timeout:Math.min(8000,remaining()),maxBuffer:65536});result.signals.push('taskkill /T /F');
      }
      else {process.kill(-browser.ownedPid,'SIGTERM');result.signals.push('SIGTERM');}
      const signalUntil=Math.min(Date.now()+3000,deadline);
      while(Date.now()<signalUntil){if(!await inspect())break;await delay(100);}
      identity=await inspect();
      if(identity&&process.platform!=='win32') {
        if(!identity.verified||identity.started!==browser.identity.started)throw Error('Refusing unverified Store cleanup escalation');
        process.kill(-browser.ownedPid,'SIGKILL');result.signals.push('SIGKILL');await delay(200);
      }
    }
  }
  result.rootGone=(await inspect())===null;
  if(process.platform!=='win32')result.processGroupGone=await groupGone();
  else {
    result.shutdownScope='verified-root-and-snapshotted-owned-Windows-descendants';
    let remainingProcesses;
    do {
      remainingProcesses=await windowsRemaining(browser,deadline);
      if(remainingProcesses.gone)break;
      await delay(Math.min(100,remaining()));
    }while(deadline-Date.now()>3200);
    result.ownedDescendants={snapshotComplete:browser.treeComplete===true,...remainingProcesses};
    result.processTreeGone=browser.treeComplete===true&&remainingProcesses?.gone===true;
    // Compatibility with existing cleanup gates: Windows has no POSIX group;
    // this field represents the verified tracked process tree on that platform.
    result.processGroupGone=result.processTreeGone;
  }
  result.closedNormally=result.browserCloseRequested&&result.signals.length===0&&result.rootGone===true&&result.processGroupGone===true;
  browser.cdp=undefined;
  browser.lastClose=immutable(result);
  browser.closed=result.rootGone===true&&result.processGroupGone===true;
  return browser.lastClose;
}

async function launchGeneration(browser,signal,{deadline:outerDeadline=Date.now()+20000,cleanupDeadline}={}) {
  if(signal?.aborted)throw Error('Store launch interrupted');
  await assertOwnedProfile(browser);
  browser.logPath=path.join(browser.output,browser.generation===0?'browser.log':`browser-restart-${browser.generation}.log`);
  const log=await open(browser.logPath,'wx',0o600);
  let launchError,lastEndpointError;
  browser.closed=false;browser.identity=undefined;browser.cdp=undefined;
  browser.tracked=new Map();browser.treeComplete=false;browser.treeEverIncomplete=false;
  browser.child=spawn(browser.executable,browser.args,{stdio:['ignore',log.fd,log.fd],detached:process.platform!=='win32'});
  browser.ownedPid=browser.child.pid;
  browser.child.once('error',error=>{launchError=error;});await log.close();
  try {
    const deadline=Math.min(Date.now()+20000,outerDeadline);
    while(Date.now()<deadline) {
      if(signal?.aborted)throw Error('Store launch interrupted');
      if(launchError)throw launchError;
      browser.identity=await processIdentity(browser,Math.max(1,Math.min(3000,deadline-Date.now())),signal);
      if(browser.identity?.verified) {
        try {
          const endpointFile=path.join(browser.profile,'DevToolsActivePort');
          const endpointStat=await lstat(endpointFile);
          if(!endpointStat.isFile()||endpointStat.isSymbolicLink()||endpointStat.size>4096)throw Error('Owned endpoint is not a bounded regular file');
          const [port,ws]=(await readFile(endpointFile,'utf8')).trim().split(/\r?\n/);
          if(!/^\d+$/.test(port)||!ws?.startsWith('/devtools/browser/'))throw Error('Invalid owned endpoint');
          const endpoint=`ws://127.0.0.1:${port}${ws}`;
          const version=await (await fetch(`http://127.0.0.1:${port}/json/version`,{signal:AbortSignal.timeout(Math.max(1,Math.min(1000,deadline-Date.now())))})).json();
          if(version.webSocketDebuggerUrl!==endpoint)throw Error('Owned endpoint identity mismatch');
          if(deadline-Date.now()<10000)break;
          browser.cdp=await CDP.connect(endpoint);
          browser.identity=immutable(browser.identity);
          if(isWindows) {
            try {
              const snapshot=await windowsSnapshot(browser,deadline);
              if(!snapshot.complete)throw Error('Initial owned Windows descendant tracking is incomplete');
            }catch(error){browser.treeComplete=false;browser.treeEverIncomplete=true;throw error;}
          }
          return;
        }catch(error){lastEndpointError=String(error.cause?.message??error.message).slice(0,500);if(browser.cdp)throw error;}
      }
      await delay(100);
    }
    throw Error(`Owned Store browser endpoint did not become ready${lastEndpointError?`: ${lastEndpointError}`:''}`);
  }catch(error){try{error.cleanup=await closeOwned(browser,{deadline:cleanupDeadline});}catch(cleanupError){error.cleanup={error:cleanupError.message};}throw error;}
}

async function verifyStopped(browser) {
  if(browser.lastClose?.closedNormally!==true||!browser.closed)throw Error('Restart requires a verified normal Browser.close boundary');
  if(isWindows) {
    const remaining=await windowsRemaining(browser,Date.now()+3500);
    if(!browser.treeComplete||!remaining.gone)throw Error('Owned Windows descendants remain or shutdown tracking is incomplete');
  } else {
    try {process.kill(-browser.ownedPid,0);throw Error('Owned browser process group still exists');}
    catch(error){if(error.code!=='ESRCH')throw error;}
  }
}

async function removeStaleEndpoint(browser) {
  await assertOwnedProfile(browser);
  const file=path.join(browser.profile,'DevToolsActivePort');
  let stat;
  try {stat=await lstat(file);}catch(error){if(error.code==='ENOENT')return;throw error;}
  if(stat.isSymbolicLink()||!stat.isFile())throw Error('Refusing to remove a non-regular owned DevToolsActivePort');
  await unlink(file); // unlink only this captured profile entry; never follows a link.
}

export async function launchOwnedStoreBrowser({executable,output,signal}) {
  executable=await realpath(executable);output=await realpath(output);
  const profile=path.join(output,'profile');await mkdir(profile,{mode:0o700});
  const args=Object.freeze([`--user-data-dir=${profile}`,'--no-first-run','--no-default-browser-check','--window-size=1280,900','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','about:blank']);
  const state={executable,output,profile,args,signal,generation:0,closed:false,busy:false,
    outputIdentity:await directoryIdentity(output),profileIdentity:await directoryIdentity(profile),executableIdentity:await executableIdentity(executable)};
  const browser={};ownedStates.set(browser,state);
  for(const key of ['executable','profile','args','child','cdp','identity','ownedPid','generation','logPath','lastClose'])Object.defineProperty(browser,key,{enumerable:true,get:()=>state[key]});
  const transition=async(action)=>{
    if(state.busy)throw Error('Owned browser lifecycle operation already in progress');
    state.busy=true;try{return await action();}finally{state.busy=false;}
  };
  Object.defineProperty(browser,'close',{value:()=>transition(()=>closeOwned(state))});
  Object.defineProperty(browser,'restart',{value:(options={})=>transition(async()=>{
    if(!options||typeof options!=='object'||Object.keys(options).some(key=>key!=='signal'))throw Error('Restart accepts only a signal; profile/executable reuse is fixed to this handle');
    const restartSignal=options.signal??state.signal;
    const deadline=Date.now()+45000;
    const previous={pid:state.ownedPid,started:state.identity?.started};
    if(!state.closed)await closeOwned(state,{deadline});
    await verifyStopped(state);await assertOwnedProfile(state);
    if(restartSignal?.aborted)throw Error('Owned Store restart interrupted before relaunch');
    await removeStaleEndpoint(state);
    // ps lstart has one-second precision on macOS. Ensure distinct observed
    // native start identities rather than accepting a same-second timestamp.
    if(!isWindows)await delay(1100);
    // Reserve the full cleanup budget before creating a new process. Slow
    // shutdown must leave the profile closed rather than overrun the boundary.
    if(deadline-Date.now()<28000)throw Error('Insufficient restart time after verified shutdown');
    state.generation+=1;
    await launchGeneration(state,restartSignal,{deadline:Math.min(Date.now()+20000,deadline-18000),cleanupDeadline:deadline});
    if(state.ownedPid===previous.pid||state.identity.started===previous.started) {
      const error=Error('Restart did not produce a fresh PID/start identity');
      error.cleanup=await closeOwned(state,{deadline});throw error;
    }
    return browser;
  })});
  Object.freeze(browser);
  await launchGeneration(state,signal);
  return browser;
}

export async function probeOwnedStoreUi(browser,{mode='preflight',deadline,signal}={}) {
  const state=ownedState(browser);
  const helper=process.env.AA_STORE_UI_HELPER;
  if(!helper)return {schema:1,status:'unsupported',reason:'AA_STORE_UI_HELPER not configured',mode};
  if(!['preflight','dialog'].includes(mode))throw Error('Unsupported read-only Store UI mode');
  const command=process.platform==='win32'?'powershell.exe':helper;
  const args=process.platform==='win32'?['-NoProfile','-NonInteractive','-File',helper,'-PidValue',String(state.ownedPid),'-Profile',state.profile,'-Executable',state.executable,'-Mode',mode]:['--pid',String(state.ownedPid),'--profile',state.profile,'--executable',state.executable,'--mode',mode];
  try {
    const timeout=Math.min(15000,deadline-Date.now());if(timeout<=0)throw Error('UI prerequisite phase deadline exceeded');
    const {stdout}=await execute(command,args,{timeout,maxBuffer:65536,signal});
    const result=JSON.parse(stdout.replace(/^\uFEFF/,''));
    if(result.schema!==1||!['ready','untrusted','unsupported','error'].includes(result.status))throw Error('Unexpected native UI helper response');
    if(result.status==='ready'&&result.identity?.verified!==true)throw Error('Native UI helper readiness lacks owned identity');
    return result;
  }catch(error){return {schema:1,status:'error',mode,error:error.message.slice(0,1000)};}
}

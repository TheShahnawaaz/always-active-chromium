#!/usr/bin/env node
// Exercise the exact production shutdown script on Windows PowerShell 5.
// Only its CIM provider is replaced with finite in-memory records: no browser,
// UI action, real process inventory, signal or profile access is performed.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';

if(process.platform!=='win32') {
  console.log(JSON.stringify({status:'unsupported',reason:'Windows PowerShell 5 required; no test executed'}));
  process.exit(0);
}
const source=await readFile(new URL('./lib/owned-store-browser.mjs',import.meta.url),'utf8');
const marker='const windowsRemainingScript=String.raw`';
const start=source.indexOf(marker),end=source.indexOf('\n`;',start);
assert.ok(start>=0&&end>start,'production shutdown script is present');
const script=source.slice(start+marker.length,end);
const provider=String.raw`
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
if($PSVersionTable.PSVersion.Major -ne 5){throw 'fixture_requires_Windows_PowerShell_5'}
function Get-CimInstance {
 param([string]$ClassName,[string]$Filter,[int]$OperationTimeoutSec)
 if($ClassName -cne 'Win32_Process' -or $Filter -cne $env:AA_FIXTURE_EXPECTED_FILTER){throw 'fixture_unexpected_CIM_query'}
 foreach($item in (ConvertFrom-Json -InputObject $env:AA_FIXTURE_CURRENT)){
  [pscustomobject]@{ProcessId=[int]$item.pid;CreationDate=[datetime]::Parse($item.started,[Globalization.CultureInfo]::InvariantCulture,[Globalization.DateTimeStyles]::RoundtripKind)}
 }
}
`;
const execute=promisify(execFile);
const a='2026-11-02T00:00:00.0000000Z',b='2026-11-02T00:00:01.0000000Z';
const records=[{pid:101,started:a},{pid:102,started:b}];
const cases=[
  {name:'flat two-record array retains alive/gone creation checks',input:records,current:[records[0]],filter:'ProcessId=101 OR ProcessId=102',states:['alive','gone']},
  {name:'one-record array remains one record',input:[records[0]],current:[],filter:'ProcessId=101',states:['gone']},
  {name:'reused PID is distinct from original creation',input:[records[0]],current:[{pid:101,started:b}],filter:'ProcessId=101',states:['reused']},
  {name:'same PID with two distinct lifetime identities remains valid',input:[records[0],{pid:101,started:b}],current:[{pid:101,started:b}],filter:'ProcessId=101 OR ProcessId=101',states:['reused','alive']},
  {name:'object root is refused before CIM',input:records[0],error:'bounded JSON array'},
  {name:'nested array is refused before CIM',input:[records],error:'flat object'},
  {name:'array-valued PID is refused before CIM',input:[{pid:[101,102],started:a}],error:'PID is invalid'},
  {name:'array-valued creation is refused before CIM',input:[{pid:101,started:[a,b]}],error:'creation identity is invalid'},
  {name:'empty identities cannot prove shutdown',input:[],error:'identities are empty'}
];
const results=[];
const deadline=Date.now()+60000;
for(const test of cases) {
  const command=provider+'\ntry { & {\n'+script+'\n} } catch { [Console]::Error.WriteLine($_.Exception.Message); exit 9 }\n';
  let result,error;
  try {
    result=await execute('powershell.exe',['-NoProfile','-NonInteractive','-Command',command],{
      timeout:Math.max(1,Math.min(6000,deadline-Date.now())),maxBuffer:65536,
      env:{...process.env,AA_OWNED_STORE_TRACKED:JSON.stringify(test.input),
        AA_FIXTURE_CURRENT:JSON.stringify(test.current??[]),AA_FIXTURE_EXPECTED_FILTER:test.filter??'INVALID_INPUT_MUST_NOT_QUERY'}});
  } catch(problem) {error=problem;}
  if(test.error) {
    assert.equal(error?.code,9,test.name+': validation must refuse');
    assert.ok(error.stderr.includes(test.error),test.name+': correct pre-query refusal');
    assert.ok(!error.stderr.includes('fixture_unexpected_CIM_query'),test.name+': no provider call');
  } else {
    if(error)throw error;
    const parsed=JSON.parse(result.stdout.replace(/^\uFEFF/,''));
    const rows=Array.isArray(parsed)?parsed:[parsed];
    assert.deepEqual(rows.map(row=>row.pid),test.input.map(row=>row.pid),test.name);
    assert.deepEqual(rows.map(row=>row.started),test.input.map(row=>row.started),test.name);
    assert.deepEqual(rows.map(row=>row.state),test.states,test.name);
  }
  results.push({name:test.name,status:'passed'});
}
console.log(JSON.stringify({status:'passed',scope:'Exact production JSON/creation/disappearance path with stub CIM only',browserOrUiActions:false,tests:results}));

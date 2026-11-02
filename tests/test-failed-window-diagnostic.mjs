// Pure report-boundary guards: no browser, PowerShell, process or UI actions.
import test from 'node:test';
import assert from 'node:assert/strict';
import {parseFailedWindowDiagnostic,sanitizeFailedWindowDiagnostic} from './lib/failed-window-diagnostic.mjs';
const identity={pid:6408,started:'2026-11-02T05:04:53.1745240Z'};
function receipt(){return {schema:1,purpose:'owned-failed-normal-window-diagnostic',status:'observed',...identity,identityReverified:true,mainWindowHandle:'300a2',mainWindowTitleCategory:'untitled',mainWindowState:{ownershipVerified:true,visible:true,minimized:false,foreground:true},
  childRoles:{status:'observed',examined:3,verified:2,unverified:1,truncated:false,creationAndPackageVerified:true,roles:{renderer:1,'gpu-process':0,utility:1,'crashpad-handler':0,other:0},utilities:{network:1,audio:0,storage:0,'video-capture':0,other:0}},
  uia:{status:'observed',reason:null,ownershipVerified:true,visitedNodes:12,truncated:false,addressBar:{status:'classified',category:'expected-loopback',candidates:1},errorTags:['STATUS_ACCESS_VIOLATION']},elapsedMs:500};}
test('retains only bounded role counts, address category and allowlisted tags',()=>{
  const value=receipt();value.rawCommand='private child args';value.mainWindowTitle='private title';value.uia.tree=['private URL'];value.childRoles.roles.private=10;
  const result=sanitizeFailedWindowDiagnostic(value,identity);
  assert.equal(result.uia.addressBar.category,'expected-loopback');assert.equal(result.childRoles.roles.renderer,1);
  assert.ok(!JSON.stringify(result).includes('private'));assert.equal(result.mainWindowTitle,undefined);
});
test('rejects wrong identity, foreign ownership, raw tags and inconsistent child evidence',()=>{
  for(const mutate of [value=>value.pid++,value=>value.started+='changed',value=>value.identityReverified=false,value=>value.uia.ownershipVerified=false,value=>value.mainWindowState.visible='unknown',value=>value.uia.errorTags=['https://private.invalid/'],value=>value.childRoles.examined=33,value=>value.childRoles.roles.renderer=2,value=>value.childRoles.utilities.other=1,value=>value.uia.visitedNodes=65,value=>value.uia.addressBar.category='http://private.invalid']){
    const value=receipt();mutate(value);assert.throws(()=>sanitizeFailedWindowDiagnostic(value,identity));
  }
});
test('deadline preserves prior verified children but never upgrades partial UIA evidence',()=>{
  const first=receipt();first.status='partial';first.uia={status:'unavailable',reason:'not_completed',ownershipVerified:false,visitedNodes:0,truncated:false,addressBar:{status:'not-found',category:null,candidates:0},errorTags:[]};
  const value=parseFailedWindowDiagnostic(JSON.stringify(first)+'\n',identity,{timedOut:true});
  assert.equal(value.status,'partial');assert.equal(value.helperDeadlineExceeded,true);assert.equal(value.childRoles.verified,2);assert.equal(value.uia.ownershipVerified,false);assert.equal(value.uia.reason,'helper_deadline');
});
test('partial, malformed or oversized unverified stdout cannot become an observation',()=>{
  for(const text of ['',JSON.stringify({...receipt(),pid:1}),'not JSON','x'.repeat(16385)])assert.throws(()=>parseFailedWindowDiagnostic(text,identity));
  const value=parseFailedWindowDiagnostic(JSON.stringify(receipt())+'\n',identity);assert.equal(value.status,'observed');
});

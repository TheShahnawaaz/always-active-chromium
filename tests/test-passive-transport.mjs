// Real local HTTP/TCP diagnostics; no browser, UI, PowerShell or payload capture.
import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import net from 'node:net';
import {once} from 'node:events';
import {setTimeout as delay} from 'node:timers/promises';
import {observePassiveTransport,controllerHealthGet} from './lib/passive-transport.mjs';
const healthPath='/_controller-health/00000000-0000-0000-0000-000000000001';
async function fixture(t,limits={}){
  let observer;let parsed=0;
  const server=http.createServer((req,res)=>{if(observer.handlePrelaunchRequest(req,res))return;parsed++;res.end('ok');});
  observer=observePassiveTransport(server,{healthPath,...limits});
  server.on('clientError',(_error,socket)=>socket.destroy());
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  t.after(async()=>{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));});
  return {server,observer,port:server.address().port,parsed:()=>parsed};
}
async function connected(port){const socket=net.createConnection({host:'127.0.0.1',port});socket.on('error',()=>{});await once(socket,'connect');return socket;}
async function closed(socket){const wait=once(socket,'close');socket.destroy();await wait;await delay(5);}
test('self-health passes and never counts as a later browser observation',async t=>{
  const f=await fixture(t);
  const health=await controllerHealthGet(f.server,f.observer,{healthPath});
  assert.equal(health.status,'passed');assert.equal(health.controllerSocketMatched,true);assert.equal(health.responseStatus,204);
  f.observer.startObservation();await delay(10);
  const value=f.observer.snapshot();
  assert.equal(f.parsed(),0);assert.equal(value.controllerSelfProbe.acceptedConnections,1);assert.equal(value.controllerSelfProbe.requests,1);
  assert.equal(value.observationUnattributed.acceptedConnections,0);assert.equal(value.observationUnattributed.bytesRead,0);
  assert.equal(value.controllerSelfProbe.closedConnections,1);assert.equal(value.payloadRetained,false);assert.equal(value.socketFlowChanged,false);
});
test('unavailable health listener fails finitely without starting an observation',async()=>{
  const server=http.createServer();const observer=observePassiveTransport(server,{healthPath});
  const value=await controllerHealthGet(server,observer,{healthPath,timeoutMs:100});
  assert.equal(value.status,'failed');assert.equal(value.error,'listener_unavailable');assert.ok(value.elapsedMs<=200);
  assert.equal(observer.snapshot().observationUnattributed.acceptedConnections,0);
});
test('a nonresponding health path hits its finite deadline and closes its own client',async t=>{
  const server=http.createServer(()=>{}),observer=observePassiveTransport(server,{healthPath});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  t.after(async()=>{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));});
  const value=await controllerHealthGet(server,observer,{healthPath,timeoutMs:100});
  assert.equal(value.status,'failed');assert.equal(value.error,'deadline');assert.ok(value.elapsedMs<500);
  observer.startObservation();await delay(10);
  assert.equal(observer.snapshot().observationUnattributed.acceptedConnections,0);
  assert.equal(observer.snapshot().controllerSelfProbe.closedConnections,1);
});
test('accepted idle or partial-HTTP sockets are visible even with zero parsed requests',async t=>{
  const f=await fixture(t);f.observer.startObservation();
  const idle=await connected(f.port),partial=await connected(f.port);
  partial.write('GET /partial');await delay(20);
  const during=f.observer.snapshot().observationUnattributed;
  assert.equal(during.acceptedConnections,2);assert.equal(during.trackedOpenConnections,2);assert.ok(during.bytesRead>=12);assert.equal(f.parsed(),0);
  await closed(idle);await closed(partial);
  const after=f.observer.snapshot().observationUnattributed;
  assert.equal(after.closedConnections,2);assert.equal(after.trackedOpenConnections,0);assert.ok(after.bytesRead>=12);assert.equal(f.parsed(),0);
});
test('a later request to the health path is ordinary traffic; parser flow is unchanged',async t=>{
  const f=await fixture(t);f.observer.startObservation();
  const response=await new Promise((resolve,reject)=>http.get({host:'127.0.0.1',port:f.port,path:healthPath,agent:false},res=>{
    let text='';res.on('data',chunk=>text+=chunk);res.on('end',()=>resolve(text));
  }).on('error',reject));
  assert.equal(response,'ok');assert.equal(f.parsed(),1);await delay(10);
  const value=f.observer.snapshot().observationUnattributed;
  assert.equal(value.acceptedConnections,1);assert.equal(value.closedConnections,1);assert.equal(value.requests,1);assert.ok(value.bytesRead>0);assert.ok(value.bytesWritten>0);
});
test('tracking and byte saturation are explicit and do not destroy overflow sockets',async t=>{
  const f=await fixture(t,{maxTracked:1,maxCounter:2,maxBytes:4});f.observer.startObservation();
  const first=await connected(f.port),overflow=await connected(f.port),third=await connected(f.port);
  first.write('GET /partial');await delay(20);
  const during=f.observer.snapshot();
  assert.equal(during.saturated,true);assert.equal(during.trackingComplete,false);assert.equal(during.observationUnattributed.acceptedConnections,2);
  assert.equal(during.observationUnattributed.untrackedConnections,2);assert.equal(during.observationUnattributed.bytesRead,4);
  assert.equal(overflow.destroyed,false);assert.equal(third.destroyed,false);
  await closed(first);await closed(overflow);await closed(third);
});

// Actual passive fixture script under finite fake browser APIs; no browser/UI run.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

const html=await readFile(new URL('./fixtures/no-debug.html',import.meta.url),'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1].replace('__NO_DEBUG_CONFIGURATION__',JSON.stringify({run:'fixture-token',page:'alpha'}));
function environment(versionRequest){
  const posts=[],intervals=[],order=[];
  const navigator={webdriver:false,userAgent:'schema fixture',...(versionRequest?{userAgentData:{getHighEntropyValues:()=>{order.push('version-request');return versionRequest();}}}:{})};
  const context=vm.createContext({navigator,performance:{now:()=>100},document:{hidden:true,visibilityState:'hidden',hasFocus:()=>false,webkitHidden:true,webkitVisibilityState:'hidden'},
    fetch:(_url,options)=>{order.push('post');posts.push(JSON.parse(options.body));return Promise.resolve({ok:true});},
    setInterval:(callback,ms)=>{order.push('interval');intervals.push({callback,ms});return 1;}});
  vm.runInContext(script,context,{timeout:1000});
  return {posts,intervals,order};
}
const flush=async()=>{await Promise.resolve();await Promise.resolve();};

test('unresolved high-entropy version cannot block initial or periodic visibility posts',async()=>{
  let resolve;
  const pending=new Promise(done=>{resolve=done;});
  const fixture=environment(()=>pending);
  assert.deepEqual(fixture.order.slice(0,3),['post','interval','version-request']);
  assert.equal(fixture.posts.length,1);assert.equal(fixture.posts[0].versionStatus,'pending');
  assert.equal(fixture.posts[0].hidden,true);assert.equal(fixture.posts[0].hasFocus,false);
  assert.equal(fixture.intervals[0].ms,250);
  await fixture.intervals[0].callback();
  assert.equal(fixture.posts.length,2);assert.equal(fixture.posts[1].versionStatus,'pending');
  resolve({fullVersionList:[{brand:'Chromium',version:'156.0.8078.80'}]});await flush();
  assert.equal(fixture.posts.at(-1).versionStatus,'resolved');
  assert.deepEqual(fixture.posts.at(-1).fullVersionList,[{brand:'Chromium',version:'156.0.8078.80'}]);
  assert.equal(fixture.posts.at(-1).versionError,null);
});
test('failed version request keeps state reporting and records bounded error',async()=>{
  const fixture=environment(()=>Promise.reject(Error('x'.repeat(500))));await flush();
  assert.equal(fixture.posts[0].versionStatus,'pending');
  assert.equal(fixture.posts.at(-1).versionStatus,'error');
  assert.equal(fixture.posts.at(-1).versionError.length,160);
  await fixture.intervals[0].callback();
  assert.equal(fixture.posts.at(-1).hidden,true);
  assert.deepEqual(fixture.posts.at(-1).fullVersionList,[]);
});
test('unavailable high-entropy API is explicit and cannot supply a matching version',async()=>{
  const fixture=environment();await flush();
  assert.equal(fixture.posts.at(-1).versionStatus,'error');
  assert.equal(fixture.posts.at(-1).versionError,'userAgentData_unavailable');
  assert.deepEqual(fixture.posts.at(-1).fullVersionList,[]);
  assert.equal(fixture.intervals.length,1);
});
test('version metadata count and string lengths are finite',async()=>{
  const values=Array.from({length:30},()=>({brand:'x'.repeat(200),version:'y'.repeat(200)}));
  const fixture=environment(()=>Promise.resolve({fullVersionList:values}));await flush();
  const observed=fixture.posts.at(-1);
  assert.equal(observed.versionStatus,'resolved');assert.equal(observed.fullVersionList.length,16);
  assert.ok(observed.fullVersionList.every(value=>value.brand.length===80&&value.version.length===80));
});

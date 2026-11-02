import test from 'node:test';
import assert from 'node:assert/strict';
import {isExpectedWindowedWindow} from './lib/window-state.mjs';

const window=(windowState,windowId=42)=>({windowId,bounds:{windowState}});

test('fullscreen exit accepts normal and restored maximized states on the expected window',()=>{
  for(const state of ['normal','maximized'])assert.equal(isExpectedWindowedWindow(window(state),42),true);
});

test('fullscreen exit rejects fullscreen, minimized and unknown states',()=>{
  for(const state of ['fullscreen','minimized','unknown','',null,undefined])assert.equal(isExpectedWindowedWindow(window(state),42),false);
});

test('a different window cannot satisfy fullscreen exit',()=>{
  for(const state of ['normal','maximized'])assert.equal(isExpectedWindowedWindow(window(state,43),42),false);
});

test('missing window, bounds, ID or expected ID cannot satisfy fullscreen exit',()=>{
  for(const value of [null,undefined,{}, {windowId:42}, {windowId:42,bounds:{}}, {bounds:{windowState:'normal'}},window('normal','42')])assert.equal(isExpectedWindowedWindow(value,42),false);
  for(const id of [undefined,null,'42',NaN,Infinity,42.5])assert.equal(isExpectedWindowedWindow(window('normal',id),id),false);
});

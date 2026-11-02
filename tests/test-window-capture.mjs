// Synthetic PNG/receipt schema guards only; never browser or appearance evidence.
import test from 'node:test';
import assert from 'node:assert/strict';
import {deflateSync} from 'node:zlib';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {fileURLToPath} from 'node:url';
import {pngMetadata,validateWindowCapture} from './lib/window-capture.mjs';

function crc32(bytes){let crc=0xffffffff;for(const byte of bytes){crc^=byte;for(let i=0;i<8;i++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);}return(crc^0xffffffff)>>>0;}
function chunk(type,body){const name=Buffer.from(type);const head=Buffer.alloc(4);head.writeUInt32BE(body.length);const crc=Buffer.alloc(4);crc.writeUInt32BE(crc32(Buffer.concat([name,body])));return Buffer.concat([head,name,body,crc]);}
function fixture(){
  const width=320,height=240,header=Buffer.alloc(13);header.writeUInt32BE(width);header.writeUInt32BE(height,4);header[8]=8;header[9]=2;
  const raw=Buffer.alloc((width*3+1)*height);for(let y=0;y<height;y++)for(let x=0;x<width;x++)raw.fill(x<160?80:220,y*(width*3+1)+1+x*3,y*(width*3+1)+4+x*3);
  const png=Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]),chunk('IHDR',header),chunk('IDAT',deflateSync(raw)),chunk('IEND',Buffer.alloc(0))]);
  const expected={pid:1234,executable:'C:\\owned\\chrome.exe',profile:'C:\\owned\\profile-native',started:'2026-11-02T00:00:00.0000000Z'};
  const receipt={schema:1,purpose:'owned-normal-browser-window-capture',platform:'win32',status:'captured',method:'PrintWindow-full-window-flags-0',captureAttempted:true,captureSucceeded:true,captureOutcomeUncertain:false,manualReview:'pending',uiEquivalenceVerified:false,visualCompletenessVerified:false,nativeUiAccessed:true,visitedWindows:1,errors:[],identity:{...expected,verified:true,immediatelyRevalidated:true,afterCaptureRevalidated:true,ownerVerified:true,sessionVerified:true},window:{handle:'abc',ownerPID:1234,width,height,dpi:96,foregroundVerified:true,visible:true,minimized:false,cloaked:false,normalTopLevelVerified:true,fixtureTitleVerified:true,unchangedAfterCapture:true},contentCheck:{nonUniform:true,visualCompletenessVerified:false},png:{file:'browser-window.png',...pngMetadata(png)}};
  return{png,receipt,expected};
}
test('complete finite PNG and owned receipt still require manual visual review',()=>{const {png,receipt,expected}=fixture();assert.equal(validateWindowCapture(receipt,png,expected).width,320);assert.equal(receipt.uiEquivalenceVerified,false);assert.equal(receipt.visualCompletenessVerified,false);});
test('uncertain capture or an equivalence claim cannot be accepted',()=>{for(const patch of [{captureOutcomeUncertain:true},{captureSucceeded:null},{uiEquivalenceVerified:true},{visualCompletenessVerified:true}]){const {png,receipt,expected}=fixture();assert.throws(()=>validateWindowCapture({...receipt,...patch},png,expected));}});
test('other PID/profile/start or unowned window cannot be accepted',()=>{for(const patch of [{pid:9},{profile:'C:\\other'},{started:'different'}]){const {png,receipt,expected}=fixture();assert.throws(()=>validateWindowCapture(receipt,png,{...expected,...patch}));}const {png,receipt,expected}=fixture();receipt.window.foregroundVerified=false;assert.throws(()=>validateWindowCapture(receipt,png,expected));});
test('PNG corruption, truncation, metadata mismatch and missing pixels refuse',()=>{const {png,receipt,expected}=fixture();const corrupted=Buffer.from(png);corrupted[40]^=1;assert.throws(()=>pngMetadata(corrupted));assert.throws(()=>pngMetadata(png.subarray(0,33)));assert.throws(()=>pngMetadata(png.subarray(0,png.length-12)));receipt.png.sha256='0'.repeat(64);assert.throws(()=>validateWindowCapture(receipt,png,expected));});
test('Windows invalid-PID helper refuses before native UI or file capture',{skip:process.platform!=='win32'},async()=>{const script=fileURLToPath(new URL('./ui/owned-window-capture.ps1',import.meta.url));const {stdout}=await promisify(execFile)('powershell.exe',['-NoProfile','-NonInteractive','-File',script,'-PidValue','1'],{timeout:15000,maxBuffer:65536,windowsHide:true});const receipt=JSON.parse(stdout.replace(/^\uFEFF/,''));assert.equal(receipt.status,'refused');assert.equal(receipt.captureAttempted,false);assert.equal(receipt.captureSucceeded,false);assert.equal(receipt.nativeUiAccessed,false);assert.equal(receipt.visitedWindows,0);assert.deepEqual(receipt.errors,['invalid_pid']);});

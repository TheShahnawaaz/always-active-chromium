// Optional native-window evidence only. No browser controls, input or desktop capture.
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {lstat,readFile,realpath,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {inflateSync} from 'node:zlib';
import path from 'node:path';

const execute=promisify(execFile);
export const captureLimits=Object.freeze({maxWidth:2048,maxHeight:1536,maxPixels:3145728,maxBytes:3145728});
export function failedStartupCaptureEnabled({optIn,platform,optionsMode,captureMode,helper}){
  if(optIn!=='1')return false;
  if(platform!=='win32'||optionsMode!=='control'||captureMode!=='control'||!helper)throw Error('failed_startup_capture_requires_windows_control_reference');
  return true;
}
const samePath=(a,b)=>typeof a==='string'&&typeof b==='string'&&a.replaceAll('\\','/').toLowerCase()===b.replaceAll('\\','/').toLowerCase();
function crc32(bytes){let crc=0xffffffff;for(const byte of bytes){crc^=byte;for(let i=0;i<8;i++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);}return (crc^0xffffffff)>>>0;}
export function pngMetadata(bytes){
  if(!Buffer.isBuffer(bytes)||bytes.length>captureLimits.maxBytes||bytes.length<57||!bytes.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10])))throw Error('invalid_png_signature_or_size');
  let offset=8,width,height,channels,ended=false;const compressed=[];
  while(offset<bytes.length){
    if(offset+12>bytes.length)throw Error('truncated_png_chunk');
    const length=bytes.readUInt32BE(offset),type=bytes.toString('ascii',offset+4,offset+8),end=offset+12+length;
    if(end>bytes.length||!/^[A-Za-z]{4}$/.test(type)||crc32(bytes.subarray(offset+4,end-4))!==bytes.readUInt32BE(end-4))throw Error('invalid_png_chunk');
    if(offset===8){
      if(type!=='IHDR'||length!==13)throw Error('png_ihdr_required');
      width=bytes.readUInt32BE(offset+8);height=bytes.readUInt32BE(offset+12);
      const depth=bytes[offset+16],color=bytes[offset+17];channels=color===2?3:color===6?4:0;
      if(width<320||height<240||width>captureLimits.maxWidth||height>captureLimits.maxHeight||width*height>captureLimits.maxPixels||depth!==8||!channels||bytes[offset+18]!==0||bytes[offset+19]!==0||bytes[offset+20]!==0)throw Error('unsupported_png_dimensions_or_format');
    }else if(type==='IHDR')throw Error('duplicate_png_ihdr');
    if(type==='IDAT')compressed.push(bytes.subarray(offset+8,offset+8+length));
    if(type==='IEND'){if(length!==0||end!==bytes.length)throw Error('invalid_png_end');ended=true;break;}
    offset=end;
  }
  if(!ended||!compressed.length)throw Error('incomplete_png');
  const stride=width*channels+1,expected=stride*height;
  const pixels=inflateSync(Buffer.concat(compressed),{maxOutputLength:expected+1});
  if(pixels.length!==expected)throw Error('invalid_png_pixel_length');
  for(let row=0;row<height;row++)if(pixels[row*stride]>4)throw Error('invalid_png_row_filter');
  return {width,height,bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')};
}
export function validateWindowCapture(receipt,bytes,{pid,profile,executable,started,captureContext='fixture'}){
  const image=pngMetadata(bytes),identity=receipt?.identity,window=receipt?.window;
  if(receipt?.schema!==1||receipt.purpose!=='owned-normal-browser-window-capture'||receipt.platform!=='win32'||receipt.status!=='captured'||receipt.method!=='PrintWindow-full-window-flags-0'||receipt.captureAttempted!==true||receipt.captureSucceeded!==true||receipt.captureOutcomeUncertain!==false||receipt.manualReview!=='pending'||receipt.uiEquivalenceVerified!==false||receipt.visualCompletenessVerified!==false||receipt.nativeUiAccessed!==true||!Array.isArray(receipt.errors)||receipt.errors.length)throw Error('unverified_capture_receipt');
  if(identity?.verified!==true||identity.immediatelyRevalidated!==true||identity.afterCaptureRevalidated!==true||identity.ownerVerified!==true||identity.sessionVerified!==true||identity.pid!==pid||identity.started!==started||!samePath(identity.executable,executable)||!samePath(identity.profile,profile))throw Error('capture_identity_mismatch');
  if(!['fixture','startup-diagnostic'].includes(captureContext)||(receipt.captureContext??'fixture')!==captureContext)throw Error('capture_context_mismatch');
  if(captureContext==='fixture'&&(window?.fixtureTitleVerified!==true||window.titleKind!==undefined&&window.titleKind!=='fixture'))throw Error('fixture_title_required');
  if(captureContext==='startup-diagnostic'&&(receipt.behaviorVerified!==false||!['fixture','untitled'].includes(window?.titleKind)||window.fixtureTitleVerified!==(window.titleKind==='fixture')||window.titleContextVerified!==true||window.titleUnchangedAfterCapture!==true))throw Error('unverified_diagnostic_title');
  if(window?.ownerPID!==pid||typeof window.handle!=='string'||!/^[0-9a-f]{1,16}$/.test(window.handle)||/^0+$/.test(window.handle)||window.foregroundVerified!==true||window.visible!==true||window.minimized!==false||window.cloaked!==false||window.normalTopLevelVerified!==true||window.unchangedAfterCapture!==true||!Number.isInteger(window.dpi)||window.dpi<48||window.dpi>768)throw Error('unverified_owned_window');
  if(!Number.isInteger(receipt.visitedWindows)||receipt.visitedWindows<1||receipt.visitedWindows>8||receipt.png?.file!=='browser-window.png'||Object.keys(image).some(key=>image[key]!==receipt.png[key])||window.width!==image.width||window.height!==image.height||receipt.contentCheck?.nonUniform!==true||receipt.contentCheck.visualCompletenessVerified!==false)throw Error('capture_png_binding_mismatch');
  return image;
}
export async function captureOwnedWindow({helper,pid,profile,executable,started,output,captureContext='fixture'}){
  const png=path.join(output,'browser-window.png'),receiptPath=path.join(output,'browser-window-capture.json');
  let receipt={schema:1,purpose:'owned-normal-browser-window-capture',platform:process.platform,status:'error',captureContext,behaviorVerified:false,manualReview:'pending',uiEquivalenceVerified:false,visualCompletenessVerified:false,captureAttempted:null,captureSucceeded:null,captureOutcomeUncertain:true,errors:[]};
  try{
    if(process.platform!=='win32')throw Error('windows_capture_only');
    if(!['fixture','startup-diagnostic'].includes(captureContext))throw Error('capture_context_invalid');
    if(await realpath(output)!==await realpath(path.dirname(profile)))throw Error('capture_output_must_own_profile');
    const script=await realpath(helper),scriptStat=await lstat(script);
    if(!scriptStat.isFile()||scriptStat.isSymbolicLink())throw Error('regular_capture_helper_required');
    const {stdout}=await execute('powershell.exe',['-NoProfile','-NonInteractive','-File',script,'-PidValue',String(pid),'-Profile',profile,'-Executable',executable,'-ExpectedStarted',started,'-OutputFile',png,'-CaptureContext',captureContext],{timeout:15000,killSignal:'SIGKILL',maxBuffer:65536,windowsHide:true});
    const candidate=JSON.parse(stdout.replace(/^\uFEFF/,''));
    if(!candidate||typeof candidate!=='object'||candidate.schema!==1||candidate.purpose!=='owned-normal-browser-window-capture'||!['captured','refused','unsupported','error'].includes(candidate.status))throw Error('invalid_capture_helper_receipt');
    if(candidate.status!=='captured'){receipt=candidate;throw Error('native_capture_not_captured');}
    const stat=await lstat(png);
    if(!stat.isFile()||stat.isSymbolicLink()||stat.size>captureLimits.maxBytes||!samePath(await realpath(png),png))throw Error('unsafe_or_oversized_png');
    const bytes=await readFile(png);validateWindowCapture(candidate,bytes,{pid,profile,executable,started,captureContext});receipt=candidate;
  }catch(error){
    if(receipt.status==='captured')receipt={...receipt,status:'error',captureSucceeded:null,captureOutcomeUncertain:true};
    receipt.errors=[...(Array.isArray(receipt.errors)?receipt.errors:[]),/^[a-z_]{1,100}$/.test(error.message)?error.message:'capture_helper_failed'].slice(0,8);
  }
  await writeFile(receiptPath,JSON.stringify(receipt,null,2)+'\n',{flag:'wx',mode:0o600});
  return {status:receipt.status==='captured'?'captured':'not-captured',captureContext,behaviorVerified:false,manualReview:'pending',uiEquivalenceVerified:false,
    receiptFile:'browser-window-capture.json',pngFile:receipt.status==='captured'?'browser-window.png':null,receipt};
}

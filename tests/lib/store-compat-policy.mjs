// Full Store test policy and bounded filesystem checks. No browser/UI actions.
import { createHash } from 'node:crypto';
import { lstat, readFile, readdir, realpath } from 'node:fs/promises';
import path from 'node:path';
import { getStoreTarget } from './store-targets.mjs';

export const COMPAT_TARGET=getStoreTarget('ubol');
export const BROWSER_REVISION='fb096c0011f9d50f0a264a9376420cdea9c421e3';
export const UBOL_PERMISSION='Read and change all your data on all websites';
export const UBOL_AUDIT=Object.freeze({
  version:'2026.1026.1812',
  manifestRawSha256:'2f5040722874e88851d9e2464b54584eef3689f114814cd5db723271a2e59557',
  manifestSemanticSha256:'89c92fd348a928ce3e2191001de222a000c26063b3aad8afef56d3300fcc7dc8',
  sources:{
    'js/background.js':'b3875ec435efd6405163e9ce1831b3b42e88cf1513c11719de0d6a8f0a1f6b27',
    'js/ruleset-manager.js':'302b1ad703c1a03d70bd42c6e9a1d22eeca835c3e97b2a8217e7b64089021b74',
    'js/ext-compat.js':'a487979c41741f5304155027f85592997f92894b7b166bc5ac9b2634dda49f6d',
    'js/config.js':'8cef880fc40111993d9cf9be8ea9e5a96b59e3b4093f7bc377c68f8e82458968'
  }
});
export const sha256=bytes=>createHash('sha256').update(bytes).digest('hex');
const canonical=value=>Array.isArray(value)?value.map(canonical):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])])):value;
export function manifestSemanticDigest(manifest){const copy={...manifest};delete copy.key;return sha256(JSON.stringify(canonical(copy)));}
export function keyExtensionId(key){
  if(typeof key!=='string'||key.length>16384||!/^[A-Za-z0-9+/]+={0,2}$/.test(key))throw Error('Invalid installed public key');
  const bytes=Buffer.from(key,'base64');if(!bytes.length||bytes.toString('base64')!==key)throw Error('Noncanonical installed public key');
  return sha256(bytes).slice(0,32).replace(/[0-9a-f]/g,digit=>String.fromCharCode(97+parseInt(digit,16)));
}
async function boundedFile(root,relative,maxBytes){
  const canonicalRoot=await realpath(root),components=relative.split(/[\\/]/);
  if(components.some(part=>!part||part==='.'||part==='..')||path.isAbsolute(relative))throw Error('Unsafe owned relative path');
  let current=canonicalRoot;
  for(let index=0;index<components.length;index++){
    current=path.join(current,components[index]);const info=await lstat(current);
    if(info.isSymbolicLink())throw Error('Refusing symlink in owned extension evidence');
    if(index<components.length-1&&!info.isDirectory())throw Error('Owned source parent is not a directory');
    if(index===components.length-1&&(!info.isFile()||info.size>maxBytes))throw Error('Nonregular or oversized owned evidence');
  }
  if(await realpath(current)!==current)throw Error('Owned source path changed');
  return readFile(current);
}
export async function inspectTargetPreferences(profile,target=COMPAT_TARGET){
  const parsedFiles=[],entries=[],errors=[];
  for(const name of ['Preferences','Secure Preferences']){
    try{
      const bytes=await boundedFile(profile,`Default/${name}`,8388608),data=JSON.parse(bytes.toString('utf8'));
      parsedFiles.push(name);const settings=data.extensions?.settings??{};
      if(Object.hasOwn(settings,target.id)){
        const entry=settings[target.id];
        entries.push({file:name,path:typeof entry.path==='string'?entry.path:null,version:entry.manifest?.version??null,state:entry.state??null});
      }
    }catch(error){if(error.code!=='ENOENT')errors.push({file:name,error:error.message.slice(0,500)});}
  }
  return {parsedFiles,entries,errors,targetAbsent:parsedFiles.length>0&&entries.length===0&&errors.length===0};
}
export function summarizePreferences(result){return {...result,entries:result.entries.map(entry=>({...entry,path:entry.path?path.basename(entry.path):null}))};}
export async function verifyInstalledSources(profile,{target=COMPAT_TARGET,audit=UBOL_AUDIT}={}){
  const preferences=await inspectTargetPreferences(profile,target);
  if(preferences.errors.length||!preferences.entries.length)throw Error('Persisted installed target path is unavailable');
  const profileRoot=await realpath(profile),installRoot=path.join(profileRoot,'Default','Extensions',target.id);
  const rootInfo=await lstat(installRoot);if(rootInfo.isSymbolicLink()||!rootInfo.isDirectory()||await realpath(installRoot)!==installRoot)throw Error('Installed target directory is not an owned regular directory');
  const versions=await readdir(installRoot,{withFileTypes:true});if(versions.length>16)throw Error('Too many installed target version entries');
  const candidates=[];
  for(const entry of versions){
    if(!entry.isDirectory()||entry.isSymbolicLink()||!entry.name.startsWith(audit.version+'_')||!/^\d+$/.test(entry.name.slice(audit.version.length+1)))continue;
    const candidate=path.join(installRoot,entry.name);
    const active=preferences.entries.some(item=>item.path&&[
      path.resolve(profileRoot,'Default',item.path),path.resolve(profileRoot,'Default','Extensions',item.path),path.resolve(item.path)
    ].some(value=>value===candidate));
    if(active)candidates.push(candidate);
  }
  if(candidates.length!==1)throw Error('Cannot uniquely identify the persisted active audited extension directory');
  const root=candidates[0],manifestBytes=await boundedFile(root,'manifest.json',1048576),manifest=JSON.parse(manifestBytes.toString('utf8'));
  if(manifest.version!==audit.version||manifest.manifest_version!==3)throw Error('Unexpected installed extension manifest version');
  const publicKeyId=manifest.key===undefined?null:keyExtensionId(manifest.key);
  if(publicKeyId!==null&&publicKeyId!==target.id)throw Error('Installed public key does not match the Store target');
  const semanticSha256=manifestSemanticDigest(manifest);
  if(semanticSha256!==audit.manifestSemanticSha256)throw Error('Installed manifest differs from the audited manifest beyond a matching public key');
  const sources=[];
  for(const [relative,expected] of Object.entries(audit.sources)){
    const actual=sha256(await boundedFile(root,relative,1048576));sources.push({path:relative,sha256:actual,expectedSha256:expected,verified:actual===expected});
    if(actual!==expected)throw Error(`Installed source digest mismatch: ${relative}`);
  }
  const declaredRulesets=manifest.declarative_net_request?.rule_resources?.map(rule=>rule.id)??[];
  if(!declaredRulesets.length||declaredRulesets.length>256||!declaredRulesets.every(id=>typeof id==='string'&&id.length<=128))throw Error('Invalid installed ruleset declarations');
  return {version:manifest.version,manifestVersion:manifest.manifest_version,activeDirectory:path.basename(root),preferences:summarizePreferences(preferences),
    manifest:{rawSha256:sha256(manifestBytes),auditedRawSha256:audit.manifestRawSha256,rawDigestMatches:sha256(manifestBytes)===audit.manifestRawSha256,semanticSha256,expectedSemanticSha256:audit.manifestSemanticSha256,semanticVerified:true,matchingPublicKeyInserted:publicKeyId!==null},sources,declaredRulesets};
}
export function validRulesetResponse(value,declaredRulesets){return Array.isArray(value)&&value.length>0&&value.length<=256&&new Set(value).size===value.length&&value.every(id=>typeof id==='string'&&id.length<=128&&declaredRulesets.includes(id));}
const normalize=value=>String(value??'').trim().replace(/\s+/g,' ').replace(/[“”]/g,'"');
const strings=record=>[record?.title,record?.description,record?.value].filter(value=>typeof value==='string').map(normalize).filter(Boolean);
export function inspectCompatPrompt(probe,{pid,operation,platform=process.platform,target=COMPAT_TARGET}){
  const inspection=probe.dialogInspection,nativeWindow=record=>['AXWindow','ControlType.Window'].includes(record?.role);
  const windowVerified=probe.status==='ready'&&probe.identity?.verified===true&&probe.identity.pid===pid&&nativeWindow(inspection?.window)&&inspection.window.windowRoleVerified===true&&(platform!=='win32'||inspection.window.nativeWindowOwnershipVerified===true);
  const focusChain=inspection?.focused?.windowOwnershipVerified===true&&inspection.window?.windowOwnershipVerified===true&&
    ((nativeWindow(inspection.focused)&&(inspection.ancestors??[]).length===0)||(inspection.ancestors??[]).some(record=>nativeWindow(record)&&record.windowOwnershipVerified===true));
  const proofKind=inspection?.proofKind??(focusChain?'focused-ancestry':null);
  const focused=windowVerified&&proofKind==='focused-ancestry'&&focusChain;
  const subtree=windowVerified&&platform==='darwin'&&proofKind==='owned-visible-window'&&probe.accessibility?.applicationHidden===false&&inspection.window.minimized===false&&inspection.window.ownWindowSubtreeVerified===true;
  const owns=record=>proofKind==='focused-ancestry'?record?.windowOwnershipVerified===true:proofKind==='owned-visible-window'?record?.ownWindowSubtreeVerified===true:false;
  const install=operation==='accept-install';if(!install&&operation!=='confirm-remove')throw Error('Unsupported Store action');
  const heading=`${install?'Add':'Remove'} "${target.name}"?`,affirmative=install?'Add extension':'Remove';
  const candidates=(inspection?.containers??[]).slice(0,4).map(container=>{
    const owner=container.owningWindow,owned=owns(container)&&(focused||subtree&&owner?.ownerPID===pid&&owner.windowRoleVerified===true&&owner.minimized===false&&owner.applicationHidden===false);
    const records=[container,...(container.controls??[])].slice(0,128).filter(owns),text=[...new Set(records.flatMap(strings))];
    const buttons=records.filter(record=>/button/i.test(record.role??''));
    const add=buttons.filter(record=>strings(record).includes(affirmative)&&record.enabled===true),cancel=buttons.filter(record=>strings(record).includes('Cancel')&&record.enabled===true);
    const targetMatched=text.includes(heading),permissionTextMatched=!install||text.includes(UBOL_PERMISSION);
    const checkbox=records.filter(record=>/checkbox/i.test(record.role??'')&&strings(record).some(value=>/report abuse/i.test(value)));
    const knownUnchecked=record=>record.checked===false||record.toggleState==='Off'||record.value===false||record.value===0||record.value==='0';
    const reportAbuseState=checkbox.length===0?'absent':checkbox.every(knownUnchecked)?'unchecked':'unknown-or-checked';
    return {owned,role:container.role,selectionReason:container.selectionReason??null,targetMatched,heading,affirmative,affirmativeEnabled:add.length>0,cancelEnabled:cancel.length>0,permissionTextMatched,
      nativeSheetRoleVerified:container.nativeSheetRoleVerified===true,reportAbuseState,text:text.slice(0,64),buttons:buttons.slice(0,24).map(record=>({role:record.role,labels:strings(record),enabled:record.enabled}))};
  });
  const matched=candidates.find(candidate=>candidate.owned&&candidate.targetMatched&&candidate.affirmativeEnabled&&candidate.cancelEnabled&&candidate.permissionTextMatched);
  return {targetPromptObserved:inspection?.status==='observed'&&Boolean(matched),proofKind,ownedNativeWindowVerified:windowVerified,matched:matched??null,candidates};
}
export function verifyActionResult(result,{browser,operation,target=COMPAT_TARGET,platform=process.platform}){
  if(!['accept-install','confirm-remove'].includes(operation))return false;
  const identity=result?.identity,prompt=result?.prompt,expectedLabel=operation==='accept-install'?'Add extension':'Remove';
  const samePath=(left,right)=>platform==='win32'?typeof left==='string'&&left.toLowerCase()===right.toLowerCase():left===right;
  return result?.schema===1&&result.status==='acted'&&result.actionAttempted===true&&result.actionPerformed===true&&result.actionOutcomeUncertain!==true&&result.operation===operation&&result.target===target.key&&
    identity?.verified===true&&identity.immediatelyRevalidated===true&&identity.pid===browser.child.pid&&identity.started===browser.identity.started&&samePath(identity.executable,browser.executable)&&samePath(identity.profile,browser.profile)&&
    prompt?.nativeDialogVerified===true&&prompt.targetMatched===true&&prompt.affirmativeLabel===expectedLabel&&prompt.affirmativeEnabled===true&&prompt.affirmativeUnique===true&&
    (operation==='accept-install'?prompt.permissionTextMatched===true:prompt.reportAbuseUncheckedOrAbsent===true)&&
    ['AXPress','UIA.Invoke','native-mouse-click'].includes(result.actionType);
}
export function classifyActionReceipt(result,context){
  const target=context.target??COMPAT_TARGET;
  const complete=result?.schema===1&&['acted','refused','error'].includes(result.status)&&result.operation===context.operation&&result.target===target.key&&typeof result.actionAttempted==='boolean';
  const knownNoAction=complete&&['refused','error'].includes(result.status)&&result.actionAttempted===false&&result.actionPerformed===false&&result.actionOutcomeUncertain!==true;
  const precise=context.expectedNativeIdentity;
  const verified=verifyActionResult(result,context)&&(!precise||result.identity.startSeconds===precise.startSeconds&&result.identity.startMicroseconds===precise.startMicroseconds);
  return {verified,knownNoAction,actionOutcomeUncertain:!(knownNoAction||verified)};
}

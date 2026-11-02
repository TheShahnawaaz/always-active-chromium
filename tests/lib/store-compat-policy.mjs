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
function publicRegistrationString(value,kind){
  if(typeof value!=='string')return null;
  if(kind==='version')return value.length<=80&&/^\d+(?:\.\d+){0,3}$/.test(value)?value:null;
  const basename=path.win32.basename(path.posix.basename(value));return Buffer.byteLength(basename)<=160?basename:null;
}
function targetPreferenceShape(entry){
  const limits={maxBytes:16384,maxTopLevelKeys:64,maxNestedKeys:16,maxArrayItems:16,maxDepth:2,maxNodes:128,maxKeyBytes:128};
  const reasons=new Set();let inspectedNodes=0;
  const type=value=>value===null?'null':Array.isArray(value)?'array':typeof value;
  const stringMetadata=value=>({utf16Length:value.length,utf8Bytes:Buffer.byteLength(value),sha256Utf8:sha256(value)});
  const describe=(value,depth,route)=>{
    const result={type:type(value)};
    if(inspectedNodes>=limits.maxNodes){result.status='unknown-node-budget';reasons.add('node-budget');return result;}inspectedNodes++;
    if(typeof value==='boolean'){result.value=value;return result;}
    if(typeof value==='number'){result.finite=Number.isFinite(value);if(result.finite)result.value=value;else{result.status='unknown-nonfinite-number';reasons.add('nonfinite-number');}return result;}
    if(typeof value==='string'){
      Object.assign(result,stringMetadata(value));
      if(route==='path'||route==='manifest.version'){
        const publicValue=publicRegistrationString(value,route==='path'?'path':'version');
        if(publicValue!==null)result.publicValue=publicValue;else result.publicValueStatus='unknown-or-oversized-public-field';
      }
      return result;
    }
    if(value===null)return result;
    if(!value||typeof value!=='object'){result.status='unknown-json-type';reasons.add('unknown-json-type');return result;}
    if(Array.isArray(value)){
      result.length=value.length;result.items=[];
      if(depth<limits.maxDepth)for(let index=0;index<Math.min(value.length,limits.maxArrayItems);index++)result.items.push({index,...describe(value[index],depth+1,route+'[]')});
      result.omittedItems=value.length-result.items.length;if(result.omittedItems)reasons.add(depth>=limits.maxDepth?'depth-budget':'array-item-budget');return result;
    }
    const keys=Object.keys(value),selected=[],maximum=depth===0?limits.maxTopLevelKeys:limits.maxNestedKeys;
    // Preserve reader-relevant registration fields even when an unknown entry
    // has more keys than the finite evidence budget permits. No classification.
    for(const key of ['location','path','manifest','idle_install_info','version'])if(Object.hasOwn(value,key)&&selected.length<maximum)selected.push(key);
    for(const key of keys){if(selected.length>=maximum)break;if(!selected.includes(key))selected.push(key);}
    result.keyCount=keys.length;result.fields=[];
    if(depth<limits.maxDepth)for(const key of selected){
      const keyBytes=Buffer.byteLength(key);
      if(keyBytes>limits.maxKeyBytes||depth>0&&!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)){
        result.fields.push({key:null,keyUtf8Bytes:keyBytes,keySha256Utf8:sha256(key),type:type(value[key]),status:keyBytes>limits.maxKeyBytes?'unknown-oversized-key':'unknown-nonschema-nested-key'});
        reasons.add(keyBytes>limits.maxKeyBytes?'key-byte-budget':'nonschema-nested-key');continue;
      }
      result.fields.push({key,...describe(value[key],depth+1,route?route+'.'+key:key)});
    }
    result.omittedKeys=keys.length-result.fields.length;result.keySetComplete=result.omittedKeys===0&&result.fields.every(field=>field.key!==null);
    if(result.omittedKeys)reasons.add(depth>=limits.maxDepth?'depth-budget':'key-count-budget');return result;
  };
  const shape=describe(entry,0,'');
  shape.schema=1;shape.limits=limits;
  const rootObject=entry!==null&&typeof entry==='object'&&!Array.isArray(entry);
  const size=()=>Buffer.byteLength(JSON.stringify({report:{observations:{installedAudit:{preferences:{entries:[{shape}]}}}}},null,2));
  const finish=()=>{shape.inspectedNodes=inspectedNodes;shape.truncated=reasons.size>0;shape.status=rootObject?(shape.truncated?'bounded':'complete'):'unknown-entry-type';shape.unknownReasons=[...reasons].slice(0,12);};
  finish();
  while(size()>limits.maxBytes){
    let selected=null;
    const visit=(record,depth)=>{
      if(depth>0&&(record.fields?.length||record.items?.length)&&(!selected||depth>selected.depth))selected={record,depth};
      for(const field of record.fields??[])visit(field,depth+1);for(const item of record.items??[])visit(item,depth+1);
    };
    visit(shape,0);const record=selected?.record??shape;
    if(record.fields?.length){record.fields.pop();record.omittedKeys++;record.keySetComplete=false;}
    else if(record.items?.length){record.items.pop();record.omittedItems++;}
    else throw Error('Target preference shape exceeds fixed metadata budget');
    reasons.add('serialized-byte-budget');finish();
  }
  return shape;
}
export async function inspectTargetPreferences(profile,target=COMPAT_TARGET){
  const parsedFiles=[],entries=[],errors=[],registrationShapeUncertainty=[];
  for(const name of ['Preferences','Secure Preferences']){
    try{
      const bytes=await boundedFile(profile,`Default/${name}`,8388608),data=JSON.parse(bytes.toString('utf8'));
      const dictionary=value=>value!==null&&typeof value==='object'&&!Array.isArray(value);
      if(!dictionary(data))registrationShapeUncertainty.push({file:name,reason:'preferences-root-not-dictionary'});
      else if(Object.hasOwn(data,'extensions')&&!dictionary(data.extensions))registrationShapeUncertainty.push({file:name,reason:'extensions-not-dictionary'});
      else if(data.extensions&&Object.hasOwn(data.extensions,'settings')&&!dictionary(data.extensions.settings))registrationShapeUncertainty.push({file:name,reason:'settings-not-dictionary'});
      parsedFiles.push(name);const settings=data.extensions?.settings??{};
      if(Object.hasOwn(settings,target.id)){
        const entry=settings[target.id];
        const record={file:name,version:publicRegistrationString(entry?.manifest?.version,'version'),
          state:typeof entry?.state==='boolean'||typeof entry?.state==='number'&&Number.isFinite(entry.state)?entry.state:null,shape:targetPreferenceShape(entry)};
        // Source verification still needs the full active path internally. It
        // must not leak if this diagnostic object is serialized before summary.
        Object.defineProperty(record,'path',{value:typeof entry?.path==='string'?entry.path:null,enumerable:false});entries.push(record);
        if(entry===null)throw Error('Target preference entry has an unknown null shape');
      }
    }catch(error){if(error.code!=='ENOENT')errors.push({file:name,error:error.message.slice(0,500)});}
  }
  const knownEmptyDictionary=entry=>entry.shape?.schema===1&&entry.shape.type==='object'&&entry.shape.status==='complete'&&
    entry.shape.keyCount===0&&entry.shape.fields?.length===0&&entry.shape.omittedKeys===0&&entry.shape.keySetComplete===true&&
    entry.shape.truncated===false&&entry.shape.unknownReasons?.length===0;
  return {parsedFiles,entries,errors,registrationShapeUncertainty,
    targetAbsent:parsedFiles.length>0&&entries.length===0&&errors.length===0,
    targetRegistrationAbsent:parsedFiles.length>0&&errors.length===0&&registrationShapeUncertainty.length===0&&entries.every(knownEmptyDictionary)};
}
export function summarizePreferences(result){return {...result,entries:result.entries.map(entry=>({...entry,path:publicRegistrationString(entry.path,'path')}))};}
export function requiredRemovalEvidenceVerified(report){
  const removal=report.removal;
  return removal?.confirmed===true&&removal.confirmationOutcome==='performed-with-verified-receipt'&&
    removal.liveRegistryAbsenceVerified===true&&removal.postRestartLiveRegistryAbsenceVerified===true&&
    report.observations?.finalNormalClose?.closedNormally===true&&
    report.phases?.some(phase=>phase.name==='confirmRemove'&&phase.status==='passed')===true&&
    report.actions?.some(action=>action.operation==='confirm-remove'&&action.status==='acted'&&action.actionAttempted===true&&action.actionPerformed===true&&action.actionOutcomeUncertain===false)===true;
}
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
// Diagnostic projection only. The original native probe, never this truncated
// view, is used for permission/action gates. No paths, DOM, or foreign UI data.
export function boundedNativeDialogTrace(probe,{maxBytes=32768}={}){
  if(!Number.isInteger(maxBytes)||maxBytes<8192||maxBytes>32768)throw Error('Invalid native trace budget');
  let stringsTruncated=false;
  const short=(value,limit)=>{
    let result='';for(const character of String(value)){if(Buffer.byteLength(result+character)>limit){stringsTruncated=true;break;}result+=character;}return result;
  };
  const stringKeys=['role','subrole','title','description','selectionReason','toggleState','identifier','automationId'];
  const scalarKeys=['enabled','offscreen','checked','valueRedacted','depth','windowRelativeDepth','nativeSheetDepth','windowOwnershipVerified','ownWindowSubtreeVerified','windowRoleVerified','nativeWindowOwnershipVerified','nativeWindowHandle','nativeSheetRoleVerified','nativeSheetAncestryVerified','minimized','applicationHidden','ownerPID'];
  let labelLimit=240;
  const copyRecord=source=>{
    if(!source||typeof source!=='object')return null;
    const result={};
    for(const key of stringKeys)if(typeof source[key]==='string')result[key]=short(source[key],labelLimit);
    if(typeof source.value==='string')result.value=short(source.value,labelLimit);
    else if(source.value===null||typeof source.value==='boolean'||typeof source.value==='number'&&Number.isFinite(source.value))result.value=source.value;
    for(const key of scalarKeys)if(typeof source[key]==='boolean'||typeof source[key]==='number'&&Number.isFinite(source[key]))result[key]=source[key];
    return result;
  };
  const inspection=probe?.dialogInspection;
  const build=()=>({schema:1,purpose:'bounded-owned-native-prompt-diagnostic-only',status:short(probe?.status??'unavailable',80),platform:short(probe?.platform??'',24),
    identity:Object.fromEntries(['pid','verified','startSeconds','startMicroseconds','created'].filter(key=>['string','boolean','number'].includes(typeof probe?.identity?.[key])).map(key=>[key,typeof probe.identity[key]==='string'?short(probe.identity[key],100):probe.identity[key]])),
    accessibility:Object.fromEntries(['trusted','applicationHidden','available','nativeWindowAvailable','visibleNativeWindowAvailable'].filter(key=>typeof probe?.accessibility?.[key]==='boolean').map(key=>[key,probe.accessibility[key]])),
    helperTruncated:probe?.truncated===true,errors:(probe?.errors??[]).slice(0,8).map(value=>short(value,240)),
    dialogInspection:{status:short(inspection?.status??'unavailable',80),proofKind:typeof inspection?.proofKind==='string'?short(inspection.proofKind,80):null,focusSource:typeof inspection?.focusSource==='string'?short(inspection.focusSource,80):null,
      focused:copyRecord(inspection?.focused),ancestors:(inspection?.ancestors??[]).slice(0,16).map(copyRecord),window:copyRecord(inspection?.window),
      notes:(inspection?.notes??[]).slice(0,8).map(value=>short(value,240)),helperTruncated:inspection?.truncated===true,
      containers:(inspection?.containers??[]).slice(0,4).map((source,index)=>({...copyRecord(source),sourceContainerIndex:index,owningWindow:copyRecord(source.owningWindow),
        observedControlCount:Array.isArray(source.controls)?source.controls.length:0,controls:(source.controls??[]).slice(0,128).map((record,controlIndex)=>({...copyRecord(record),sourceControlIndex:controlIndex}))}))},
    retention:{maxBytes,maxAncestors:16,maxContainers:4,maxControlsPerContainer:128,labelByteLimit:labelLimit,
      omittedAncestors:Math.max(0,(inspection?.ancestors??[]).length-16),omittedContainers:Math.max(0,(inspection?.containers??[]).length-4),
      omittedControls:(inspection?.containers??[]).slice(0,4).reduce((sum,container)=>sum+Math.max(0,(container.controls??[]).length-128),0),
      truncated:stringsTruncated||(inspection?.ancestors??[]).length>16||(inspection?.containers??[]).length>4||(inspection?.containers??[]).slice(0,4).some(container=>(container.controls??[]).length>128)}});
  // This wrapper overestimates indentation at the actual report insertion site.
  const size=value=>Buffer.byteLength(JSON.stringify({report:{observations:{promptCaptures:{operation:{attempts:[{nativeDialogTrace:value}]}}}}},null,2));
  const priority=record=>{
    const text=strings(record).join(' '),role=record.role??'';
    if(/heading/i.test(role)||/button|checkbox/i.test(role)&&/Add extension|Cancel|Remove|Report abuse/.test(text))return 0;
    if(/^(Add|Remove) "/.test(text)||text.includes(UBOL_PERMISSION))return 1;
    if(/Window|Sheet|Dialog|Alert/.test(role))return 2;
    return 3;
  };
  let trace=build();
  for(;;){
    while(size(trace)>maxBytes){
      let selected=null;
      for(const container of trace.dialogInspection.containers)for(let index=container.controls.length-1;index>=0;index--){const rank=priority(container.controls[index]);if(!selected||rank>selected.rank)selected={container,index,rank};}
      if(!selected)break;
      selected.container.controls.splice(selected.index,1);trace.retention.omittedControls++;trace.retention.truncated=true;
    }
    if(size(trace)<=maxBytes)return trace;
    if(labelLimit<=60)throw Error('Native trace fixed metadata exceeds its finite budget');
    labelLimit=Math.floor(labelLimit/2);trace=build();trace.retention.truncated=true;
  }
}
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

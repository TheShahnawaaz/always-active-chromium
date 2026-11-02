// Strict allowlist boundary: never retain raw PowerShell/UIA output or UI text.
const roles=['renderer','gpu-process','utility','crashpad-handler','other'];
const utilities=['network','audio','storage','video-capture','other'];
const statuses=['observed','partial'];
const count=(value,max)=>Number.isInteger(value)&&value>=0&&value<=max;
const tag=value=>typeof value==='string'&&(/^(?:ERR|STATUS|RESULT_CODE)_[A-Z0-9_]{1,64}$/.test(value)||['Aw Snap','Page unresponsive','startup-choice'].includes(value));
export function sanitizeFailedWindowDiagnostic(value,{pid,started}){
  if(value?.schema!==1||value.purpose!=='owned-failed-normal-window-diagnostic'||!statuses.includes(value.status)||value.pid!==pid||value.started!==started||value.identityReverified!==true||typeof value.mainWindowHandle!=='string'||!/^[0-9a-f]{1,16}$/.test(value.mainWindowHandle)||!['untitled','fixture','other'].includes(value.mainWindowTitleCategory))throw Error('invalid_owned_window_diagnostic');
  const children=value.childRoles,uia=value.uia,address=uia?.addressBar,state=value.mainWindowState;
  if(typeof state?.ownershipVerified!=='boolean'||['visible','minimized','foreground'].some(key=>state.ownershipVerified?typeof state[key]!=='boolean':state[key]!==null)||state.ownershipVerified&&/^0+$/.test(value.mainWindowHandle))throw Error('invalid_owned_window_state');
  if(!['observed','unavailable'].includes(children?.status)||!count(children.examined,32)||!count(children.verified,32)||!count(children.unverified,32)||children.verified+children.unverified!==children.examined||typeof children.truncated!=='boolean'||children.creationAndPackageVerified!==true)throw Error('invalid_child_role_counts');
  const selectedCounts=(source,names)=>Object.fromEntries(names.map(name=>{if(!count(source?.[name],32))throw Error('invalid_role_count');return [name,source[name]];}));
  const roleCounts=selectedCounts(children.roles,roles),utilityCounts=selectedCounts(children.utilities,utilities);
  if(Object.values(roleCounts).reduce((a,b)=>a+b,0)!==children.verified||Object.values(utilityCounts).reduce((a,b)=>a+b,0)!==roleCounts.utility)throw Error('inconsistent_role_counts');
  if(!['observed','unavailable'].includes(uia?.status)||typeof uia.ownershipVerified!=='boolean'||!count(uia.visitedNodes,64)||typeof uia.truncated!=='boolean'||!Array.isArray(uia.errorTags)||uia.errorTags.length>16||!uia.errorTags.every(tag)||new Set(uia.errorTags).size!==uia.errorTags.length||!['classified','not-found','ambiguous'].includes(address?.status)||!count(address.candidates,64)||!count(value.elapsedMs,12000))throw Error('invalid_bounded_uia_observation');
  if(uia.status==='observed'&&(!uia.ownershipVerified||value.status!=='observed'||uia.reason!==null||/^0+$/.test(value.mainWindowHandle)))throw Error('unverified_uia_window');
  if(uia.status==='unavailable'&&!['not_completed','no_owned_window','bounded_owned_uia_unavailable'].includes(uia.reason))throw Error('invalid_uia_reason');
  if(address.status==='classified'?(address.candidates!==1||!['expected-loopback','blank','internal','other','unavailable'].includes(address.category)):(address.category!==null||(address.status==='not-found'?address.candidates!==0:address.candidates<2)))throw Error('invalid_address_category');
  return {schema:1,purpose:value.purpose,status:value.status,pid,started,identityReverified:true,mainWindowHandle:value.mainWindowHandle,mainWindowTitleCategory:value.mainWindowTitleCategory,
    mainWindowState:{ownershipVerified:state.ownershipVerified,visible:state.visible,minimized:state.minimized,foreground:state.foreground},childRoles:{status:children.status,examined:children.examined,verified:children.verified,unverified:children.unverified,truncated:children.truncated,creationAndPackageVerified:true,roles:roleCounts,utilities:utilityCounts},
    uia:{status:uia.status,reason:uia.reason,ownershipVerified:uia.ownershipVerified,visitedNodes:uia.visitedNodes,truncated:uia.truncated,addressBar:{status:address.status,category:address.category,candidates:address.candidates},errorTags:uia.errorTags},
    limits:{maxChildren:32,maxNodes:64,maxDepth:6,maxTags:16,maxTextLength:2048},elapsedMs:value.elapsedMs};
}
export function parseFailedWindowDiagnostic(stdout,expected,{timedOut=false}={}){
  if(typeof stdout!=='string'||Buffer.byteLength(stdout)>16384)throw Error('oversized_diagnostic_output');
  const lines=stdout.replace(/^\uFEFF/,'').trim().split(/\r?\n/).slice(-3);
  for(const line of lines.reverse()){
    try{
      const value=sanitizeFailedWindowDiagnostic(JSON.parse(line),expected);
      if(timedOut)return {...value,status:'partial',helperDeadlineExceeded:true,uia:{status:'unavailable',reason:'helper_deadline',ownershipVerified:false,visitedNodes:0,truncated:true,addressBar:{status:'not-found',category:null,candidates:0},errorTags:[]}};
      return value;
    }catch{}
  }
  throw Error('no_verified_diagnostic_receipt');
}

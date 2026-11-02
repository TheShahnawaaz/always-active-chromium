import { readFileSync } from 'node:fs';

const targets=JSON.parse(readFileSync(new URL('./store-targets.json',import.meta.url),'utf8'));
export const DEFAULT_STORE_TARGET='always-active';
export function getStoreTarget(key=DEFAULT_STORE_TARGET) {
  if(!Object.hasOwn(targets,key))throw Error(`Unsupported Store target: ${key}`);
  return Object.freeze({...targets[key]});
}
export function matchesStoreTargetUrl(value,target) {
  try {
    const actual=new URL(value),expected=new URL(target.url);
    return actual.origin===expected.origin&&actual.pathname===expected.pathname;
  }catch{return false;}
}

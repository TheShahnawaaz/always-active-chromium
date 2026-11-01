import { spawn } from 'node:child_process';
import { access, mkdir, open, readFile, rm } from 'node:fs/promises';
import path from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { CDP } from './cdp.mjs';

export async function launchBrowser({executable, profile, output, args = []}) {
  await access(executable);
  await mkdir(output, {recursive:true});
  await mkdir(profile, {recursive:true});
  // Caller-owned profile only; never inspect/reuse stock Chrome's endpoint.
  await rm(path.join(profile, 'DevToolsActivePort'), {force:true});
  const log = await open(path.join(output, 'browser.log'), 'a');
  const child = spawn(executable, [
    `--user-data-dir=${profile}`, '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0',
    '--no-first-run', '--no-default-browser-check', '--disable-background-networking',
    '--disable-component-update', '--enable-unsafe-extension-debugging',
    '--window-size=1024,768', ...args, 'about:blank'
  ], {stdio:['ignore',log.fd,log.fd]});
  await log.close();
  let error;
  child.once('error', e => { error = e; });
  for (let i = 0; i < 200; i++) {
    if (error) throw error;
    if (child.exitCode !== null) throw Error(`Browser exited ${child.exitCode}; see browser.log`);
    try {
      const [port, ws] = (await readFile(path.join(profile, 'DevToolsActivePort'), 'utf8')).trim().split(/\r?\n/);
      if (!/^\d+$/.test(port) || !ws.startsWith('/devtools/browser/')) throw Error('Bad endpoint');
      const endpoint = `ws://127.0.0.1:${port}${ws}`;
      const cdp = await CDP.connect(endpoint);
      return {cdp,child,profile,endpoint,port:Number(port),async close() {
        await cdp.send('Browser.close').catch(() => {});
        cdp.close();
        if (child.exitCode === null) await Promise.race([new Promise(resolve => child.once('exit',resolve)),delay(5000)]);
        if (child.exitCode === null) child.kill();
      }};
    } catch {}
    await delay(100);
  }
  child.kill(); throw Error('Browser did not expose an endpoint; see browser.log');
}

export async function page(cdp, url, {background = false} = {}) {
  const {targetId} = await cdp.send('Target.createTarget', {url:'about:blank',background});
  const {sessionId} = await cdp.send('Target.attachToTarget', {targetId,flatten:true});
  await cdp.send('Page.enable', {}, sessionId);
  await cdp.send('Runtime.enable', {}, sessionId);
  await cdp.send('Page.navigate', {url}, sessionId);
  for (let i=0;i<100;i++) {
    if (await cdp.evaluate(sessionId, 'Boolean(window.probeReady)').catch(() => false)) return {targetId,sessionId,url};
    await delay(50);
  }
  throw Error(`Fixture did not load: ${url}`);
}

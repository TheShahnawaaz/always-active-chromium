window.addEventListener('message', async e => {
  if (e.source !== window || e.data?.source !== 'always-active-mv3-request') return;
  const result = await chrome.runtime.sendMessage({kind:'compatibility-probe'});
  window.postMessage({source:'always-active-mv3-reply',nonce:e.data.nonce,...result},location.origin);
});

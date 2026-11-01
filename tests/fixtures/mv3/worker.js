chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (message.kind !== 'compatibility-probe') return;
  chrome.storage.local.get({count:0}, old => {
    const count=old.count+1;
    chrome.storage.local.set({count}, () => reply({count,version:chrome.runtime.getManifest().version,tabId:Number.isInteger(sender.tab?.id)}));
  });
  return true;
});

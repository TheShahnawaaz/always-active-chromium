import http from 'node:http';
import { readFile } from 'node:fs/promises';

export async function serve() {
  const html = await readFile(new URL('../fixtures/site.html', import.meta.url));
  const requests = [];
  const server = http.createServer((req,res) => {
    requests.push({url:req.url,host:req.headers.host,time:Date.now()});
    res.setHeader('Content-Type','text/html; charset=utf-8');
    res.setHeader('Cache-Control','no-store');
    res.end(html);
  });
  await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
  const port = server.address().port;
  return {server,port,url:`http://127.0.0.1:${port}`,requests,close:() => new Promise(resolve => server.close(resolve))};
}

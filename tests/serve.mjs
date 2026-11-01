import { serve } from './lib/site.mjs';
const site=await serve();
console.log(JSON.stringify({url:site.url,port:site.port}));
process.on('SIGINT',async()=>{await site.close();process.exit();});
process.on('SIGTERM',async()=>{await site.close();process.exit();});

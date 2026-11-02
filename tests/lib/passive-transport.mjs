// HTTP listener diagnostics only: never read/retain socket data or alter its flow.
import http from 'node:http';

const empty=()=>({acceptedConnections:0,closedConnections:0,closedWithError:0,bytesRead:0,bytesWritten:0,untrackedConnections:0,requests:0});
export function observePassiveTransport(server,{healthPath,maxTracked=64,maxCounter=1000000,maxBytes=1073741824}={}){
  if(typeof healthPath!=='string'||!/^\/_controller-health\/[0-9a-f-]{36}$/.test(healthPath)||![maxTracked,maxCounter,maxBytes].every(Number.isSafeInteger)||maxTracked<1||maxTracked>64||maxCounter<1||maxCounter>1000000||maxBytes<1||maxBytes>1073741824)throw Error('invalid_transport_configuration');
  const totals={controllerSelfProbe:empty(),prelaunchUnattributed:empty(),observationUnattributed:empty()};
  const live=new Map(),records=new WeakMap(),pendingControllerPorts=new Set();
  let observing=false,saturated=false,trackingComplete=true;
  const add=(object,key,value,limit)=>{
    if(!Number.isSafeInteger(value)||value<0){trackingComplete=false;return;}
    if(value>limit-object[key]){object[key]=limit;saturated=true;}else object[key]+=value;
  };
  const increment=(object,key)=>add(object,key,1,maxCounter);
  const close=record=>{
    if(record.closed)return;
    record.closed=true;live.delete(record.socket);
    const bucket=totals[record.kind];
    increment(bucket,'acceptedConnections');increment(bucket,'closedConnections');
    if(record.hadError)increment(bucket,'closedWithError');
    add(bucket,'bytesRead',record.socket.bytesRead,maxBytes);
    add(bucket,'bytesWritten',record.socket.bytesWritten,maxBytes);
  };
  server.on('connection',socket=>{
    const kind=observing?'observationUnattributed':'prelaunchUnattributed';
    if(live.size>=maxTracked){
      increment(totals[kind],'acceptedConnections');increment(totals[kind],'untrackedConnections');
      trackingComplete=false;return;
    }
    const record={socket,kind,closed:false,hadError:false};
    if(pendingControllerPorts.delete(socket.remotePort))record.kind='controllerSelfProbe';
    live.set(socket,record);records.set(socket,record);
    socket.once('close',hadError=>{record.hadError=hadError;close(record);});
  });
  return {
    startObservation(){observing=true;},
    // Match our own outbound connection, never a request path alone. No ports
    // or addresses are retained in the public report.
    markControllerSocket(socket){
      const address=server.address();
      if(!address||typeof address==='string'||socket.remoteAddress!=='127.0.0.1'||socket.remotePort!==address.port||socket.localAddress!=='127.0.0.1'||!Number.isInteger(socket.localPort))return false;
      for(const record of live.values()){
        if(record.socket.remotePort===socket.localPort&&record.kind==='prelaunchUnattributed'){
          record.kind='controllerSelfProbe';return true;
        }
      }
      if(!observing&&pendingControllerPorts.size<1){
        const port=socket.localPort;pendingControllerPorts.add(port);
        socket.once('close',()=>pendingControllerPorts.delete(port));return true;
      }
      return false;
    },
    // Call before normal request counters. Any connection accepted before
    // launch remains separate even if it closes after the browser starts.
    handlePrelaunchRequest(req,res){
      const record=records.get(req.socket);
      if(record?.kind==='observationUnattributed'||(!record&&observing)){
        increment(totals.observationUnattributed,'requests');return false;
      }
      const kind=record?.kind??'prelaunchUnattributed';
      increment(totals[kind],'requests');
      const self=kind==='controllerSelfProbe'&&req.method==='GET'&&req.url===healthPath;
      res.writeHead(self?204:404,{'Connection':'close','Cache-Control':'no-store'}).end();
      return true;
    },
    isPrelaunchSocket(socket){const record=records.get(socket);return record?record.kind!=='observationUnattributed':!observing;},
    snapshot(){
      const buckets=structuredClone(totals);
      for(const record of live.values()){
        const bucket=buckets[record.kind];increment(bucket,'acceptedConnections');
        add(bucket,'bytesRead',record.socket.bytesRead,maxBytes);add(bucket,'bytesWritten',record.socket.bytesWritten,maxBytes);
      }
      const open={controllerSelfProbe:0,prelaunchUnattributed:0,observationUnattributed:0};
      for(const record of live.values())open[record.kind]++;
      for(const [key,bucket] of Object.entries(buckets))bucket.trackedOpenConnections=open[key];
      return {schema:1,mechanism:'listener-connection-close-and-socket-byte-counters',
        attribution:'Controller self-probe socket is source-port matched. Prelaunch connections stay separate. Later loopback connections are unattributed; counters do not prove browser ownership or a parsed HTTP request.',
        ...buckets,trackingComplete,saturated,limits:{maxTracked,maxCounter,maxBytes},
        payloadRetained:false,socketFlowChanged:false};
    }
  };
}

export function controllerHealthGet(server,observer,{healthPath,timeoutMs=2000}={}){
  if(!Number.isInteger(timeoutMs)||timeoutMs<1||timeoutMs>2000)throw Error('invalid_health_timeout');
  const started=Date.now();
  return new Promise(resolve=>{
    let request,response,finished=false,matched=false,responseStatus=null,responseBytes=0;
    const finish=(status,error=null)=>{
      if(finished)return;finished=true;clearTimeout(timer);
      response?.destroy();request?.destroy();
      resolve({status,scope:'Controller-only dedicated loopback health GET before browser launch; excluded from observation counters.',
        elapsedMs:Date.now()-started,timeoutMs,controllerSocketMatched:matched,responseStatus,responseBytes,error});
    };
    const timer=setTimeout(()=>finish('failed','deadline'),timeoutMs);
    try{
      const address=server.address();
      if(!address||typeof address==='string')return finish('failed','listener_unavailable');
      request=http.get({host:'127.0.0.1',port:address.port,path:healthPath,agent:false,headers:{Connection:'close'}},incoming=>{
        response=incoming;responseStatus=incoming.statusCode;
        // Consume only our own bounded health response, never listener data.
        incoming.on('data',chunk=>{responseBytes+=chunk.length;if(responseBytes>1024)finish('failed','response_limit');});
        incoming.once('error',()=>finish('failed','response_error'));
        incoming.once('end',()=>finish(matched&&responseStatus===204&&responseBytes===0?'passed':'failed',matched&&responseStatus===204&&responseBytes===0?null:'unexpected_response'));
      });
      request.once('socket',socket=>{
        const mark=()=>{matched=observer.markControllerSocket(socket);};
        if(socket.connecting)socket.once('connect',mark);else mark();
      });
      request.once('error',()=>finish('failed','request_error'));
    }catch{finish('failed','request_setup_failed');}
  });
}

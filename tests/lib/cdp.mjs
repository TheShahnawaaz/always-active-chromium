import { EventEmitter } from 'node:events';

// Test-only CDP transport. The shipped browser needs no debugging connection.
export class CDP extends EventEmitter {
  pending = new Map();
  nextId = 0;
  static async connect(endpoint) {
    const u = new URL(endpoint);
    if (u.protocol !== 'ws:' || !['127.0.0.1', 'localhost', '[::1]'].includes(u.hostname)) throw Error('Only loopback CDP is allowed.');
    const socket = new WebSocket(endpoint);
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(Error('CDP connection timeout')), 10000);
      socket.addEventListener('open', () => { clearTimeout(timeout); resolve(); }, {once:true});
      socket.addEventListener('error', () => { clearTimeout(timeout); reject(Error('CDP connection failed')); }, {once:true});
    });
    return new CDP(socket);
  }
  constructor(socket) {
    super(); this.socket = socket;
    socket.addEventListener('message', e => {
      const m = JSON.parse(e.data);
      if (!m.id) return this.emit(m.method, m.params ?? {}, m.sessionId);
      const p = this.pending.get(m.id);
      if (!p) return;
      this.pending.delete(m.id); clearTimeout(p.timeout);
      if (m.error) p.reject(Error(`${p.method}: ${m.error.message}`)); else p.resolve(m.result ?? {});
    });
    socket.addEventListener('close', () => {
      for (const p of this.pending.values()) { clearTimeout(p.timeout); p.reject(Error(`CDP disconnected: ${p.method}`)); }
      this.pending.clear(); this.emit('disconnect');
    });
  }
  send(method, params = {}, sessionId) {
    if (this.socket.readyState !== WebSocket.OPEN) return Promise.reject(Error('CDP closed'));
    const id = ++this.nextId;
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => { this.pending.delete(id); reject(Error(`CDP timeout: ${method}`)); }, 15000);
      this.pending.set(id, {resolve,reject,timeout,method});
      this.socket.send(JSON.stringify({id,method,params,...(sessionId ? {sessionId} : {})}));
    });
  }
  async evaluate(sessionId, expression, options = {}) {
    const r = await this.send('Runtime.evaluate', {expression,returnByValue:true,awaitPromise:true,...options}, sessionId);
    if (r.exceptionDetails) throw Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
    return r.result.value;
  }
  close() { this.socket.close(); }
}

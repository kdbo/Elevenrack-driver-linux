const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const { webcrypto } = require('node:crypto');
const source = fs.readFileSync(path.join(__dirname, '../frontend/native.js'), 'utf8');
function load(onInvoke = async () => null) {
  const listeners = new Map(), calls = [];
  class BrowserSocket { constructor(url) { this.url = url; } }
  const context = { EventTarget, Event, MessageEvent, console, crypto:webcrypto, WebSocket:BrowserSocket,
    document:{addEventListener(){}}, addEventListener(){}, dispatchEvent(){},
    __TAURI__:{ core:{invoke:async (command, args) => { calls.push([command,args]); return onInvoke(command,args); }},
      event:{listen:async (name,callback) => {listeners.set(name,callback); return () => listeners.delete(name);}} }};
  context.window=context;vm.createContext(context);vm.runInContext(source,context);
  return {context,calls,listeners,BrowserSocket};
}
const tick = () => new Promise(resolve => setImmediate(resolve));
test('every Electron preload API has an explicit Tauri compatibility mapping', () => {
  const {context}=load();
  const preload=fs.readFileSync(path.join(__dirname,'../../editor/preload.js'),'utf8');
  const names=[...preload.matchAll(/^  (\w+):/gm)].map(m=>m[1]);
  assert.ok(names.length>40);
  for (const name of names) assert.ok(name in context.electronAPI, name);
  assert.equal(context.electronAPI.isTauri,true);assert.equal(context.electronAPI.isElectron,false);
});
test('MIDI IPC preserves ordering, filters sessions and cleans up', async () => {
  let release;
  const {context,calls,listeners}=load(async (command,args) => {
    if(command==='midi_command' && args.message.hex==='first') await new Promise(resolve=>release=resolve);
    return args.message?.cmd==='list_ports'?{type:'ports',devices:[]}:null;
  });
  const socket=new context.WebSocket('ws://localhost:57121');const incoming=[];
  socket.onmessage=e=>incoming.push(JSON.parse(e.data));await tick();
  assert.equal(socket.readyState,1);assert.equal(incoming[0].type,'ports');
  socket.send(JSON.stringify({cmd:'send',hex:'first'}));socket.send(JSON.stringify({cmd:'send',hex:'second'}));await tick();
  assert.equal(calls.filter(c=>c[1].message?.cmd==='send').length,1);release();await tick();
  assert.deepEqual(calls.filter(c=>c[1].message?.cmd==='send').map(c=>c[1].message.hex),['first','second']);
  const emit=listeners.get('native-midi');emit({payload:{session:'another-session',message:{type:'midi_in'}}});
  emit({payload:{session:socket.session,message:{type:'midi_in',bytes:[1]}}});
  assert.equal(incoming.filter(e=>e.type==='midi_in').length,1);
  socket.close();await tick();assert.equal(socket.readyState,3);assert.equal(listeners.has('native-midi'),false);
  assert.equal(calls.at(-1)[1].message.cmd,'disconnect');assert.equal(calls.at(-1)[1].session,socket.session);
});
test('other URLs retain the browser WebSocket implementation', () => {
  const {context,BrowserSocket}=load();assert.ok(new context.WebSocket('ws://example.test:1234') instanceof BrowserSocket);
});
test('content policy preserves legacy inline layouts without allowing remote content', () => {
  const config=JSON.parse(fs.readFileSync(path.join(__dirname,'../src-tauri/tauri.conf.json'),'utf8'));
  const csp=config.app.security.csp;
  assert.match(csp,/style-src-attr 'unsafe-inline'/);
  assert.match(csp,/object-src 'none'/);
  assert.match(csp,/connect-src ipc: http:\/\/ipc\.localhost/);
});
test('MIDI pacing uses a native wait with the requested duration', async () => {
  const {context,calls}=load(async () => true);
  const transport=fs.readFileSync(path.join(__dirname,'../../editor/src/js/transport.js'),'utf8');
  const start=transport.indexOf('function sleep(ms) {');
  vm.runInContext(transport.slice(start,transport.indexOf('\n}',start)+2),context);
  await context.sleep(35);
  assert.deepEqual(JSON.parse(JSON.stringify(calls.at(-1))),['host_call',{method:'midiDelay',args:[35]}]);
});

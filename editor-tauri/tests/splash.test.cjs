const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
test('startup progress never moves backwards and retry resets it', async () => {
  const elements = new Map(), listeners = new Map();
  const get = id => {
    if (!elements.has(id)) elements.set(id,{style:{},classList:{add(){},remove(){}},getBoundingClientRect:()=>({width:22,height:10})});
    return elements.get(id);
  };
  const calls=[];
  const context={document:{getElementById:get},innerWidth:520,innerHeight:380,
    requestAnimationFrame:callback=>callback(),
    __TAURI__:{core:{invoke:async (name,args)=>{calls.push(args);return args.method==='getAppVersion'?'test':true;}},
      event:{listen:async (name,callback)=>{listeners.set(name,callback);return ()=>{};}}}};
  context.window=context;vm.createContext(context);
  await vm.runInContext(fs.readFileSync(path.join(__dirname,'../frontend/splash.js'),'utf8'),context);
  const update=data=>listeners.get('splashProgress')({payload:[data]});
  update({message:'Reading preset',fraction:.6});
  assert.equal(get('progress-bar').style.width,'60%');
  update({message:'Reading controls',fraction:.9});
  update({message:'Waiting for amplifier reply',fraction:.72});
  assert.equal(get('progress-bar').style.width,'90%');
  assert.equal(get('status-text').textContent,'Waiting for amplifier reply');
  get('btn-startup-retry').onclick();
  assert.equal(get('progress-bar').style.width,'5%');
  assert.ok(calls.some(c=>c.method==='splashReady' && c.args[0].barVisible));
  assert.equal(calls.at(-1).method,'splashRetry');
});

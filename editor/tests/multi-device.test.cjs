const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../src/js/transport.js'),'utf8');
const context={};vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('function linuxRackPairs('),source.indexOf('function populateLinuxRacks(')),context);
const port=(id,kind,index)=>({deviceId:id,kind,index,name:'Eleven Rack:Eleven Rack Rig '+index+':0',desc:id});
test('two identical names group by physical identity, independent of port order',()=>{
 const pairs=context.linuxRackPairs([port('b','out',4),port('a','in',1),port('b','in',3),port('a','out',2)]);
 assert.equal(pairs.length,2);
 assert.equal(pairs.find(p=>p.id==='a').outs[0].index,2);
 assert.equal(pairs.find(p=>p.id==='b').ins[0].index,3);
});
test('incomplete, ambiguous and external pairs cannot be selected',()=>{
 assert.equal(context.linuxRackPairs([port('a','in',1),port('b','out',2)]).length,0);
 assert.equal(context.linuxRackPairs([port('a','in',1),port('a','in',2),port('a','out',3)]).length,0);
 assert.equal(context.linuxRackPairs([{...port('a','in',1),name:'Eleven Rack External'},port('a','out',2)]).length,0);
});
test('device selector is hidden with one Rack and shown with two',()=>{
 const picker={style:{},appendChild(){}};
 const sandbox={document:{getElementById:()=>picker,createElement:()=>({})},bridgeInIdx:null,bridgeMidiReady:false,
   window:{electronAPI:{getSavedPorts:()=>new Promise(()=>{})}},clearTimeout(){},startupGateTimer:null};
 vm.createContext(sandbox);
 vm.runInContext(source.slice(source.indexOf('var rackPickerPending'),source.indexOf('async function switchLinuxRack')),sandbox);
 sandbox.populateLinuxRacks([port('a','in',1),port('a','out',2)]);
 assert.equal(picker.style.display,'none');
 sandbox.populateLinuxRacks([port('a','in',1),port('a','out',2),port('b','in',3),port('b','out',4)]);
 assert.equal(picker.style.display,'');
});
test('startup migrates a saved one-Rack pair without waiting for a device dialog',async()=>{
 const picker={style:{},appendChild(){}};
 const ports=[port('a','in',1),port('b','in',3),port('b','out',4),port('a','out',2)];
 let connected=null,dialogs=0;
 const sandbox={document:{getElementById:()=>picker,createElement:()=>({})},bridgeInIdx:null,bridgeMidiReady:false,
   bridgePorts:ports,hasCompletedInitialConnect:false,
   window:{electronAPI:{getSavedPorts:async()=>({inName:ports[0].name,outName:ports[3].name}),chooseRack:async()=>{dialogs++;return null;}}},
   clearTimeout(){},startupGateTimer:null,setStatus(){},finishPortSelection:(i,o)=>{connected=[i,o];}};
 vm.createContext(sandbox);
 vm.runInContext(source.slice(source.indexOf('var rackPickerPending'),source.indexOf('async function switchLinuxRack')),sandbox);
 sandbox.populateLinuxRacks(ports);
 await new Promise(resolve=>setImmediate(resolve));
 assert.deepEqual(connected,[1,2]);assert.equal(dialogs,0);
});

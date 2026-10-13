const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const html = fs.readFileSync('editor/src/index.html', 'utf8');
const code = html.slice(html.indexOf('const editorUpdateNotice ='), html.indexOf('window.openEditorAbout ='));
const controls = {};
function element() { return { hidden: false, disabled: false, textContent: '', addEventListener(name, cb) { this[name] = cb; } }; }
const document = { createElement: element, body: { appendChild(el) { controls.notice = el; } }, getElementById(id) { return controls[id] ||= element(); } };
let result = { status: 'available', version: '<beta9>' };
let offers = 0;
const context = vm.createContext({document, window: {electronAPI: {checkUpdates: async () => result, showUpdateOffer: async () => offers++}}, setTimeout() {} });
vm.runInContext(code, context);
(async () => {
  await vm.runInContext('checkEditorUpdates(false)', context);
  assert.equal(controls.notice.hidden, false);
  assert(controls.notice.textContent.includes('<beta9>'));
  assert.equal(offers, 0); // Startup never opens a modal or installs anything.
  await vm.runInContext('checkEditorUpdates(true)', context);
  assert.equal(offers, 1);
  result = {status:'current'};
  await vm.runInContext('checkEditorUpdates(true)', context);
  assert.equal(controls.notice.hidden, true);
  result = {status:'offline',message:'Offline'};
  await vm.runInContext('checkEditorUpdates(true)', context);
  assert.equal(controls['about-update-status'].textContent,'Offline');
  assert.equal(controls['about-check-updates'].disabled,false);
  console.log('Editor startup notice, manual offer and offline UI OK');
})().catch(e => { console.error(e); process.exitCode = 1; });

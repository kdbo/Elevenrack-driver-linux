const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function setup() {
  const nodes = new Map();
  const context = {
    document: { getElementById(id) {
      if (!nodes.has(id)) {
        const classes = new Set();
        nodes.set(id, { hidden: false, style: {}, classList: {
          remove(...names) { names.forEach(n => classes.delete(n)); },
          toggle(name, on) { if (on) classes.add(name); else classes.delete(name); },
          contains(name) { return classes.has(name); },
        }, addEventListener() {} });
      }
      return nodes.get(id);
    } },
    window: { addEventListener() {} }, Date,
    tunerOn: true, bridgeMidiReady: true, CC_TUNER: 69,
    sends: [], timers: new Map(), sendCC() {},
    sendHex(hex) { context.sends.push(hex); return true; },
    setInterval(fn) { context.timers.set(1, fn); return 1; },
    clearInterval(id) { context.timers.delete(id); },
    handleTunerCC() { context.tunerOn = false; context.syncSoftwareTuner(); },
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../src/js/tuner.js'), 'utf8'), context);
  return { context, nodes };
}
const reply = (note, tune) => [0xF0, 0x13, 0x0B, 0x0F, 0x12, 0x42, note, tune, 0xF7];

test('reference writes match controlled capture and update only from Rack replies', () => {
  const { context: c, nodes } = setup();
  assert.equal(c.encodeTunerReference(440), 'F0 13 0B 0F 00 41 40 00 F7');
  assert.equal(c.encodeTunerReference(438), 'F0 13 0B 0F 00 41 3E 00 F7');
  for (const invalid of [409,481,440.5,NaN]) assert.equal(c.encodeTunerReference(invalid), null);
  assert.equal(c.changeTunerReference(440), true);
  assert.equal(nodes.get('tuner-reference-status').textContent, 'Waiting for Rack…');
  c.handleTunerNeedleReply([240,19,11,15,2,65,64,0,247]);
  assert.equal(nodes.get('tuner-reference').value, '440');
  assert.equal(nodes.get('tuner-reference-status').textContent, '');
  assert.equal(c.handleTunerReferenceReply([240,19,11,15,2,65,64,1,247]), false);
  c.bridgeMidiReady = false;
  assert.equal(c.changeTunerReference(438), false);
});

test('recognizes hardware tuner chain at startup without treating it as a rig', () => {
  const source = fs.readFileSync(path.join(__dirname, '../src/js/sysex-handler.js'), 'utf8');
  const start = source.indexOf('function handleChainMap(data)');
  const end = source.indexOf('\n  const trip = [];', start);
  let state = null;
  let readinessChecks = 0;
  const c = { initialChainMapDone: false, checkInitialPopulateReady() { readinessChecks++; }, appLog() {}, handleTunerCC(value) { state = value; } };
  vm.createContext(c);
  vm.runInContext(source.slice(start, end) + '\n}', c);
  c.handleChainMap([240,19,11,15,18,33,2,55,112,11,37,111,0,247]);
  assert.equal(state, 127);
  assert.equal(c.initialChainMapDone, true);
  assert.equal(readinessChecks, 1);
  state = null; c.handleChainMap([240,19,11,15,18,33,0,247]);
  assert.equal(state, null);
});

test('decodes chromatic notes, center, flat, sharp and idle', () => {
  const { context: c } = setup();
  for (const [raw, note, octave] of [[18,'E',2],[23,'A',2],[28,'D',3],[33,'G',3],[37,'B',3],[42,'E',4]]) {
    const reading = c.decodeTunerReply(reply(raw, 64));
    assert.equal(reading.note, note); assert.equal(reading.octave, octave);
    assert.equal(reading.deviation, 0);
  }
  assert.equal(c.decodeTunerReply(reply(0x03, 60)).deviation, -4);
  assert.equal(c.decodeTunerReply(reply(0x03, 68)).deviation, 4);
  assert.equal(c.decodeTunerReply(reply(0, 64)).idle, true);
  assert.equal(c.decodeTunerReply(reply(0x1C, 64)).note, 'D');
  assert.equal(c.decodeTunerReply(reply(0x24, 128)), null);
  assert.equal(c.decodeTunerReply(reply(0x24, 64).slice(0, -1)), null);
});
test('polls once per interval and stops on off or disconnect', () => {
  const { context: c, nodes } = setup();
  c.syncSoftwareTuner(); c.syncSoftwareTuner();
  assert.equal(c.timers.size, 1); assert.equal(c.sends.length, 2);
  assert.equal(c.sends[0], 'F0 13 0B 0F 01 41 F7');
  assert.equal(c.sends[1], 'F0 13 0B 0F 01 42 F7');
  c.handleLiveTunerReply(reply(0x12, 64));
  assert.equal(nodes.get('tuner-note').textContent, 'E2');
  assert.equal(nodes.get('tuner-reading').textContent, '0');
  assert.equal(nodes.get('tuner-led-left').classList.contains('tuned'), true);
  assert.equal(nodes.get('tuner-led-right').classList.contains('tuned'), true);
  c.handleLiveTunerReply(reply(0x24, 60));
  assert.equal(nodes.get('tuner-reading').textContent, '−4');
  assert.equal(nodes.get('tuner-led-left').classList.contains('flat'), true);
  assert.equal(nodes.get('tuner-led-right').classList.contains('tuned'), false);
  c.handleTunerNeedleReply([0xF0,0x13,0x0B,0x0F,0,0x41,44,1,0xF7]);
  assert.equal(nodes.get('tuner-needle').style.transform, 'rotate(-27.5deg)');
  c.handleLiveTunerReply(reply(0x24, 68));
  assert.equal(nodes.get('tuner-reading').textContent, '+4');
  assert.equal(nodes.get('tuner-led-right').classList.contains('sharp'), true);
  c.handleLiveTunerReply(reply(0x24, 64));
  assert.equal(nodes.get('tuner-needle').style.transform, 'rotate(0deg)');
  c.handleLiveTunerReply(reply(0, 64));
  assert.equal(nodes.get('tuner-needle').hidden, true);
  assert.equal(nodes.get('tuner-led-left').classList.contains('tuned'), false);
  c.bridgeMidiReady = false; c.timers.get(1)();
  assert.equal(c.timers.size, 0); assert.equal(nodes.get('tuner-panel').hidden, true);
  c.bridgeMidiReady = true; c.tunerOn = true; c.syncSoftwareTuner();
  c.tunerOn = false; c.syncSoftwareTuner(); assert.equal(c.timers.size, 0);
});

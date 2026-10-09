const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function setup() {
  const nodes = new Map();
  const context = {
    document: { getElementById(id) {
      if (!nodes.has(id)) nodes.set(id, { hidden: false, style: {}, classList: { remove() {}, toggle() {} }, addEventListener() {} });
      return nodes.get(id);
    } },
    window: { addEventListener() {} }, Date,
    tunerOn: true, bridgeMidiReady: true, CC_TUNER: 69,
    sends: [], timers: new Map(), sendCC() {},
    sendHex(hex) { context.sends.push(hex); },
    setInterval(fn) { context.timers.set(1, fn); return 1; },
    clearInterval(id) { context.timers.delete(id); },
    handleTunerCC() { context.tunerOn = false; context.syncSoftwareTuner(); },
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../src/js/tuner.js'), 'utf8'), context);
  return { context, nodes };
}
const reply = (note, tune) => [0xF0, 0x13, 0x0B, 0x0F, 0x12, 0x42, note, tune, 0xF7];

test('decodes chromatic notes, center, flat, sharp and idle', () => {
  const { context: c } = setup();
  assert.equal(c.decodeTunerReply(reply(0x24, 64)).note, 'E');
  assert.equal(c.decodeTunerReply(reply(0x24, 64)).octave, 2);
  assert.equal(c.decodeTunerReply(reply(0x24, 64)).deviation, 0);
  assert.equal(c.decodeTunerReply(reply(0x03, 60)).deviation, -4);
  assert.equal(c.decodeTunerReply(reply(0x03, 68)).deviation, 4);
  assert.equal(c.decodeTunerReply(reply(0, 64)).idle, true);
  assert.equal(c.decodeTunerReply(reply(0x0C, 64)), null);
  assert.equal(c.decodeTunerReply(reply(0x24, 128)), null);
  assert.equal(c.decodeTunerReply(reply(0x24, 64).slice(0, -1)), null);
});
test('polls once per interval and stops on off or disconnect', () => {
  const { context: c, nodes } = setup();
  c.syncSoftwareTuner(); c.syncSoftwareTuner();
  assert.equal(c.timers.size, 1); assert.equal(c.sends.length, 1);
  assert.equal(c.sends[0], 'F0 13 0B 0F 01 42 F7');
  c.handleLiveTunerReply(reply(0x24, 64));
  assert.equal(nodes.get('tuner-note').textContent, 'E2');
  assert.equal(nodes.get('tuner-reading').textContent, 'In tune');
  c.handleLiveTunerReply(reply(0, 64));
  assert.equal(nodes.get('tuner-needle').hidden, true);
  c.bridgeMidiReady = false; c.timers.get(1)();
  assert.equal(c.timers.size, 0); assert.equal(nodes.get('tuner-panel').hidden, true);
  c.bridgeMidiReady = true; c.tunerOn = true; c.syncSoftwareTuner();
  c.tunerOn = false; c.syncSoftwareTuner(); assert.equal(c.timers.size, 0);
});

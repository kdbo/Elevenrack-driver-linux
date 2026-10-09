/* Copyright (c) 2026 Koen de Boevé
 * SPDX-License-Identifier: MIT
 * Protocol: Charles Wardick's ElevenEdit Technical Reference, live tuner 0x42.
 */
const TUNER_QUERY = 'F0 13 0B 0F 01 42 F7';
let tunerPollTimer = null;
let tunerLastReply = 0;
let tunerNeedleLastReply = 0;
let tunerHasNote = false;
let tunerReferenceHz = null;

function encodeTunerReference(hz) {
  if (!Number.isInteger(hz) || hz < 410 || hz > 480) return null;
  // Two original-editor captures: 440->438->440 = 64->62->64.
  return 'F0 13 0B 0F 00 41 ' + (hz - 376).toString(16).padStart(2, '0').toUpperCase() + ' 00 F7';
}

function handleTunerReferenceReply(data) {
  if (data.length !== 9 || data[0] !== 0xF0 || data[1] !== 0x13 ||
      data[2] !== 0x0B || data[3] !== 0x0F ||
      (data[4] !== 2 && data[4] !== 0x12) || data[5] !== 0x41 ||
      data[7] !== 0 || data[8] !== 0xF7 || data[6] > 127) return false;
  const hz = data[6] + 376;
  if (hz < 410 || hz > 480) return false;
  tunerReferenceHz = hz;
  document.getElementById('tuner-reference').value = String(hz);
  document.getElementById('tuner-reference-status').textContent = '';
  return true;
}

function changeTunerReference(hz) {
  const hex = encodeTunerReference(hz);
  if (!hex || !bridgeMidiReady || !tunerOn) return false;
  if (!sendHex(hex)) return false;
  document.getElementById('tuner-reference-status').textContent = 'Waiting for Rack…';
  return true;
}

function setTunerNeedle(deviation) {
  const needle = document.getElementById('tuner-needle');
  needle.hidden = false;
  needle.style.transform = 'rotate(' + (Math.max(-1, Math.min(1, deviation / 40)) * 55) + 'deg)';
}

function handleTunerNeedleReply(data) {
  if (handleTunerReferenceReply(data)) return;
  if (!tunerOn || !tunerHasNote || data.length !== 9 || data[0] !== 0xF0 ||
      data[1] !== 0x13 || data[2] !== 0x0B || data[3] !== 0x0F ||
      (data[4] !== 0 && data[4] !== 2) || data[5] !== 0x41 ||
      data[6] > 127 || data[7] !== 1 || data[8] !== 0xF7) return;
  tunerNeedleLastReply = Date.now();
  setTunerNeedle(data[6] - 64);
}

function decodeTunerReply(data) {
  if (data.length !== 9 || data[0] !== 0xF0 || data[1] !== 0x13 ||
      data[2] !== 0x0B || data[3] !== 0x0F || data[4] !== 0x12 ||
      data[5] !== 0x42 || data[8] !== 0xF7 ||
      data[6] > 127 || data[7] > 127) return null;
  if (data[6] === 0 && data[7] === 64) return { idle: true };
  const notes = ['C', 'C♯', 'D', 'E♭', 'E', 'F', 'F♯', 'G', 'A♭', 'A', 'B♭', 'B'];
  // Live firmware 0157 capture: open E2=0x12, A2=0x17, D3=0x1C.
  // This is a linear semitone index, offset 22 from MIDI note numbering;
  // it is not the octave/chromatic nibble encoding described upstream.
  const midiNote = data[6] + 22;
  return { idle: false, note: notes[midiNote % 12], octave: Math.floor(midiNote / 12) - 1, deviation: data[7] - 64 };
}

function clearTunerReading(message) {
  document.getElementById('tuner-note').textContent = '—';
  document.getElementById('tuner-reading').textContent = message;
  document.getElementById('tuner-panel').classList.remove('in-tune');
  tunerHasNote = false;
  document.getElementById('tuner-led-left').classList.remove('flat', 'tuned');
  document.getElementById('tuner-led-right').classList.remove('sharp', 'tuned');
  document.getElementById('tuner-needle').hidden = true;
}

function handleLiveTunerReply(data) {
  if (!tunerOn) return;
  const reading = decodeTunerReply(data);
  if (!reading) return;
  tunerLastReply = Date.now();
  if (reading.idle) { clearTunerReading('Play a single note'); return; }
  const inTune = reading.deviation === 0;
  tunerHasNote = true;
  document.getElementById('tuner-note').textContent = reading.note + reading.octave;
  document.getElementById('tuner-reading').textContent = reading.deviation > 0
    ? '+' + reading.deviation
    : (reading.deviation < 0 ? '−' + Math.abs(reading.deviation) : '0');
  document.getElementById('tuner-panel').classList.toggle('in-tune', inTune);
  const left = document.getElementById('tuner-led-left');
  const right = document.getElementById('tuner-led-right');
  left.classList.toggle('flat', reading.deviation < 0);
  right.classList.toggle('sharp', reading.deviation > 0);
  left.classList.toggle('tuned', inTune);
  right.classList.toggle('tuned', inTune);
  // Center immediately on an authoritative in-tune reply. Otherwise prefer
  // the finer 0x41 stream, falling back to 0x42 if it is unavailable.
  if (inTune || Date.now() - tunerNeedleLastReply > 250) setTunerNeedle(reading.deviation);
}

function syncSoftwareTuner() {
  const panel = document.getElementById('tuner-panel');
  panel.hidden = !tunerOn;
  if (!tunerOn) {
    clearInterval(tunerPollTimer);
    tunerPollTimer = null;
    clearTunerReading('Play a single note');
    tunerReferenceHz = null;
    document.getElementById('tuner-reference').value = '';
    document.getElementById('tuner-reference-status').textContent = '';
    return;
  }
  if (tunerPollTimer !== null) return;
  tunerLastReply = Date.now();
  tunerNeedleLastReply = 0;
  clearTunerReading('Waiting for tuner…');
  function poll() {
    if (!bridgeMidiReady) {
      handleTunerCC(0);
      return;
    }
    sendHex(TUNER_QUERY);
    if (Date.now() - tunerLastReply > 1500) clearTunerReading('Waiting for tuner signal…');
  }
  tunerPollTimer = setInterval(poll, 66);
  sendHex('F0 13 0B 0F 01 41 F7');
  poll();
}

document.getElementById('tuner-close').addEventListener('click', function () {
  if (bridgeMidiReady && tunerOn) sendCC(CC_TUNER, 0);
});
document.getElementById('tuner-reference').addEventListener('change', function () {
  const input = document.getElementById('tuner-reference');
  if (!changeTunerReference(Number(input.value))) {
    input.value = tunerReferenceHz === null ? '' : String(tunerReferenceHz);
    document.getElementById('tuner-reference-status').textContent = 'Choose 410–480 Hz while connected';
  }
});
['down', 'up'].forEach(function (direction) {
  document.getElementById('tuner-reference-' + direction).addEventListener('click', function () {
    if (tunerReferenceHz === null) {
      document.getElementById('tuner-reference-status').textContent = 'Enter a reference frequency first';
      return;
    }
    changeTunerReference(tunerReferenceHz + (direction === 'up' ? 1 : -1));
  });
});
window.addEventListener('beforeunload', function () { clearInterval(tunerPollTimer); });

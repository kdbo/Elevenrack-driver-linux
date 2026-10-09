/* Copyright (c) 2026 Koen de Boevé
 * SPDX-License-Identifier: MIT
 * Protocol: Charles Wardick's ElevenEdit Technical Reference, live tuner 0x42.
 */
const TUNER_QUERY = 'F0 13 0B 0F 01 42 F7';
let tunerPollTimer = null;
let tunerLastReply = 0;
let tunerNeedleLastReply = 0;
let tunerHasNote = false;

function setTunerNeedle(deviation) {
  const needle = document.getElementById('tuner-needle');
  needle.hidden = false;
  needle.style.transform = 'rotate(' + (Math.max(-1, Math.min(1, deviation / 40)) * 55) + 'deg)';
}

function handleTunerNeedleReply(data) {
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
      data[6] > 127 || data[7] > 127 || (data[6] & 15) > 11) return null;
  if (data[6] === 0 && data[7] === 64) return { idle: true };
  const notes = ['C', 'C♯', 'D', 'E♭', 'E', 'F', 'F♯', 'G', 'A♭', 'A', 'B♭', 'B'];
  return { idle: false, note: notes[data[6] & 15], octave: data[6] >> 4, deviation: data[7] - 64 };
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
  document.getElementById('tuner-reading').textContent = inTune ? 'In tune' : (reading.deviation < 0 ? 'Flat — tune up' : 'Sharp — tune down');
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
window.addEventListener('beforeunload', function () { clearInterval(tunerPollTimer); });

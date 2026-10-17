#!/usr/bin/env python3
"""Record a click track through REAPER per rate/buffer and measure the recorded offset.

For each profile: set the Rack rate and PipeWire buffer through the installed
controls, generate a click track and project, start the user's normal
REAPER with a ReaScript that records, saves and quits, then measure every
click in the recording against the played click. REAPER's own recording
latency compensation stays on, so the result is the residual offset a REAPER
user gets. Main Out L must be connected to Line In L.
"""
import argparse
import array
import ctypes
import json
import math
import os
from pathlib import Path
import re
import signal
import statistics
import struct
import subprocess
import sys
import time
import uuid
import wave

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = '/usr/lib/eleven-rack/tools/eleven-rack-settings.py'
LAUNCHER = Path.home()/'.local/share/eleven-rack-local/reaper/start-reaper.sh'
REAPER = Path.home()/'Downloads/reaper782_linux_x86_64/reaper_linux_x86_64/REAPER/reaper'
RATES = (44100, 48000, 88200, 96000)
QUANTA = (64, 128, 256, 512, 1024, 2048)
PERIOD = 0.5        # seconds between clicks; first click at PERIOD
LEVEL = 0.1         # about -20 dBFS
SEARCH = 0.050      # seconds either side of the expected click
LINE_IN_L = 6       # REAPER input index of Line In L (input 7)


def guid():
    return '{%s}' % str(uuid.uuid4()).upper()


def click_burst(rate):
    length = int(0.002*rate)
    return [LEVEL*math.sin(2*math.pi*2000*i/rate)*math.sin(math.pi*i/length)**2 for i in range(length)]


def click_positions(rate, seconds):
    return [int((k+1)*PERIOD*rate) for k in range(int((seconds-PERIOD)/PERIOD))]


def write_click(path, rate, seconds):
    frames = bytearray(rate*seconds*2)
    burst = click_burst(rate)
    for start in click_positions(rate, seconds):
        for i, value in enumerate(burst):
            struct.pack_into('<h', frames, (start+i)*2, int(value*32767))
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(1); output.setsampwidth(2); output.setframerate(rate)
        output.writeframes(bytes(frames))


def track(name, rec, mainsend, items=''):
    track_id = guid()
    return f'''  <TRACK {track_id}
    NAME "{name}"
    VOLPAN 1 0 1 -1 1
    MUTESOLO 0 0 0
    IPHASE 0
    REC {rec}
    NCHAN 2
    FX 1
    TRACKID {track_id}
    MAINSEND {mainsend} 0
{items}  >
'''


def write_project(path, rate, seconds):
    item = f'''    <ITEM
      POSITION 0
      LENGTH {seconds}
      NAME Click
      VOLPAN 1 0 1 -1
      SOFFS 0
      IGUID {guid()}
      GUID {guid()}
      <SOURCE WAVE
        FILE "click.wav"
      >
    >
'''
    # Track 1 plays the clicks through the master to Main Out L/R. Track 2
    # records Line In L with monitoring off and no master send.
    path.write_text(f'''<REAPER_PROJECT 0.1 "7.82/linux-x86_64" 0
  RECORD_PATH "Media" ""
  <RECORD_CFG
    ZXZhdxgAAQ==
  >
  SAMPLERATE {rate} 1 0
  TEMPO 120 4 4 0
  MASTERHWOUT 0 0 1 0 0 0 0 -1
  MASTER_NCH 2 2
  MASTER_VOLUME 1 0 -1 -1 1
''' + track('Click - Main Out L', '0 0 0 0 0 0 0 0', 1, item)
        + track('Recording - Line In L', f'1 {LINE_IN_L} 0 0 0 0 0 0', 0) + '>\n')


def write_script(path, seconds):
    # The script starts with REAPER, before its audio device runs: wait for
    # audio, then record (1013). Stop and keep all recorded media without a
    # prompt (40667), save the project (40026) and quit (40004) at the end, or
    # when recording stops early.
    log = path.with_suffix('.log')
    path.write_text(f'''local log = io.open([[{log}]], "w")
local function note(text) log:write(string.format("%.3f %s\\n", reaper.time_precise(), text)); log:flush() end
local started, attempts, last, audio_since = nil, 0, 0, nil
local function finish(reason)
  note("finishing: " .. reason)
  reaper.Main_OnCommand(40667, 0)
  note("items after stop " .. reaper.CountMediaItems(0))
  reaper.Main_OnCommand(40026, 0)
  note("saved, quitting")
  log:close()
  reaper.Main_OnCommand(40004, 0)
end
local function step()
  local now = reaper.time_precise()
  local state, position = reaper.GetPlayState(), reaper.GetPlayPosition()
  if now - last >= 1 then
    last = now
    note(string.format("audio %d state %d position %.2f", reaper.Audio_IsRunning(), state, position))
  end
  if not started then
    if reaper.Audio_IsRunning() ~= 1 then audio_since = nil; return true end
    audio_since = audio_since or now
    if now - audio_since < 2 then return true end
    attempts = attempts + 1
    for i = 0, reaper.CountTracks(0) - 1 do
      local t = reaper.GetTrack(0, i)
      note(string.format("track %d arm %d input %d mode %d monitor %d", i + 1,
        reaper.GetMediaTrackInfo_Value(t, "I_RECARM"), reaper.GetMediaTrackInfo_Value(t, "I_RECINPUT"),
        reaper.GetMediaTrackInfo_Value(t, "I_RECMODE"), reaper.GetMediaTrackInfo_Value(t, "I_RECMON")))
    end
    note("project path " .. reaper.GetProjectPath(""))
    reaper.SetEditCurPos(0, false, false)
    reaper.Main_OnCommand(1013, 0)
    started = now
    note("record attempt " .. attempts)
    return true
  end
  if (state & 4) ~= 4 then
    if now - started < 1.5 and attempts < 3 then started = nil; audio_since = now; return true end
    finish("recording stopped early at " .. string.format("%.2f", position))
    return false
  end
  if position >= {seconds + 0.5} then finish("done"); return false end
  return true
end
local function loop()
  local ok, more = pcall(step)
  if not ok then note("error " .. tostring(more)); finish("script error"); return end
  if more then reaper.defer(loop) end
end
reaper.defer(loop)
''')


def read_mono(path):
    data = path.read_bytes()
    if data[:4] != b'RIFF' or data[8:12] != b'WAVE':
        raise ValueError('Not a WAV file: %s' % path)
    offset, fmt, body = 12, None, None
    while offset < len(data) - 8:
        chunk, size = data[offset:offset+4], struct.unpack('<I', data[offset+4:offset+8])[0]
        if chunk == b'fmt ':
            fmt = struct.unpack('<HHIIHH', data[offset+8:offset+24])
        elif chunk == b'data':
            body = data[offset+8:offset+8+size]
        offset += 8 + size + (size & 1)
    tag, channels, rate, _, align, bits = fmt
    count = len(body)//align
    body = body[:count*align]
    if tag == 3 and bits == 32:
        samples = array.array('f', body)
    elif bits == 24:
        padded = bytearray(count*channels*4)
        padded[1::4], padded[2::4], padded[3::4] = body[0::3], body[1::3], body[2::3]
        samples = array.array('f', (v/2147483648 for v in array.array('i', padded)))
    elif bits == 16:
        samples = array.array('f', (v/32768 for v in array.array('h', body)))
    else:
        raise ValueError('Unsupported WAV format')
    if channels > 1:
        samples = array.array('f', samples[0::channels])
    return rate, samples


def recorded_item(project):
    """Recorded file, its project position and source offset, from the saved project."""
    text = project.read_text()
    tracks = text.split('\n  <TRACK ')
    if len(tracks) < 3:
        raise ValueError('Recording track missing from saved project')
    take = tracks[2]
    found = re.search(r'POSITION ([\d.]+).*?SOFFS ([\d.]+).*?FILE "([^"]+)"', take, re.S)
    if not found:
        raise ValueError('No recorded item in saved project')
    return project.parent/found[3], float(found[1]), float(found[2])


def measure(project, seconds):
    rate = int(re.search(r'SAMPLERATE (\d+)', project.read_text())[1])
    recording, position, source_offset = recorded_item(project)
    rec_rate, samples = read_mono(recording)
    if rec_rate != rate:
        raise ValueError('Recording rate %d differs from project rate %d' % (rec_rate, rate))
    lib = ctypes.CDLL(str(ROOT/'build/latency/liblatency-correlation.so'))
    lib.latency_peak.argtypes = [ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_double),
                                 ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_double)]
    lib.latency_peak.restype = ctypes.c_int
    burst = click_burst(rate)
    lead, tail = 20, 20
    template = [0.0]*lead + burst + [0.0]*tail
    width, search = len(template), int(SEARCH*rate)
    reference = (ctypes.c_double*width)(*template)
    buffer = (ctypes.c_float*len(samples)).from_buffer(samples)
    energy = math.sqrt(sum(v*v for v in template))
    # Project time t lies at recording sample (t - position + source_offset) * rate.
    shift = round((source_offset - position)*rate)
    offsets, scores = [], []
    for click in click_positions(rate, seconds):
        start = click - lead + shift - search
        if start < 0 or start + 2*search + width >= len(samples):
            continue
        score = ctypes.c_double()
        lag = lib.latency_peak(ctypes.cast(ctypes.byref(buffer, start*4), ctypes.POINTER(ctypes.c_float)),
                               reference, width, 2*search+1, ctypes.byref(score))

        def value(at):
            segment = samples[start+at:start+at+width]
            norm = math.sqrt(sum(v*v for v in segment))
            return abs(sum(a*b for a, b in zip(template, segment)))/(energy*norm) if norm else 0.0
        low, mid, high = value(lag-1), abs(score.value), value(lag+1)
        curve = low - 2*mid + high
        offsets.append(lag - search + (0.5*(low-high)/curve if curve else 0.0))
        scores.append(score.value)
    if not offsets:
        raise ValueError('No clicks found in the recording')
    milliseconds = [o*1000/rate for o in offsets]
    steps = [{'click': i+1, 'from_samples': round(a, 2), 'to_samples': round(b, 2)}
             for i, (a, b) in enumerate(zip(offsets, offsets[1:])) if abs(b-a) > 1.0]
    return {'rate': rate, 'clicks': len(offsets), 'expected_clicks': len(click_positions(rate, seconds)),
            'median_offset_ms': round(statistics.median(milliseconds), 3),
            'median_offset_samples': round(statistics.median(offsets), 2),
            'min_offset_ms': round(min(milliseconds), 3), 'max_offset_ms': round(max(milliseconds), 3),
            'spread_ms': round(max(milliseconds)-min(milliseconds), 3),
            'min_match': round(min(abs(s) for s in scores), 4),
            'polarity': 'inverted' if statistics.median(scores) < 0 else 'normal',
            'steps': steps, 'recording': str(recording.relative_to(project.parent))}


def wait_until_idle(limit=30):
    """A closing REAPER holds the device briefly; rate changes need an idle Rack."""
    for _ in range(limit):
        if 'Status: Running' not in Path('/proc/asound/Rack/stream0').read_text():
            return
        time.sleep(1)


def settings(*arguments):
    return subprocess.run(['python3', SETTINGS, *arguments], check=True,
                          capture_output=True, text=True).stdout


def run_profile(directory, rate, quantum, seconds):
    directory.mkdir(parents=True)
    (directory/'Media').mkdir()
    write_click(directory/'click.wav', rate, seconds)
    project = directory/'click-test.RPP'
    write_project(project, rate, seconds)
    script = directory/'record-click.lua'
    write_script(script, seconds)
    wait_until_idle()
    settings('rate', str(rate))
    settings('buffer', str(quantum))
    environment = dict(os.environ, PIPEWIRE_QUANTUM=f'{quantum}/{rate}',
                       PIPEWIRE_LATENCY=f'{quantum}/{rate}', PIPEWIRE_RATE=f'1/{rate}')
    with (directory/'reaper.log').open('w') as log:
        # The user's normal REAPER configuration; nothing in it is changed.
        process = subprocess.Popen(['/bin/bash', str(LAUNCHER), str(REAPER), '-nosplash', str(project), str(script)],
                                   stdout=log, stderr=subprocess.STDOUT, env=environment, start_new_session=True)
        try:
            # Record which ports feed REAPER once the recording should be running.
            try:
                process.wait(timeout=min(12, seconds))
            except subprocess.TimeoutExpired:
                links = subprocess.run(['pw-link', '-l'], capture_output=True, text=True).stdout
                (directory/'links-during-recording.txt').write_text(links)
            process.wait(timeout=seconds + 90)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
            raise RuntimeError('REAPER did not finish; it was stopped (dialog or hang?)')
    return measure(project, seconds)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profiles', nargs='+', default=['44100:128', '48000:64', '48000:128', '48000:256', '96000:128'])
    parser.add_argument('--seconds', type=int, default=300, help='Click track length per profile (10..1800)')
    parser.add_argument('--repeats', type=int, default=1, help='Fresh REAPER starts per profile (1..20)')
    parser.add_argument('--analyse', type=Path, help='Only measure an existing saved click-test.RPP')
    args = parser.parse_args()
    if args.analyse:
        print(json.dumps(measure(args.analyse, args.seconds), indent=2))
        return
    if not 10 <= args.seconds <= 1800 or not 1 <= args.repeats <= 20:
        parser.error('seconds: 10..1800; repeats: 1..20')
    profiles = []
    for item in args.profiles:
        rate, quantum = map(int, item.split(':'))
        if rate not in RATES or quantum not in QUANTA:
            parser.error('Unsupported profile ' + item)
        profiles.append((rate, quantum))
    if subprocess.run(['pgrep', '-x', 'reaper'], stdout=subprocess.DEVNULL).returncode == 0:
        sys.exit('Save and close REAPER first')
    if args.output.exists():
        parser.error('Output already exists')
    args.output.mkdir(parents=True)
    previous = settings('buffer')
    previous_rate = int(re.search(r'Hardware sample rate: (\d+)', settings('rate'))[1])
    previous_buffer = re.search(r'Buffer size: (\d+)', previous)[1]
    results = []
    try:
        for repeat in range(1, args.repeats+1):
          for rate, quantum in profiles:
            name = f'{rate}-{quantum}' + (f'-run{repeat}' if args.repeats > 1 else '')
            print('Recording', name, f'({args.seconds} s) ...', flush=True)
            started = time.time()
            try:
                result = run_profile(args.output/name, rate, quantum, args.seconds)
                result['status'] = 'ok'
            except Exception as error:
                result = {'status': 'error: %s' % error}
            result.update(profile=name, quantum=quantum, seconds=round(time.time()-started))
            results.append(result)
            (args.output/'summary.json').write_text(json.dumps(results, indent=2)+'\n')
            if result['status'] == 'ok':
                print('  offset %+.3f ms (%+.1f samples), spread %.3f ms, %d/%d clicks, %d steps'
                      % (result['median_offset_ms'], result['median_offset_samples'], result['spread_ms'],
                         result['clicks'], result['expected_clicks'], len(result['steps'])), flush=True)
            else:
                print('  ' + result['status'], flush=True)
    finally:
        wait_until_idle()
        settings('rate', str(previous_rate))
        settings('buffer', previous_buffer)
        print('Restored', previous_rate, 'Hz, buffer', previous_buffer, flush=True)


if __name__ == '__main__':
    main()

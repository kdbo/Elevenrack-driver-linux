#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Correlate a jack-loopback.c mono float32 recording against its test bursts."""
import argparse
import array
import json
import math
from pathlib import Path
import re
import csv
import ctypes


def analyze(path):
    log = path.with_suffix('.log').read_text()
    match = re.search(r'settled rate=(\d+) quantum=(\d+) capture=(\d+)..(\d+) playback=(\d+)..(\d+)', log)
    if not match or not re.search(r'^xruns=0$', log, re.MULTILINE) or 'Xrun invalidates' in log:
        raise ValueError('Missing valid settled parameters or xrun-free log')
    rate, quantum, cmin, cmax, pmin, pmax = map(int, match.groups())
    phases = re.search(r'warmup_xruns=(\d+) post_recording_xruns=(\d+)', log)
    client_match = re.search(r'client capture=(\d+)\.\.(\d+) playback=(\d+)\.\.(\d+)', log)
    client_latency = {}
    if client_match:
        ccmin, ccmax, cpmin, cpmax = map(int, client_match.groups())
        client_latency = {'capture_range_frames': [ccmin, ccmax],
                          'playback_range_frames': [cpmin, cpmax]}
    samples = array.array('f')
    samples.frombytes(path.read_bytes())
    if len(samples) != rate * 8:
        raise ValueError('Expected the complete eight-second recording')
    width = rate // 100
    reference = [math.sin(2 * math.pi * 997 * j / rate) * math.sin(math.pi * j / width)**2 for j in range(width)]
    energy = sum(x*x for x in reference)
    native = Path(__file__).resolve().parents[1] / 'build/latency/liblatency-correlation.so'
    peak = None
    if native.exists():
        peak = ctypes.CDLL(str(native)).latency_peak
        peak.argtypes = [ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_double),
                         ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_double)]
        peak.restype = ctypes.c_int
        sample_buffer = (ctypes.c_float * len(samples)).from_buffer(samples)
        reference_buffer = (ctypes.c_double * width)(*reference)
    bursts = []
    for start in range(rate // 2, rate * 7, rate):
        best = (-1, None, None)
        # Large graph buffers can exceed 40 ms before hardware delay is added.
        # Keep the search below the one-second spacing between stimuli.
        search_frames = min(rate // 2, cmax + pmax + rate // 25)
        if peak:
            score = ctypes.c_double()
            lag = peak(ctypes.cast(ctypes.byref(sample_buffer, start*4), ctypes.POINTER(ctypes.c_float)),
                       reference_buffer, width, search_frames, ctypes.byref(score))
            best = (abs(score.value), lag, score.value)
        for lag in range(0 if peak else search_frames):
            segment = samples[start+lag:start+lag+width]
            norm = sum(x*x for x in segment)
            score = sum(x*y for x, y in zip(reference, segment)) / math.sqrt(energy * norm) if norm else 0
            if abs(score) > best[0]:
                best = (abs(score), lag, score)
        if best[0] < .9:
            raise ValueError('No reliable correlated test burst at '+str(start / rate))
        bursts.append({'stimulus_seconds': start/rate, 'lag_frames': best[1],
                       'lag_ms': best[1]*1000/rate, 'correlation': best[2],
                       'minus_reported_frames': best[1]-cmin-pmin})
    live_path = Path(str(path)+'.latency.csv')
    timestamps_path = Path(str(path)+'.timestamps.csv')
    if live_path.exists() and timestamps_path.exists():
        live = list(csv.DictReader(live_path.open()))
        callbacks = list(csv.DictReader(timestamps_path.open()))
        for burst in bursts:
            frame = round(burst['stimulus_seconds'] * rate)
            stamp = next(entry for entry in callbacks if int(entry['frame']) >= frame)
            realtime = int(stamp['realtime_ns'])
            before = [entry for entry in live if int(entry['realtime_ns']) <= realtime]
            if before:
                entry = before[-1]
                reported = int(entry['capture_min']) + int(entry['playback_min'])
                burst['reported_frames_at_stimulus'] = reported
                burst['minus_live_reported_frames'] = burst['lag_frames'] - reported
    transport = {}
    status_path = path.with_suffix('.status.json')
    stamp_path = Path(str(path)+'.timestamps.csv')
    if status_path.exists() and stamp_path.exists():
        stamps = list(csv.DictReader(stamp_path.open()))
        first = int(stamps[0]['realtime_ns'])
        last = int(stamps[-1]['realtime_ns'])
        snapshots = json.loads(status_path.read_text())
        for direction in ('p', 'c'):
            previous = None
            changes = 0
            for snapshot in snapshots:
                if snapshot['realtime_ns'] > last:
                    break
                trigger = re.search(r'trigger_time:\s*(\S+)', snapshot[direction+'_status'])
                if not trigger or trigger[1] == '0.000000000':
                    continue
                if previous is not None and trigger[1] != previous and snapshot['realtime_ns'] >= first:
                    changes += 1
                previous = trigger[1]
            transport[direction+'_trigger_changes_during_recording'] = changes
    return {'recording': str(path), 'rate_hz': rate, 'quantum': quantum,
            'alsa_transport': transport,
            'client_port_latency': client_latency,
            'capture_range_frames': [cmin, cmax], 'playback_range_frames': [pmin, pmax],
            'xruns': 0, 'bursts': bursts,
            'warmup_xruns': int(phases[1]) if phases else None,
            'post_recording_xruns': int(phases[2]) if phases else None,
            'method': 'Uncompensated JACK callback sample timeline; aggregate physical loopback, no input/output split'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recordings', nargs='+', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        results = [analyze(path) for path in args.recordings]
    except (ValueError, OSError) as error:
        raise SystemExit(str(error))
    args.output.write_text(json.dumps({'results': results}, indent=2)+'\n')
    for result in results:
        print(result['rate_hz'], result['quantum'], [b['lag_frames'] for b in result['bursts']])

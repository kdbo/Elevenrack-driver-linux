#!/usr/bin/env python3
"""Offline loopback continuity screening; preserves window-level evidence."""
import mmap
import struct
import ctypes
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

def analyze(raw):
    raw = Path(raw)
    log = raw.with_suffix('.log').read_text()
    match = re.search(r'settled rate=(\d+) quantum=(\d+)', log)
    if not match:
        raise ValueError('No settled graph parameters')
    rate, quantum = map(int, match.groups())
    signal = 'multitone' if 'multitone' in str(raw.parent) else 'sine' if 'sine' in str(raw.parent) else 'pink' if 'pink' in str(raw.parent) else 'white'
    capture_file=raw.open('rb')
    reference_file=Path(str(raw)+'.reference.raw').open('rb')
    samples=mmap.mmap(capture_file.fileno(),0,access=mmap.ACCESS_COPY)
    reference=mmap.mmap(reference_file.fileno(),0,access=mmap.ACCESS_READ)
    count=len(samples)//4
    if len(samples) != len(reference) or count < rate:
        raise ValueError('Incomplete or mismatched recording')
    lib = ctypes.CDLL(str(ROOT/'build/latency/liblatency-correlation.so'))
    peak = lib.latency_peak
    peak.argtypes = [ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_double), ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_double)]
    peak.restype = ctypes.c_int
    buf = (ctypes.c_float*count).from_buffer(samples)
    scan=lib.regression_scan
    scan.argtypes=[ctypes.POINTER(ctypes.c_float),ctypes.c_int]
    scan.restype=ctypes.c_int
    stream_flags=scan(ctypes.cast(ctypes.byref(buf,rate*4),ctypes.POINTER(ctypes.c_float)),count-rate-rate//5)
    rows, faults, previous = [], [], None
    width, step = (rate//10 if signal=='multitone' else 512), rate//10
    for start in range(rate, count-rate//5-width, step):
        low = 0 if previous is None or signal == 'sine' else max(0,previous-256)
        search = rate//5 if previous is None else (max(2,rate//997*2) if signal=='sine' else 513)
        ref = (ctypes.c_double*width)(*struct.unpack_from(f'<{width}f',reference,start*4))
        score = ctypes.c_double()
        lag = low+peak(ctypes.cast(ctypes.byref(buf,(start+low)*4),ctypes.POINTER(ctypes.c_float)),ref,width,search,ctypes.byref(score))
        block = struct.unpack_from(f'<{width}f',samples,(start+lag)*4)
        rms = math.sqrt(sum(v*v for v in block)/width)
        issues=[]
        if not math.isfinite(score.value) or abs(score.value)<.80: issues.append('low_correlation')
        if rms<1e-5: issues.append('silence')
        if any(not math.isfinite(v) or abs(v)>=.999 for v in block): issues.append('clipping_or_nonfinite')
        if previous is not None and signal!='sine' and abs(lag-previous)>max(8,rate//1000): issues.append('delay_jump')
        row={'seconds':start/rate,'lag_frames':lag,'correlation':score.value,'rms':rms,'issues':issues}
        rows.append(row)
        if issues: faults.append(row)
        if abs(score.value)>=.80: previous=lag
    xruns = int(re.search(r'^xruns=(\d+)',log,re.M)[1]) if re.search(r'^xruns=(\d+)',log,re.M) else None
    result={'rate_hz':rate,'quantum':quantum,'signal':signal,'duration_seconds':count/rate,'xruns':xruns,'stream_fault_flags':stream_flags,'passed':xruns==0 and stream_flags==0 and not faults and bool(rows) and 'Incomplete recording' not in log,'faults':faults,'windows':rows,
            'correlation_window_frames':width, 'limitations':'Full-stream scan for nonfinite/clipped samples, 64 consecutive near-zero or identical samples; Correlation windows every 100 ms: 512 samples for noise/sine, 100 ms for multitone. Other brief faults between windows can escape detection. Sine delay is ambiguous; no absolute latency/drift claim.'}
    raw.with_suffix('.regression.json').write_text(json.dumps(result,indent=2)+'\n')
    del buf
    samples.close(); reference.close(); capture_file.close(); reference_file.close()
    return result

if __name__=='__main__':
    import sys
    result=analyze(Path(sys.argv[1]))
    print(json.dumps({k:v for k,v in result.items() if k!='windows'},indent=2))
    sys.exit(0 if result['passed'] else 1)

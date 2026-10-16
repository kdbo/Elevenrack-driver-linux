#!/usr/bin/env python3
"""Separate stationary analog filtering from timing faults in white-noise loopbacks.

A fixed FIR is learned once and validated on independent windows. Raw correlation
results remain available; no per-window fitting or adaptive delay correction is
used to hide discontinuities. This is an offline diagnostic, not a latency fix.
"""
import array
import bisect
import ctypes
import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_tool(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT/'tools'/filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def analyze(raw):
    raw = Path(raw)
    # The existing tool infers signal from directory names. This entry point is
    # deliberately white-noise only; reject misleading directories.
    if any(word in str(raw.parent) for word in ('sine', 'pink', 'multitone')):
        raise ValueError('White-noise recordings require a white-noise directory')
    original = load_tool('regression', 'analyze-loopback-regression.py').analyze(raw)
    rate = original['rate_hz']
    x, y = array.array('f'), array.array('f')
    x.frombytes(Path(str(raw)+'.reference.raw').read_bytes())
    y.frombytes(raw.read_bytes())
    if len(x) != len(y) or len(x) < 3*rate:
        raise ValueError('Need at least three seconds of matched reference and capture')
    xb = (ctypes.c_float*len(x)).from_buffer(x)
    yb = (ctypes.c_float*len(y)).from_buffer(y)
    lib = ctypes.CDLL(str(ROOT/'build/latency/libloopback-filter.so'))
    floats, doubles = ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_double)
    lib.noise_fit.argtypes = [floats, floats, ctypes.c_int, ctypes.c_int,
                             ctypes.c_int, ctypes.c_int, doubles]
    lib.noise_fit.restype = ctypes.c_int
    lib.noise_score.argtypes = [floats, floats, ctypes.c_int, ctypes.c_int,
                               ctypes.c_int, ctypes.c_int, doubles, doubles]
    lib.noise_score.restype = None
    half = 32
    h = (ctypes.c_double*(2*half+1))()
    initial_lag = original['windows'][0]['lag_frames']
    train_start, train_count = round(1.1*rate), round(.2*rate)
    if train_start+train_count+initial_lag >= len(y):
        raise ValueError('Calibration interval exceeds recording')
    if lib.noise_fit(xb, yb, train_start, train_count, initial_lag, half, h):
        raise ValueError('Analog response estimation failed')
    rows = []
    for w in original['windows']:
        start, lag = round(w['seconds']*rate), w['lag_frames']
        # Fractional delays can make two adjacent raw integer peaks exchange
        # places. Choose among neighbours using the same fixed response; this
        # does not relearn the filter or absorb a larger timing step.
        best = None
        for candidate in range(max(0, lag-1), lag+2):
            if start+candidate+512 > len(y):
                continue
            score = (ctypes.c_double*3)()
            lib.noise_score(xb, yb, start, 512, candidate, half, h, score)
            if best is None or score[0] > best[0]:
                best = (score[0], score[1], candidate)
        rows.append(dict(w, raw_lag_frames=lag, lag_frames=best[2],
                         filter_correlation=best[0], relative_residual_rms=best[1]))
    # Validate the fixed model beyond its training data before accepting any
    # explanation of a low raw correlation as stationary analog filtering.
    validation = [w for w in rows if 1.5 <= w['seconds'] <= 2.0]
    calibrated = len(validation) >= 4 and all(
        math.isfinite(w['filter_correlation']) and w['filter_correlation'] >= .98
        for w in validation)
    faults, delay_steps, previous = [], [], None
    for w in rows:
        good_shape = calibrated and math.isfinite(w['filter_correlation']) and w['filter_correlation'] >= .98
        issues = [i for i in w['issues'] if i not in ('low_correlation', 'delay_jump')]
        if not good_shape:
            issues.append('waveform_mismatch' if calibrated else 'uncalibrated_analog_response')
        reliable_lag = good_shape or abs(w['correlation']) >= .80
        if reliable_lag:
            if previous is not None and abs(w['lag_frames']-previous) > 8:
                issues.append('delay_step')
                delay_steps.append({'seconds': w['seconds'], 'frames': w['lag_frames']-previous})
            previous = w['lag_frames']
        w['issues'] = issues
        if issues:
            faults.append(w)
    # Check consecutive blocks as well as the sparse alignment windows. A
    # short dropout between those windows must not disappear after filtering.
    starts = [round(w['seconds']*rate) for w in rows]
    dense_faults, dense_max_residual = [], 0.0
    if calibrated:
        for start in range(rate, len(y)-rate//5-512, 512):
            w = rows[max(0, bisect.bisect_right(starts, start)-1)]
            lag = w['lag_frames']
            best = None
            for candidate in range(max(0, lag-1), lag+2):
                if start+candidate+512 > len(y):
                    continue
                score = (ctypes.c_double*3)()
                lib.noise_score(xb, yb, start, 512, candidate, half, h, score)
                if best is None or score[1] < best[1]:
                    best = (score[0], score[1])
            dense_max_residual = max(dense_max_residual, best[1])
            if not math.isfinite(best[0]) or best[0] < .98 or best[1] > .10:
                dense_faults.append({'seconds': start/rate, 'correlation': best[0],
                                     'relative_residual_rms': best[1]})
    snapshots = raw.with_suffix('.status.json')
    restarted = None
    if snapshots.exists() and Path(str(raw)+'.timestamps.csv').exists():
        matrix = load_tool('matrix', 'test-full-latency-matrix.py')
        restarted = matrix.pcm_restarted(json.loads(snapshots.read_text()),
                                        matrix.recording_bounds(raw, rate))
    result = {'rate_hz': rate, 'quantum': original['quantum'],
              'signal': 'white', 'duration_seconds': original['duration_seconds'],
              'analog_model_validated': calibrated,
              'model_training_seconds': [train_start/rate, (train_start+train_count)/rate],
              'model_coefficients': list(h), 'delay_steps': delay_steps,
              'pcm_restart_during_recording': restarted,
              'raw_screening_passed': original['passed'],
              'stream_fault_flags': original['stream_fault_flags'],
              'xruns': original['xruns'], 'faults': faults, 'windows': rows,
              'dense_faults': dense_faults, 'dense_fault_count': len(dense_faults),
              'dense_max_relative_residual_rms': dense_max_residual,
              'passed': calibrated and not faults and not dense_faults and original['xruns'] == 0
                        and original['stream_fault_flags'] == 0 and restarted is not True
                        and 'Incomplete recording' not in raw.with_suffix('.log').read_text(),
              'limitations': 'One fixed 65-tap analog model; alignment windows every 100 ms and consecutive '
                             '512-sample residual blocks (correlation >=.98, relative residual RMS <=.10). '
                             'Eight-frame delay-step threshold is a diagnostic bound, not proof '
                             'of exact sample continuity. PCM evidence is unavailable when null. '
                             'No recalibration across a restart or delay step.'}
    raw.with_suffix('.white-path.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


if __name__ == '__main__':
    import sys
    r = analyze(Path(sys.argv[1]))
    print(json.dumps({k: v for k, v in r.items() if k not in ('windows', 'faults', 'dense_faults', 'model_coefficients')}, indent=2))
    sys.exit(0 if r['passed'] else 1)

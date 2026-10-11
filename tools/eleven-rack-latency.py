#!/usr/bin/env python3
"""Calculate/apply/reset a measured loopback calibration in PipeWire.

This is a user/path calibration, not a universal hardware delay constant.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import statistics
import math

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / 'build/latency/pipewire-calibration-state.json'


def run(*args):
    return subprocess.check_output(args, text=True, timeout=8)


def current():
    nodes = json.loads(run('pw-dump'))
    matches = [o for o in nodes if o.get('type') == 'PipeWire:Interface:Node'
               and o.get('info', {}).get('props', {}).get('node.name', '').startswith(
                   'alsa_input.usb-Digidesign_Eleven_Rack')]
    if len(matches) != 1:
        raise RuntimeError('Expected exactly one Eleven Rack capture node')
    node = matches[0]
    text = run('pw-cli', 'enum-params', str(node['id']), 'ProcessLatency')
    values = {}
    for name, kind in [('quantum', 'Float'), ('rate', 'Int'), ('ns', 'Long')]:
        match = re.search(r':'+name+r'\s*\([^\n]*\n\s*'+kind+r'\s+(-?[\d.]+)', text)
        if not match:
            raise RuntimeError('Cannot read current ProcessLatency '+name)
        values[name] = float(match[1]) if name == 'quantum' else int(match[1])
    return node, values


def set_latency(node, values):
    pod = '{ quantum = %s rate = %s ns = %s }' % (
        values['quantum'], values['rate'], values['ns'])
    run('pw-cli', 'set-param', str(node['id']), 'ProcessLatency', pod)
    _, actual = current()
    if actual != values:
        raise RuntimeError('PipeWire did not confirm the requested calibration')


def calculate(path, rate, quantum, verification=False):
    """Estimate the aggregate missing delay; never infer an ADC/DAC split."""
    rows = [r for r in json.loads(path.read_text())['results']
            if r['rate_hz'] == rate and r['quantum'] == quantum]
    if not rows:
        raise ValueError('No measurement for the requested rate/quantum')
    if len(rows) < 2 or len({r['recording'] for r in rows}) < 2:
        raise ValueError('At least two separate recordings are required to check repeatability')
    residuals = []
    delays = []
    for row in rows:
        if any(row.get('alsa_transport', {}).values()):
            raise ValueError('ALSA restarted during recording despite JACK xrun count; repeat the measurement')
        if row['xruns'] != 0 or len(row['bursts']) < 7:
            raise ValueError('Calibration requires complete xrun-free measurements')
        capture, playback = row['capture_range_frames'], row['playback_range_frames']
        if capture[0] != capture[1] or playback[0] != playback[1]:
            raise ValueError('Reported latency range is ambiguous')
        for burst in row['bursts']:
            if not math.isfinite(burst['correlation']) or abs(burst['correlation']) < .9:
                raise ValueError('Unreliable correlated test signal')
            lag = burst['lag_frames']
            if not isinstance(lag, int) or lag < 0:
                raise ValueError('Invalid measured delay')
            delays.append(lag)
            residuals.append(lag-capture[0]-playback[0])
    if max(residuals)-min(residuals) > 4:
        raise ValueError('Residual varies by more than four frames; repeat the measurement')
    correction = round(statistics.median(residuals))
    if verification and max(abs(x) for x in residuals) > 4:
        raise ValueError('Verification failed: measured and reported delay differ by more than four frames')
    if correction < 0 and not verification:
        raise ValueError('Reported latency exceeds measured delay; investigate before applying')
    return {'rate_hz': rate, 'quantum': quantum,
            'measured_round_trip_frames': statistics.median(delays),
            'correction_frames': correction, 'correction_ms': correction*1000/rate,
            'residual_range_frames': [min(residuals), max(residuals)],
            'measurement_file': str(path.resolve()),
            'scope': 'Measured path/configuration only; aggregate assigned to capture for recording alignment'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['calculate', 'verify', 'status', 'apply', 'reset'])
    parser.add_argument('--measurement', type=Path, help='JSON from analyze-jack-loopback.py')
    parser.add_argument('--rate', type=int, help='Measured graph sample rate')
    parser.add_argument('--quantum', type=int, help='Measured graph buffer size')
    args = parser.parse_args()
    calibration = None
    if args.command in ('calculate', 'verify', 'apply'):
        if not args.measurement or not args.rate or not args.quantum:
            parser.error('calculate/verify/apply require --measurement, --rate and --quantum')
        calibration = calculate(args.measurement, args.rate, args.quantum,
                                verification=args.command == 'verify')
        if args.command in ('calculate', 'verify'):
            if args.command == 'verify':
                calibration['verification'] = 'passed'
            print(json.dumps(calibration, indent=2))
            return
    node, old = current()
    if args.command == 'apply':
        metadata = run('pw-metadata', '-n', 'settings')
        settings = dict(re.findall(r"key:'([^']+)' value:'([^']+)'", metadata))
        rate = int(settings.get('clock.force-rate', '0')) or int(settings.get('clock.rate', '0'))
        quantum = int(settings.get('clock.force-quantum', '0')) or int(settings.get('clock.quantum', '0'))
        if (rate, quantum) != (args.rate, args.quantum):
            raise RuntimeError('Current rate/quantum do not match the measurement')
        if STATE.exists():
            raise RuntimeError('A calibration snapshot already exists; reset it before applying again')
        if any(old.values()):
            raise RuntimeError('An internal latency is already configured; refusing to double-count it')
        STATE.parent.mkdir(parents=True, exist_ok=True)
        applied = dict(old, rate=calibration['correction_frames'])
        STATE.write_text(json.dumps({'node_name': node['info']['props']['node.name'],
                                    'previous': old, 'applied': applied,
                                    'measurement': calibration}, indent=2)+'\n')
        set_latency(node, applied)
    elif args.command == 'reset':
        if not STATE.exists():
            raise RuntimeError('No saved calibration to restore')
        saved = json.loads(STATE.read_text())
        if node['info']['props']['node.name'] != saved['node_name']:
            raise RuntimeError('The capture node does not match the saved calibration')
        if old not in (saved['applied'], saved['previous']):
            raise RuntimeError('Latency changed externally; refusing to overwrite it')
        set_latency(node, saved['previous'])
        STATE.unlink()
    _, values = current()
    print(json.dumps(values, indent=2))
    print('Calibration changes reported latency, not physical delay. Reset REAPER manual offsets to zero.')
    print('Session-only: reapply after node recreation; reset before changing the calibrated rate/quantum.')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error))

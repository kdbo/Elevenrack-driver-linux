#!/usr/bin/env python3
"""Apply/reset the local 48 kHz, quantum-64 loopback calibration in PipeWire.

This is a user/path calibration, not a universal hardware delay constant.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

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
        match = re.search(r':'+name+r'\s*\([^\n]*\n\s*'+kind+r'\s+([\d.]+)', text)
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['status', 'apply', 'reset'])
    args = parser.parse_args()
    node, old = current()
    if args.command == 'apply':
        metadata = run('pw-metadata', '-n', 'settings')
        settings = dict(re.findall(r"key:'([^']+)' value:'([^']+)'", metadata))
        rate = int(settings.get('clock.force-rate', '0')) or int(settings.get('clock.rate', '0'))
        quantum = int(settings.get('clock.force-quantum', '0')) or int(settings.get('clock.quantum', '0'))
        if (rate, quantum) != (48000, 64):
            raise RuntimeError('This calibration is validated only at 48000 Hz and quantum 64')
        if STATE.exists():
            raise RuntimeError('A calibration snapshot already exists; reset it before applying again')
        if any(old.values()):
            raise RuntimeError('An internal latency is already configured; refusing to double-count it')
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({'node_name': node['info']['props']['node.name'],
                                    'previous': old, 'applied': dict(old, rate=210)}, indent=2)+'\n')
        set_latency(node, dict(old, rate=210))
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
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error))

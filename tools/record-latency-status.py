#!/usr/bin/env python3
"""Repeat JACK loopbacks with passive ALSA snapshots; restore forced quantum."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', default='/tmp/eleven-jack-loopback')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--quanta', type=int, nargs='+', default=[64, 128, 256])
    parser.add_argument('--interval', type=float, default=.1)
    args = parser.parse_args()
    if args.repeats < 1 or args.interval <= 0 or any(q < 32 for q in args.quanta):
        parser.error('Use positive repeats/interval and quanta of at least 32')
    args.output.mkdir(parents=True, exist_ok=True)
    metadata = subprocess.check_output(['pw-metadata', '-n', 'settings'], text=True)
    settings = dict(re.findall(r"key:'([^']+)' value:'([^']+)'", metadata))
    client_env = os.environ.copy()
    forced_rate = int(settings.get('clock.force-rate', '0'))
    if forced_rate:
        client_env['ELEVEN_TEST_RATE'] = str(forced_rate)
    previous = settings.get('clock.force-quantum', '0')
    results = []
    try:
        for quantum in args.quanta:
            if forced_rate:
                client_env['PIPEWIRE_QUANTUM'] = f'{quantum}/{forced_rate}'
                client_env['PIPEWIRE_LATENCY'] = f'{quantum}/{forced_rate}'
                client_env['PIPEWIRE_RATE'] = f'1/{forced_rate}'
            subprocess.run(['pw-metadata', '-n', 'settings', '0',
                            'clock.force-quantum', str(quantum)], check=True,
                           stdout=subprocess.DEVNULL)
            for repeat in range(args.repeats):
                prefix = args.output / f'quantum-{quantum}-run-{repeat+1}'
                snapshots = []
                with prefix.with_suffix('.log').open('w') as log:
                    process = subprocess.Popen([
                        'pw-jack', args.binary, 'Eleven Rack Outputs:Main Out L',
                        'Eleven Rack Inputs:Line In L', str(prefix.with_suffix('.raw'))],
                        stdout=log, stderr=subprocess.STDOUT, env=client_env)
                    try:
                        deadline = time.monotonic() + int(client_env.get("ELEVEN_TEST_SECONDS", "8")) + 20
                        while process.poll() is None:
                            if time.monotonic() > deadline:
                                raise RuntimeError('Loopback timed out')
                            snapshot = {'monotonic_ns': time.monotonic_ns(),
                                        'realtime_ns': time.time_ns()}
                            for direction in ('p', 'c'):
                                base = Path(f'/proc/asound/Rack/pcm0{direction}/sub0')
                                for item in ('status', 'hw_params'):
                                    snapshot[f'{direction}_{item}'] = (base / item).read_text()
                            snapshot['end_monotonic_ns'] = time.monotonic_ns()
                            snapshots.append(snapshot)
                            time.sleep(args.interval)
                    finally:
                        if process.poll() is None:
                            process.terminate()
                            try:
                                process.wait(timeout=3)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait()
                        prefix.with_suffix('.status.json').write_text(
                            json.dumps(snapshots, indent=2) + '\n')
                    results.append({'quantum': quantum, 'repeat': repeat+1,
                                    'returncode': process.returncode,
                                    'prefix': str(prefix)})
                    print(results[-1], flush=True)
                    # Retain failed runs as diagnostics, never as calibration evidence.
    finally:
        subprocess.run(['pw-metadata', '-n', 'settings', '0',
                        'clock.force-quantum', previous], check=True)
        (args.output / 'runs.json').write_text(json.dumps(results, indent=2)+'\n')


if __name__ == '__main__':
    main()

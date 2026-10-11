#!/usr/bin/env python3
"""Run bounded IN-only monitoring probes; do not replace the audio driver."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
MODULE = 'eleven_monitor_read_probe'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-modes', action='store_true',
                        help='Verify known DAW-only and hardware settings, then restore hardware')
    args = parser.parse_args()
    if Path('/sys/module', MODULE).exists():
        raise RuntimeError('Probe already loaded; refusing to interfere')
    binary = ROOT / 'build/monitor-read-probe' / (MODULE + '.ko')
    if not binary.is_file():
        raise RuntimeError('Build the read-only probe first')
    # Fixed module and fixed requests only; no interface unbinds or OUT requests.
    commands = '''set -eu
trap '/usr/sbin/rmmod eleven_monitor_read_probe 2>/dev/null || true' EXIT
/usr/sbin/insmod /home/koen/git/Eleven-Rack-Linux/build/monitor-read-probe/eleven_monitor_read_probe.ko request=3
cat /sys/module/eleven_monitor_read_probe/parameters/results
/usr/sbin/rmmod eleven_monitor_read_probe
/usr/sbin/insmod /home/koen/git/Eleven-Rack-Linux/build/monitor-read-probe/eleven_monitor_read_probe.ko request=1
cat /sys/module/eleven_monitor_read_probe/parameters/results
'''
    if args.verify_modes:
        commands = '''set -eu
trap '/usr/sbin/rmmod eleven_monitor_read_probe 2>/dev/null || true; /usr/bin/python3 /usr/lib/eleven-rack/tools/eleven-rack-settings.py monitor hardware >&2' EXIT
/usr/bin/python3 /usr/lib/eleven-rack/tools/eleven-rack-settings.py monitor daw-only >&2
echo mode=daw-only
/usr/sbin/insmod /home/koen/git/Eleven-Rack-Linux/build/monitor-read-probe/eleven_monitor_read_probe.ko request=3
cat /sys/module/eleven_monitor_read_probe/parameters/results
/usr/sbin/rmmod eleven_monitor_read_probe
/usr/bin/python3 /usr/lib/eleven-rack/tools/eleven-rack-settings.py monitor hardware >&2
echo mode=hardware
/usr/sbin/insmod /home/koen/git/Eleven-Rack-Linux/build/monitor-read-probe/eleven_monitor_read_probe.ko request=3
cat /sys/module/eleven_monitor_read_probe/parameters/results
'''
    result = subprocess.run(['pkexec', '/bin/sh', '-c', commands],
                            capture_output=True, text=True, timeout=180)
    rows = []
    mode = None
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        if line.startswith('mode='):
            mode = line[5:]
            continue
        request, value, index, wanted, received, data = line.split(',')
        rows.append({'mode_set_for_validation': mode,
                     'request': int(request, 16), 'request_type': 0xa1,
                     'value': int(value, 16), 'index': int(index, 16),
                     'expected_length': int(wanted), 'return_value': int(received),
                     'data_hex': data})
    report = {'date': '2026-10-10', 'read_probe_sends_only_in_requests': True,
              'monitor_mode_changes_for_validation': args.verify_modes,
              'audio_driver_replaced': False, 'returncode': result.returncode,
              'stderr': result.stderr, 'reads': rows,
              'probe_unloaded': not Path('/sys/module', MODULE).exists()}
    path = ROOT / 'build/monitor-read-probe' / ('mode-verification.json' if args.verify_modes else 'results.json')
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2), flush=True)
    if result.returncode:
        raise RuntimeError('Read probe failed; see ' + str(path))


if __name__ == '__main__':
    main()

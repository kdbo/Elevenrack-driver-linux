#!/usr/bin/env python3
"""Activate the installed monitor control and test writes, restoring hardware mode."""
import json
import os
from pathlib import Path
import re
import signal
import sys
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent


def call(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT)


def main():
    for name in ('reaper', 'jackd'):
        if subprocess.run(['pgrep', '-x', name], stdout=subprocess.DEVNULL).returncode == 0:
            raise RuntimeError('Save and close ' + name + ' before activating the driver')
    version = call('dpkg-query', '-W', '-f=${Version}', 'eleven-rack-driver')
    if version != (ROOT / 'VERSION').read_text().strip():
        raise RuntimeError('Install the monitoring package before activation')
    metadata = dict(re.findall(r"key:'([^']+)' value:'([^']+)'", call('pw-metadata', '-n', 'settings')))
    units = ['wireplumber.service', 'pipewire-pulse.service', 'pipewire-pulse.socket',
             'pipewire.service', 'pipewire.socket']
    active = [unit for unit in units if subprocess.run(
        ['systemctl', '--user', 'is-active', '--quiet', unit]).returncode == 0]
    output = ROOT / 'build/monitor-driver/activation.json'
    report = {'package': version, 'previous_settings': metadata, 'previous_active_units': active}
    try:
        # The settings panel's amixer event watcher holds the old module open.
        # Close only installed settings panels and their own child processes.
        panels = []
        children = {}
        for proc in Path('/proc').glob('[0-9]*'):
            try:
                args = (proc / 'cmdline').read_bytes().split(b'\0')
                ppid = int(re.search(r'^PPid:\s*(\d+)', (proc / 'status').read_text(), re.MULTILINE)[1])
                pid = int(proc.name)
                children.setdefault(ppid, []).append(pid)
                if b'/usr/lib/eleven-rack/tools/eleven-rack-panel.py' in args or b'/tmp/eleven-open-refreshed-panel.py' in args:
                    panels.append(pid)
            except (OSError, TypeError):
                continue
        for pid in panels:
            for child in children.get(pid, []):
                try:
                    os.kill(child, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        if panels:
            time.sleep(1)
        report['settings_panels_closed_for_reload'] = len(panels)
        call('systemctl', '--user', 'daemon-reload')
        call('systemctl', '--user', 'stop', *units)
        for direction in ('p', 'c'):
            status = Path(f'/proc/asound/Rack/pcm0{direction}/sub0/status').read_text()
            if status.strip() != 'closed':
                raise RuntimeError('Rack still in use; refusing driver unload: ' + status)
        subprocess.run(['pkexec', '/bin/sh', '-c',
                        '/usr/sbin/modprobe -r snd_usb_audio && /usr/sbin/modprobe snd_usb_audio'], check=True)
        backend = '/usr/lib/eleven-rack/tools/eleven-rack-settings.py'
        report['initial'] = call('/usr/bin/python3', backend, 'monitor')
        report['hardware_sample_rate'] = call('/usr/bin/python3', backend, 'rate')
        if '--rate-only' not in sys.argv:
            try:
                report['daw_only'] = call('/usr/bin/python3', backend, 'monitor', 'daw-only')
            finally:
                report['hardware'] = call('/usr/bin/python3', backend, 'monitor', 'hardware')
        report['usb_commands_accepted'] = True
        report['audible_effect_verified'] = False
    finally:
        if active:
            call('systemctl', '--user', 'start', *active)
            time.sleep(3)
            for key in ('clock.force-rate', 'clock.force-quantum'):
                call('pw-metadata', '-n', 'settings', '0', key, metadata.get(key, '0'))
        output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()

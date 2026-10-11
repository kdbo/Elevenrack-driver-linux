#!/usr/bin/env python3
"""Restart the installed backend, preserving forced rate and graph quantum."""
import json
from pathlib import Path
import re
import subprocess
import time

def call(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT)

if subprocess.run(['pgrep', '-x', 'reaper'], stdout=subprocess.DEVNULL).returncode == 0:
    raise SystemExit('REAPER is open; save and close before restarting audio.')
settings = dict(re.findall(r"key:'([^']+)' value:'([^']+)'", call('pw-metadata', '-n', 'settings')))
subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
subprocess.run(['systemctl', '--user', 'restart', 'pipewire.service', 'wireplumber.service'], check=True)
try:
    time.sleep(2)
finally:
    for key in ('clock.allowed-rates', 'clock.rate', 'clock.force-rate', 'clock.force-quantum'):
        if key in settings:
            call('pw-metadata', '-n', 'settings', '0', key, settings[key])
pid = call('systemctl', '--user', 'show', 'pipewire.service', '-p', 'MainPID', '--value').strip()
if '/usr/lib/eleven-rack/spa/alsa/libspa-alsa.so' not in Path('/proc', pid, 'maps').read_text():
    raise SystemExit('Installed backend is not loaded')
nodes = json.loads(call('pw-dump'))
config = Path('/etc/wireplumber/wireplumber.conf.d/52-eleven-rack-latency.conf').read_text()
expected = {f'api.alsa.eleven-correction-{r}-{q}': int(v) for r,q,v in
            re.findall(r'eleven-correction-(\d+)-(\d+)\s*=\s*(-?\d+)', config)}
properties = []
for node in nodes:
    props = node.get('info', {}).get('props', {})
    if props.get('api.alsa.card.id') == 'Rack' and props.get('media.class') in ('Audio/Source', 'Audio/Sink'):
        corrections = {k: v for k, v in props.items() if k.startswith('api.alsa.eleven-correction-')}
        if corrections != expected:
            raise SystemExit('Missing correction properties on ' + props.get('node.name', '?'))
        properties.append({'node': props['node.name'], 'corrections': corrections})
if len(properties) != 2:
    raise SystemExit('Expected Rack capture and playback nodes')
Path('docs/latency-profile-activation.json').write_text(json.dumps({
    'package': call('dpkg-query', '-W', '-f=${Version}', 'eleven-rack-latency-backend'),
    'loaded_backend_verified': True, 'node_properties': properties,
    'restored_settings': settings,
    'new_physical_validation': False,
}, indent=2) + '\n')
print('Installed backend loaded, all corrections verified, original rate/quantum restored')

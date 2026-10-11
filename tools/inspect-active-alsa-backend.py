#!/usr/bin/env python3
import subprocess
from pathlib import Path
for unit in ('pipewire.service','wireplumber.service'):
    pid=subprocess.check_output(['systemctl','--user','show',unit,'-p','MainPID','--value'],text=True).strip()
    print(unit,pid)
    print('\n'.join(line for line in Path('/proc',pid,'maps').read_text().splitlines() if 'spa' in line and 'alsa' in line))
    environ=Path('/proc',pid,'environ').read_bytes().split(b'\0')
    print([s.decode() for s in environ if s.startswith(b'SPA_PLUGIN_DIR=')])

for app in ("reaper", "jackd"):
    r = subprocess.run(["pgrep", "-x", app], text=True, capture_output=True)
    print(app, r.stdout.strip() or "closed")

import json
nodes = json.loads(subprocess.check_output(["pw-dump"], text=True))
for node in nodes:
    props = node.get("info", {}).get("props", {})
    if props.get("node.name", "").startswith(("alsa_output.usb-Digidesign_Eleven_Rack", "alsa_input.usb-Digidesign_Eleven_Rack")):
        print({key: props.get(key) for key in ("node.name", "api.alsa.eleven-backend", "api.alsa.eleven-phase-enabled", "api.alsa.eleven-latency", "api.alsa.eleven-analog-delay")})

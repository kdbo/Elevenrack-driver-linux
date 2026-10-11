#!/usr/bin/env python3
"""Install the authorized nightly regression entry, preserving existing cron jobs."""
from pathlib import Path
import shlex
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
if Path('/etc/timezone').read_text().strip()!='Europe/Brussels':
    raise RuntimeError('Cron host timezone must be Europe/Brussels')
existing=subprocess.run(['crontab','-l'],capture_output=True,text=True)
if existing.returncode and 'no crontab for' not in existing.stderr:
    raise RuntimeError(existing.stderr)
marker='# eleven-rack-nightly-regression'
lines=[line for line in existing.stdout.splitlines() if marker not in line]
logs=ROOT/'build/latency/nightly-regression';logs.mkdir(parents=True,exist_ok=True)
entry=f'0 23 * * * {shlex.quote(sys.executable)} {shlex.quote(str(ROOT/"tools/run-nightly-regression.py"))} >> {shlex.quote(str(logs/"cron.log"))} 2>&1 {marker}'
lines.append(entry)
subprocess.run(['crontab','-'],input='\n'.join(lines)+'\n',text=True,check=True)
installed=subprocess.check_output(['crontab','-l'],text=True)
assert entry in installed
print('Installed and verified:',entry)
subprocess.run(['systemctl','is-active','cron.service'],check=True)

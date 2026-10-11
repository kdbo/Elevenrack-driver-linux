#!/usr/bin/env python3
"""Open a separate rate/quantum latency project using the installed controls."""
import argparse
import os
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('project', type=Path)
parser.add_argument('--rate', required=True, type=int, choices=[48000,88200,96000])
parser.add_argument('--quantum', required=True, type=int, choices=[128,256,512,1024,2048])
args = parser.parse_args()
project = args.project.resolve()
if not project.is_file():
    raise RuntimeError('Project does not exist')
if subprocess.run(['pgrep','-x','reaper'],stdout=subprocess.DEVNULL).returncode == 0:
    raise RuntimeError('Save and close REAPER first')
backend = '/usr/lib/eleven-rack/tools/eleven-rack-settings.py'
subprocess.run(['python3',backend,'rate',str(args.rate)],check=True)
subprocess.run(['python3',backend,'buffer',str(args.quantum)],check=True)
launcher=Path.home()/'.local/share/eleven-rack-local/reaper/start-reaper.sh'
executable=Path.home()/'Downloads/reaper782_linux_x86_64/reaper_linux_x86_64/REAPER/reaper'
environment = os.environ.copy()
environment['PIPEWIRE_QUANTUM'] = f'{args.quantum}/{args.rate}'
environment['PIPEWIRE_LATENCY'] = f'{args.quantum}/{args.rate}'
environment['PIPEWIRE_RATE'] = f'1/{args.rate}'
with project.with_suffix('.launch.log').open('a') as log:
    process=subprocess.Popen(['/bin/bash',str(launcher),str(executable),str(project)],stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env=environment)
print('REAPER launched:',process.pid,'Project:',project)

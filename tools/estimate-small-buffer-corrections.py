#!/usr/bin/env python3
"""Use nearest measured high-rate profile for unmeasured smaller buffers."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
path = ROOT/'docs/latency-profile-corrections.json'
report = json.loads(path.read_text())
report['profiles'] = [p for p in report['profiles'] if not (p['rate_hz'] >= 88200 and p['quantum'] < 512)]
estimates = []
for rate in (88200,96000):
    reference = next(p for p in report['profiles'] if p['rate_hz']==rate and p['quantum']==512)
    for quantum in (64,128,256):
        estimates.append({'rate_hz':rate,'quantum':quantum,
                          'status':'estimated, not physically validated',
                          'addition_frames':reference['addition_frames'],
                          'method':'Constant extrapolation from nearest measured buffer (512); no established linear buffer trend',
                          'reference_quantum':512,'valid_starts':0})
report['profiles'].extend(estimates)
report['profiles'].sort(key=lambda p:(p['rate_hz'],p['quantum']))
path.write_text(json.dumps(report,indent=2)+'\n')
config = ROOT/'config/52-eleven-rack-latency.conf'
t = config.read_text()
for p in estimates:
    key = f"api.alsa.eleven-correction-{p['rate_hz']}-{p['quantum']}"
    t = re.sub(r'^\s*'+re.escape(key)+r'\s*=.*\n','',t,flags=re.M)
    t = t.replace('    api.alsa.eleven-analog-delay = 140\n',
                  '    api.alsa.eleven-analog-delay = 140\n'+f"    {key} = {p['addition_frames']}\n")
config.write_text(t)
out = ROOT/'docs/latency-small-buffer-estimates.json'
out.write_text(json.dumps({'method':'Nearest measured buffer, constant extrapolation',
                          'reason':'Three measured high-rate buffers do not establish a reliable linear trend; extrapolating a fitted slope would add unsupported buffer dependence',
                          'limitation':'These offsets do not fix xruns or distorted audio and were not measured at these buffers',
                          'profiles':estimates},indent=2)+'\n')
for p in estimates: print(p['rate_hz'],p['quantum'],p['addition_frames'])

#!/usr/bin/env python3
"""Fit exact profile offsets to fresh-start measurements, accounting for old offsets."""
import json
from pathlib import Path
import re
import statistics

ROOT = Path(__file__).resolve().parents[1]
matrix = json.loads((ROOT/'build/latency/full-profile-matrix/matrix.json').read_text())
if len(matrix['results']) != 36 or not matrix['restored']:
    raise SystemExit('Matrix incomplete or original settings not restored')
for directory in ('full-profile-matrix-recovery','full-profile-matrix-recovery-explicit'):
    retry = ROOT/'build/latency'/directory/'matrix.json'
    if retry.exists():
        extra = json.loads(retry.read_text())
        if not extra['restored']: raise SystemExit('Recovery still running')
        matrix['results'].extend(extra['results'])
profiles = []
for rate in (44100,48000,88200,96000):
    quanta = (64,128,256,512,1024,2048) if rate < 88200 else (512,1024,2048)
    for quantum in quanta:
        rows = [r for r in matrix['results'] if r['rate_hz']==rate and r['quantum']==quantum]
        good = [r for r in rows if r['valid']]
        profile = {'rate_hz':rate,'quantum':quantum,'valid_starts':len(good),
                   'errors':[r.get('error') for r in rows if not r['valid']]}
        if good:
            samples = [[b['minus_live_reported_frames']+r['existing_correction']
                        for b in r['bursts'] if b['stimulus_seconds']>=2.5] for r in good]
            means = [statistics.mean(s) for s in samples]
            correction = round(statistics.mean(means))
            residuals = [v-correction for s in samples for v in s]
            profile.update(status='measured approximation' if len(good)>=2 else 'provisional, one valid start',
                           addition_frames=correction, start_means_frames=means,
                           residual_range_frames=[min(residuals),max(residuals)],
                           residual_range_ms=[min(residuals)*1000/rate,max(residuals)*1000/rate],
                           recordings=[r['recording'] for r in good])
        else:
            profile['status']='unusable in both probes; no fitted correction'
        profiles.append(profile)
report = {'method':'Signed addition to runtime report; equal weight per fresh start; settled stimuli >=2.5 seconds; existing correction removed before fitting',
          'baseline':'rates3profiles2: dynamic ALSA queue+USB delay and 140/48000-second residual term',
          'physical_measurement':'Main Out L to Line In L, JACK sample timeline, live reported latency at each pulse',
          'limitation':'Two starts per profile, observed spread is not a guaranteed future bound; aggregate correction is attributed to capture',
          'profiles':profiles}
(ROOT/'docs/latency-profile-corrections.json').write_text(json.dumps(report,indent=2)+'\n')
p=ROOT/'config/52-eleven-rack-latency.conf';t=p.read_text()
t=re.sub(r'^\s*api\.alsa\.eleven-correction-.*\n','',t,flags=re.M)
lines=[]
for profile in profiles:
    if 'addition_frames' in profile:
        lines.append(f"    api.alsa.eleven-correction-{profile['rate_hz']}-{profile['quantum']} = {profile['addition_frames']}\n")
    print(profile['rate_hz'],profile['quantum'],profile.get('addition_frames'),profile.get('residual_range_frames'),profile['status'])
t=t.replace('    api.alsa.eleven-analog-delay = 140\n','    api.alsa.eleven-analog-delay = 140\n'+''.join(lines))
p.write_text(t)

#!/usr/bin/env python3
"""Compare bounded playback headroom candidates; retain defaults, write a recommendation."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import statistics
import signal
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]

def assess(folder):
    matrices=list(folder.glob('*/matrix.json'))
    rows=[row for path in matrices for row in json.loads(path.read_text())['results']]
    restored=bool(matrices) and all(json.loads(p.read_text()).get('restored') for p in matrices)
    timings=[]
    for row in rows:
        if row.get('signal') in ('white','pink'):
            timings.extend(w['lag_frames']*1000/row['rate_hz'] for w in row.get('windows',[]) if not w['issues'])
    return {'passed':len(rows)==len(matrices) and bool(rows) and restored and all(r.get('valid',False) for r in rows),
            'restored':restored,'runs':len(rows),'roundtrip_ms':statistics.median(timings) if timings else None}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--execute',action='store_true',help='Run physical loopbacks; default only shows plan')
    args=parser.parse_args()
    candidates=['default',0,32,64,96,128,192,256]
    if not args.execute:
        print('48 kHz / 128: compare playback headroom',candidates)
        print('Screen each with 1-minute sine/white/pink. Confirm eligible candidates with 5/15/30 minutes and two fresh starts. Target 10–12 ms. Preserve defaults; recommendation only.');return
    storage=ROOT/'build/latency/nightly-regression';storage.mkdir(parents=True,exist_ok=True)
    lock=Path('/tmp/eleven-rack-regression-%d.lock' % os.getuid()).open('a')
    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: raise SystemExit('Regression runner active; postpone tuning until it finishes')
    def stop(signum,frame): raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop)
    if args.output.exists(): raise SystemExit('Refusing to overwrite results')
    args.output.mkdir(parents=True)
    report={'target_ms':[10,12],'candidates':[],'recommendation':None,'defaults_changed':False}
    def save(): (args.output/'tuning.json').write_text(json.dumps(report,indent=2)+'\n')
    def run(headroom,folder,minutes,cycles=1):
        env=dict(os.environ)
        env.pop('ELEVEN_TEST_PLAYBACK_HEADROOM',None)
        if headroom!='default': env['ELEVEN_TEST_PLAYBACK_HEADROOM']=str(headroom)
        # White noise needs the fixed analog-response analysis; raw correlation
        # fails on the AC-coupled analog input regardless of the candidate.
        command=[sys.executable,str(ROOT/'tools/test-audio-regression.py'),'--analog-white-noise','--output',str(folder),'--profiles','48000:128','--minutes',*map(str,minutes),'--cycles',str(cycles)]
        with folder.with_suffix('.log').open('w') as log:
            child=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT)
            try: child.wait()
            except KeyboardInterrupt:
                child.send_signal(2);child.wait();raise
        result=assess(folder)
        expected=3*len(minutes)*cycles
        result['passed']=result['passed'] and result['runs']==expected
        return result
    try:
        for headroom in candidates:
            row={'headroom_frames':headroom,'screen':run(headroom,args.output/f'headroom-{headroom}-screen',[1])}
            report['candidates'].append(row);save()
            if not row['screen']['restored']: raise RuntimeError('Restoration failed; stopped tuning')
        eligible=[r for r in report['candidates'] if r['screen']['passed'] and r['screen']['roundtrip_ms'] is not None and 10<=r['screen']['roundtrip_ms']<=12]
        eligible.sort(key=lambda r:abs(r['screen']['roundtrip_ms']-12))
        for row in eligible:
            headroom=row['headroom_frames']
            row['confirmation']=run(headroom,args.output/f'headroom-{headroom}-confirmation',[5,15,30],2);save()
            if not row['confirmation']['restored']: raise RuntimeError('Restoration failed; stopped tuning')
            ms=row['confirmation']['roundtrip_ms']
            if row['confirmation']['passed'] and ms is not None and 10<=ms<=12:
                report['recommendation']={'playback_headroom_frames':headroom,'roundtrip_ms':ms,'requires_review':True};break
    finally: save()
    print(json.dumps(report,indent=2))
if __name__=='__main__': main()

#!/usr/bin/env python3
"""Run sine, white and pink loopback matrices, restoring audio settings per matrix."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seconds',type=int,help='Short diagnostic duration; overrides --minutes')
    parser.add_argument('--minutes',type=int,nargs='+',choices=[1,5,15,30],default=[1,5,15,30])
    parser.add_argument('--cycles',type=int,default=1)
    parser.add_argument('--signals',nargs='+',choices=['sine','white','pink','multitone'],default=['sine','white','pink'])
    parser.add_argument('--profiles',nargs='+',default=[f'{r}:{q}' for r in (44100,48000,88200,96000) for q in (64,128,256,512,1024,2048)])
    parser.add_argument('--plan',action='store_true',help='Show duration and profiles without touching audio')
    args=parser.parse_args()
    durations=[args.seconds] if args.seconds is not None else [m*60 for m in args.minutes]
    if any(not 1<=s<=1800 for s in durations) or args.cycles<1: parser.error('seconds: 1..1800; cycles: positive')
    allowed={f'{r}:{q}' for r in (44100,48000,88200,96000) for q in (64,128,256,512,1024,2048)}
    if any(p not in allowed for p in args.profiles): parser.error('Unsupported profile')
    print(f'{len(args.profiles)*len(args.signals)*args.cycles*len(durations)} runs; {len(args.profiles)*len(args.signals)*args.cycles*sum(durations)/60:.1f} minutes of signal, plus setup/warmup',flush=True)
    if args.plan: return
    if args.output.exists(): parser.error('Output already exists')
    args.output.mkdir(parents=True)
    report={'started':time.time(),'runs':[],'completed':False}
    def save(): (args.output/'regression.json').write_text(json.dumps(report,indent=2)+'\n')
    child=None
    def interrupt(signum,frame):
        if child is not None and child.poll() is None: child.send_signal(signal.SIGINT)
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,interrupt)
    try:
        subprocess.run(['cc','-O2','-Wall','-Wextra','-Werror',str(ROOT/'tools/jack-loopback.c'),'-o',str(ROOT/'build/latency/jack-loopback-diagnostic'),'-l:libjack.so.0','-lm'],check=True)
        subprocess.run(['cc','-shared','-fPIC','-O2',str(ROOT/'tools/latency-correlation.c'),'-o',str(ROOT/'build/latency/liblatency-correlation.so'),'-lm'],check=True)
        for cycle in range(1,args.cycles+1):
            for seconds in durations:
              for kind in args.signals:
                out=args.output/f'cycle-{cycle}-{seconds}s-{kind}'
                env=dict(os.environ,ELEVEN_TEST_SIGNAL=kind,ELEVEN_TEST_SECONDS=str(seconds))
                child=subprocess.Popen([sys.executable,str(ROOT/'tools/test-full-latency-matrix.py'),'--regression','--output',str(out),'--starts',str(cycle),'--profiles',*args.profiles],env=env)
                try: code=child.wait()
                except KeyboardInterrupt:
                    child.send_signal(signal.SIGINT)
                    child.wait(timeout=60)
                    raise
                report['runs'].append({'cycle':cycle,'signal':kind,'seconds':seconds,'directory':str(out),'returncode':code});save()
                if code: raise RuntimeError('Matrix stopped; see retained logs')
        report['completed']=True
    finally:
        report['finished']=time.time();save()
    failed=sum(not row['valid'] for run in report['runs'] for row in json.loads((Path(run['directory'])/'matrix.json').read_text())['results'])
    print(f'Finished: {failed} failing profiles. Reports: {args.output}',flush=True)
    if failed: sys.exit(1)
if __name__=='__main__': main()

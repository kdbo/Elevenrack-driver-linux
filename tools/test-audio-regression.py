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
    parser.add_argument('--analog-white-noise', action='store_true',
                        help='Use fixed-response analog white-noise analysis; keep raw results and timing checks')
    parser.add_argument('--platform-calibration', type=int, default=0, metavar='SECONDS',
                        help='Before audio, busy-loop this long to measure SMI/stolen-time gaps (0: skip)')
    parser.add_argument('--transport-trace', action='store_true',
                        help='Record xHCI completion errors and PipeWire resyncs during each matrix')
    parser.add_argument('--usb-flight', action='store_true',
                        help='Dump a kernel flight recorder before each playback Ring Underrun')
    args=parser.parse_args()
    if not 0<=args.platform_calibration<=600: parser.error('platform calibration: 0..600 seconds')
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
        if args.analog_white_noise:
            subprocess.run(['cc','-shared','-fPIC','-O2',str(ROOT/'tools/loopback-filter.c'),
                            '-o',str(ROOT/'build/latency/libloopback-filter.so'),'-lm'],check=True)
        # Unprivileged fallback; the installed cap_perfmon copy is preferred for SMI counts.
        subprocess.run(['cc','-O2','-Wall','-Wextra','-Werror',str(ROOT/'tools/smi-counter.c'),'-o',str(ROOT/'build/latency/smi-counter')],check=True)
        if args.transport_trace or args.usb_flight:
            # Unprivileged build; only the installed cap_dac_override copy can trace.
            subprocess.run(['cc','-O2','-Wall','-Wextra','-Werror',str(ROOT/'tools/xhci-trace.c'),'-o',str(ROOT/'build/latency/xhci-trace')],check=True)
        if args.platform_calibration:
            sys.path.insert(0,str(ROOT/'tools'))
            import platform_noise
            calibration=platform_noise.calibrate(args.platform_calibration)
            (args.output/'platform-calibration.json').write_text(json.dumps(calibration,indent=2)+'\n')
            report['platform_calibration']={k:v for k,v in calibration.items() if k!='gaps'};save()
            print('Platform calibration:',json.dumps(report['platform_calibration']),flush=True)
        for cycle in range(1,args.cycles+1):
            for seconds in durations:
              for kind in args.signals:
                out=args.output/f'cycle-{cycle}-{seconds}s-{kind}'
                env=dict(os.environ,ELEVEN_TEST_SIGNAL=kind,ELEVEN_TEST_SECONDS=str(seconds))
                analysis_flags = ['--analog-white-noise'] if args.analog_white_noise and kind == 'white' else []
                if args.transport_trace: analysis_flags.append('--transport-trace')
                if args.usb_flight: analysis_flags.append('--usb-flight')
                child=subprocess.Popen([sys.executable,str(ROOT/'tools/test-full-latency-matrix.py'),'--regression',*analysis_flags,'--output',str(out),'--starts',str(cycle),'--profiles',*args.profiles],env=env)
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
    rows=[row for run in report['runs'] for row in json.loads((Path(run['directory'])/'matrix.json').read_text())['results']]
    failed=sum(not row['valid'] for row in rows)
    print(f'Finished: {failed} failing profiles. Reports: {args.output}',flush=True)
    if failed:
        causes={}
        for row in rows:
            if not row['valid']:
                cause=row.get('platform',{}).get('classification','none')
                causes[cause]=causes.get(cause,0)+1
        print('Failing profiles by platform attribution:',', '.join(f'{k}={v}' for k,v in sorted(causes.items())),flush=True)
    if failed: sys.exit(1)
if __name__=='__main__': main()

#!/usr/bin/env python3
"""Persistent regression queue, admitted only inside the Brussels night window."""
import argparse
from datetime import datetime, timedelta
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
ZONE=ZoneInfo('Europe/Brussels')

def tasks():
    return [(r,q,m,s) for m in (1,5,15,30) for r in (48000,44100,88200,96000) for q in (128,64,256,512,1024,2048) for s in ('sine','white','pink')]

def deadline(now):
    if now.hour>=23: return (now+timedelta(days=1)).replace(hour=3,minute=55,second=0,microsecond=0)
    if now.hour<4: return now.replace(hour=3,minute=55,second=0,microsecond=0)
    return None

def remove_passed_recordings(output, reports):
    """Delete raw recordings of a passed task; analyses, logs and failed recordings stay."""
    results=[row for report in reports for row in report.get('results',[])]
    if not results or not all(row.get('passed') is True for row in results): return None
    removed=0
    for path in output.rglob('*.raw'):
        if path.is_file() and not path.is_symlink():
            removed+=path.stat().st_size;path.unlink()
    return removed

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',action='store_true')
    window=parser.add_mutually_exclusive_group()
    window.add_argument('--start-now',action='store_true',help='Manually open a five-hour window using the same queue')
    window.add_argument('--until', help='Run until the next HH:MM Europe/Brussels (tomorrow if already passed), reserving five minutes for restoration')
    args=parser.parse_args()
    until=None
    if args.until:
        try:
            until=datetime.strptime(args.until, '%H:%M').time()
        except ValueError:
            parser.error('--until must be HH:MM')
    if args.plan:
        print('288 tasks: all 24 profiles × sine/white/pink × 1/5/15/30 minutes. Persistent queue, 23:00–03:55; reserve until 04:00 for restoration.');return
    def cancelled(signum,frame): raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,cancelled)
    storage=ROOT/'build/latency/nightly-regression';storage.mkdir(parents=True,exist_ok=True)
    lock=Path('/tmp/eleven-rack-regression-%d.lock' % os.getuid()).open('a')
    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: print('Another nightly run is active');return
    now=datetime.now(ZONE);end=now+timedelta(hours=4,minutes=55) if args.start_now else deadline(now)
    if until is not None:
        end=now.replace(hour=until.hour,minute=until.minute,second=0,microsecond=0)
        # A time that has already passed today means tomorrow, so a run can last overnight.
        if end<=now: end+=timedelta(days=1)
        end-=timedelta(minutes=5)
    if end is None or now>=end: print('Outside testing window');return
    os.environ.setdefault('XDG_RUNTIME_DIR',f'/run/user/{os.getuid()}')
    os.environ.setdefault('DBUS_SESSION_BUS_ADDRESS',f'unix:path={os.environ["XDG_RUNTIME_DIR"]}/bus')
    statefile=storage/'queue.json'
    state=json.loads(statefile.read_text()) if statefile.exists() else {'next_task':0,'results':[]}
    def save():
        temp=statefile.with_suffix('.tmp');temp.write_text(json.dumps(state,indent=2)+'\n');temp.replace(statefile)
    queue=tasks()
    first_task=state['next_task']
    # Tasks to measure again after the queue, for example after a failure with an outside cause.
    rerunfile=storage/'reruns.json'
    reruns=json.loads(rerunfile.read_text()) if rerunfile.exists() else []
    plan=[(index,False) for index in range(first_task,len(queue))]+[(index,True) for index in reruns if 0<=index<len(queue)]
    for position,(index,rerun) in enumerate(plan):
        stop_request = storage / 'stop-after-current'
        if stop_request.exists():
            stop_request.unlink()
            print('Stopped after previous measurement; queue retained.', flush=True)
            break
        r,q,m,kind=queue[index]
        remaining=(end-datetime.now(ZONE)).total_seconds()
        if remaining<m*60+120: print('Next task reserved for tomorrow');break
        if shutil.disk_usage(storage).free<8*1024**3: print('Stopped: less than 8 GiB free');break
        if subprocess.run(['pgrep','-x','reaper'],stdout=subprocess.DEVNULL).returncode==0: print('REAPER active; postponed');break
        name=f'{index:03d}-{r}-{q}-{m}min-{kind}-{"rerun-" if rerun else ""}{datetime.now(ZONE):%Y%m%d-%H%M%S}'
        output=storage/name
        print('Starting',name,flush=True)
        analysis_flags = ['--analog-white-noise'] if kind == 'white' else []
        # Explains delay steps: xHCI Ring Underruns versus PipeWire resyncs.
        analysis_flags += ['--transport-trace', '--usb-flight']
        # One SMI/stolen-time calibration per night, before the first audio task.
        if position == 0: analysis_flags += ['--platform-calibration', '30']
        with (storage/(name+'.log')).open('w') as log:
            child=subprocess.Popen([sys.executable,str(ROOT/'tools/test-audio-regression.py'),*analysis_flags,'--output',str(output),'--profiles',f'{r}:{q}','--minutes',str(m),'--signals',kind],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            try:
                while child.poll() is None:
                    if datetime.now(ZONE)>=end:
                        child.terminate();child.wait(timeout=90);break
                    time.sleep(2)
            except BaseException:
                if child.poll() is None:
                    child.terminate()
                    try: child.wait(timeout=90)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid,signal.SIGKILL)
                raise
        matrices=list(output.glob('*/matrix.json'))
        complete=False
        restored=False
        driver_srcversion=None
        platform=None
        transport=None
        passed=None
        removed=None
        if matrices:
            report=json.loads(matrices[0].read_text())
            driver_srcversion=report.get('driver_srcversion')
            platform=next((row.get('platform',{}).get('classification') for row in report.get('results',[])),None)
            transport=next((row.get('transport',{}).get('classification') for row in report.get('results',[])),None)
            restored=report.get('restored',False)
            complete=restored and len(report.get('results',[]))==1
            passed=all(row.get('passed') is True for row in report.get('results',[])) if complete else None
            # About 1.3 GB per 30-minute task: keep recordings only where a fault needs inspection.
            if complete: removed=remove_passed_recordings(output,[json.loads(path.read_text()) for path in matrices])
        state['results'].append({'task':index,'profile':[r,q],'minutes':m,'signal':kind,'returncode':child.returncode,'complete':complete,'restored':restored,'passed':passed,'recordings_removed_bytes':removed,'rerun':rerun,'driver_srcversion':driver_srcversion,'platform':platform,'transport':transport,'output':str(output)})
        if complete and not rerun: state['next_task']=index+1
        save()
        if complete and rerun:
            reruns=json.loads(rerunfile.read_text()) if rerunfile.exists() else []
            if index in reruns: reruns.remove(index)
            rerunfile.write_text(json.dumps(reruns)+'\n')
        if (storage / 'stop-after-current').exists():
            (storage / 'stop-after-current').unlink()
            print('Stopped after current measurement; queue retained.', flush=True)
            break
        if not complete:
            print('Incomplete task; queue paused until next night. Inspect logs.',flush=True);break
    pending=json.loads(rerunfile.read_text()) if rerunfile.exists() else []
    if state['next_task']==len(queue) and not pending: print('Full regression queue completed; logs retained.')
if __name__=='__main__': main()

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

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',action='store_true')
    parser.add_argument('--start-now',action='store_true',help='Manually open a five-hour window using the same queue')
    args=parser.parse_args()
    if args.plan:
        print('288 tasks: all 24 profiles × sine/white/pink × 1/5/15/30 minutes. Persistent queue, 23:00–03:55; reserve until 04:00 for restoration.');return
    def cancelled(signum,frame): raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,cancelled)
    storage=ROOT/'build/latency/nightly-regression';storage.mkdir(parents=True,exist_ok=True)
    lock=Path('/tmp/eleven-rack-regression-%d.lock' % os.getuid()).open('a')
    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: print('Another nightly run is active');return
    now=datetime.now(ZONE);end=now+timedelta(hours=4,minutes=55) if args.start_now else deadline(now)
    if end is None or now>=end: print('Outside testing window');return
    os.environ.setdefault('XDG_RUNTIME_DIR',f'/run/user/{os.getuid()}')
    os.environ.setdefault('DBUS_SESSION_BUS_ADDRESS',f'unix:path={os.environ["XDG_RUNTIME_DIR"]}/bus')
    statefile=storage/'queue.json'
    state=json.loads(statefile.read_text()) if statefile.exists() else {'next_task':0,'results':[]}
    def save():
        temp=statefile.with_suffix('.tmp');temp.write_text(json.dumps(state,indent=2)+'\n');temp.replace(statefile)
    queue=tasks()
    for index in range(state['next_task'],len(queue)):
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
        name=f'{index:03d}-{r}-{q}-{m}min-{kind}-{datetime.now(ZONE):%Y%m%d-%H%M%S}'
        output=storage/name
        print('Starting',name,flush=True)
        with (storage/(name+'.log')).open('w') as log:
            child=subprocess.Popen([sys.executable,str(ROOT/'tools/test-audio-regression.py'),'--output',str(output),'--profiles',f'{r}:{q}','--minutes',str(m),'--signals',kind],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
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
        if matrices:
            report=json.loads(matrices[0].read_text())
            restored=report.get('restored',False)
            complete=restored and len(report.get('results',[]))==1
        state['results'].append({'task':index,'profile':[r,q],'minutes':m,'signal':kind,'returncode':child.returncode,'complete':complete,'restored':restored,'output':str(output)})
        if complete: state['next_task']=index+1
        save()
        if (storage / 'stop-after-current').exists():
            (storage / 'stop-after-current').unlink()
            print('Stopped after current measurement; queue retained.', flush=True)
            break
        if not complete:
            print('Incomplete task; queue paused until next night. Inspect logs.',flush=True);break
    if state['next_task']==len(queue): print('Full regression queue completed; logs retained.')
if __name__=='__main__': main()

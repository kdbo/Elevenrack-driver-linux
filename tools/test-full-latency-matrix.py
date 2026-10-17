#!/usr/bin/env python3
"""Measure 18 profiles on two fresh audio starts, restoring user settings."""
import importlib.util
import argparse
import csv
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/latency/full-profile-matrix'
PROFILES = [(r, q) for r in (44100, 48000) for q in (128,64,256,512,1024,2048)] + [(r,q) for r in (88200,96000) for q in (512,1024,2048)]
UNITS = ['wireplumber.service','pipewire-pulse.service','pipewire-pulse.socket','pipewire.service','pipewire.socket']

class RateOverride:
    """Back up an existing rule before using its filename for a test."""
    def __init__(self, path, backup_directory):
        self.path = path
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise RuntimeError('Rate override must be a regular file')
        self.original = path.read_bytes() if path.exists() else None
        self.mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
        if self.original is not None:
            (backup_directory/'original-rate-override.conf').write_bytes(self.original)

    def restore(self):
        if self.original is None:
            self.path.unlink(missing_ok=True)
        else:
            self.path.write_bytes(self.original)
            self.path.chmod(self.mode)

    def restored(self):
        if self.original is None:
            return not self.path.exists()
        return (self.path.is_file() and self.path.read_bytes() == self.original
                and stat.S_IMODE(self.path.stat().st_mode) == self.mode)

def call(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT)

def stop():
    call('systemctl','--user','stop','pipewire-pulse.socket','pipewire.socket')
    call('systemctl','--user','stop','wireplumber.service','pipewire-pulse.service','pipewire.service')

def recording_bounds(raw, rate):
    """Use recorded callbacks, including the final block's duration."""
    with Path(str(raw)+'.timestamps.csv').open() as stream:
        stamps = csv.DictReader(stream)
        first = next(stamps, None)
        if first is None or int(first['frame']) != 0:
            raise ValueError('Missing recording start timestamp')
        last = first
        for last in stamps:
            pass
    sample_count = raw.stat().st_size // 4
    final_frames = min(int(last['frames']), sample_count-int(last['frame']))
    if final_frames <= 0:
        raise ValueError('Invalid recording end timestamp')
    return (int(first['realtime_ns']),
            int(last['realtime_ns']) + final_frames*1_000_000_000//rate)


def pcm_restarted(snapshots, bounds=None):
    """Keep a warmup baseline, but reject only changes within recording."""
    for direction in ('p', 'c'):
        previous = None
        for snapshot in snapshots:
            if bounds is not None and snapshot['realtime_ns'] >= bounds[1]:
                break
            for value in re.findall(r'^trigger_time\s*:\s*(.+)', snapshot[direction+'_status'], re.M):
                value = value.strip()
                if re.fullmatch(r'0+(?:\.0+)?', value):
                    continue
                in_recording = bounds is None or snapshot['realtime_ns'] >= bounds[0]
                if previous is not None and value != previous and in_recording:
                    return True
                previous = value
    return False

def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--regression', action='store_true', help='Analyze continuous regression signal instead of calibration bursts')
    parser.add_argument('--analog-white-noise', action='store_true',
                        help='Validate a fixed analog response for white-noise regression; retain timing faults')
    parser.add_argument('--output', type=Path, default=OUT)
    parser.add_argument('--starts', type=int, nargs='+', default=[1,2])
    parser.add_argument('--profiles', nargs='+', help='Subset as rate:quantum, for invalid-run recovery')
    args = parser.parse_args()
    if args.analog_white_noise and (not args.regression or os.environ.get('ELEVEN_TEST_SIGNAL') != 'white'):
        parser.error('--analog-white-noise requires white-noise regression')
    headroom = os.environ.get('ELEVEN_TEST_PLAYBACK_HEADROOM')
    if headroom is not None and (not headroom.isdecimal() or not 0 <= int(headroom) <= 512):
        parser.error('Playback headroom must be 0..512 frames')
    OUT = args.output.resolve()
    profiles = PROFILES
    if args.profiles:
        profiles = [tuple(map(int, p.split(':'))) for p in args.profiles]
        if any(p not in [(r,q) for r in (44100,48000,88200,96000) for q in (64,128,256,512,1024,2048)] for p in profiles): raise RuntimeError('Unsupported profile')
    if OUT.exists(): raise RuntimeError('Refusing to overwrite existing matrix')
    if subprocess.run(['pgrep','-x','reaper'], stdout=subprocess.DEVNULL).returncode == 0:
        raise RuntimeError('Save and close REAPER first')
    settings = dict(re.findall(r"key:'([^']+)' value:'([^']+)'",call('pw-metadata','-n','settings')))
    hardware = call('python3',str(ROOT/'tools/eleven-rack-settings.py'),'rate')
    original_rate = int(re.search(r'Hardware sample rate: (\d+)',hardware)[1])
    active = [u for u in UNITS if subprocess.run(['systemctl','--user','is-active','--quiet',u]).returncode==0]
    config = Path('/etc/wireplumber/wireplumber.conf.d/52-eleven-rack-latency.conf').read_text()
    old = {(int(r),int(q)):int(v) for r,q,v in re.findall(r'eleven-correction-(\d+)-(\d+)\s*=\s*(-?\d+)',config)}
    analyzer = ('tools/analyze-white-noise-path.py' if args.analog_white_noise else
                'tools/analyze-loopback-regression.py' if args.regression else 'tools/analyze-jack-loopback.py')
    spec = importlib.util.spec_from_file_location('analysis', ROOT/analyzer)
    analysis = importlib.util.module_from_spec(spec); spec.loader.exec_module(analysis)
    spec = importlib.util.spec_from_file_location('platform_noise', ROOT/'tools/platform_noise.py')
    platform = importlib.util.module_from_spec(spec); spec.loader.exec_module(platform)
    OUT.mkdir()
    report = {'original_settings':settings,'original_hardware_rate':original_rate,'results':[],'restored':False}
    report['driver_srcversion'] = Path('/sys/module/snd_usb_audio/srcversion').read_text().strip()
    rate_config = Path.home()/'.config/wireplumber/wireplumber.conf.d/99-eleven-matrix-rate.conf'
    override = RateOverride(rate_config, OUT)
    report['original_rate_override_existed'] = override.original is not None
    report['original_rate_override_mode'] = override.mode
    rate_config.parent.mkdir(parents=True,exist_ok=True)
    def save(): (OUT/'matrix.json').write_text(json.dumps(report,indent=2)+'\n')
    smi = platform.SmiMonitor(OUT/'smi.csv').__enter__()
    report['smi_counter'] = smi.status
    save()
    try:
        for repeat in args.starts:
            for rate,quantum in profiles:
                stop()
                rate_config.write_text('monitor.alsa.rules = [ { matches = [\n'
                    '{ node.name = "~alsa_input.usb-Digidesign_Eleven_Rack.*" api.alsa.card.id = "Rack" }\n'
                    '{ node.name = "~alsa_output.usb-Digidesign_Eleven_Rack.*" api.alsa.card.id = "Rack" }\n'
                    '] actions = { update-props = { audio.rate = '+str(rate)+' } } } ]\n')
                if headroom is not None:
                    with rate_config.open('a') as override:
                        override.write('monitor.alsa.rules = [ { matches = [ { node.name = \"~alsa_output.usb-Digidesign_Eleven_Rack.*\" api.alsa.card.id = \"Rack\" } ] actions = { update-props = { api.alsa.headroom = '+headroom+' } } } ]\n')
                subprocess.run(['arecord','-D','hw:Rack,0','-f','S32_LE','-r',str(rate),'-c','8','-d','1','-t','raw','/dev/null'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                call('systemctl','--user','start',*[u for u in active if u != 'wireplumber.service'])
                time.sleep(1)
                for k,v in [('clock.allowed-rates',f'[ {rate} ]'),('clock.rate',str(rate)),('clock.force-rate',str(rate)),('clock.force-quantum',str(quantum))]:
                    call('pw-metadata','-n','settings','0',k,v)
                if 'wireplumber.service' in active:
                    call('systemctl','--user','start','wireplumber.service')
                time.sleep(2)
                directory = OUT/f'{rate}-{quantum}-start-{repeat}'
                # PipeWire sometimes applies the second playback configuration after
                # a 5 s delay; a 6 s warmup keeps that reopen out of the recording.
                env = dict(os.environ,ELEVEN_TEST_WARMUP_SECONDS='6')
                subprocess.run([sys.executable,str(ROOT/'tools/record-latency-status.py'),'--binary',str(ROOT/'build/latency/jack-loopback-diagnostic'),'--output',str(directory),'--quanta',str(quantum),'--repeats','1'],check=True,env=env, stdout=subprocess.DEVNULL)
                raw = directory/f'quantum-{quantum}-run-1.raw'
                row = {'rate_hz':rate,'quantum':quantum,'start':repeat,'existing_correction':old.get((rate,quantum),0)}
                result = {}
                try:
                    result = analysis.analyze(raw)
                    if result['rate_hz'] != rate or result['quantum'] != quantum: raise ValueError('Graph mismatch')
                    snapshots = json.loads(raw.with_suffix('.status.json').read_text())
                    for d in ('p','c'):
                        actual = {int(v) for x in snapshots for v in re.findall(r'^rate: (\d+)',x[d+'_hw_params'],re.M)}
                        if actual != {rate}: raise ValueError('ALSA rate mismatch')
                    if args.regression:
                        bounds = recording_bounds(raw, rate)
                        row['recording_start_realtime_ns'], row['recording_end_realtime_ns'] = bounds
                        if pcm_restarted(snapshots, bounds):
                            raise ValueError('PCM restarted during regression')
                    if any(result.get('alsa_transport', {}).values()): raise ValueError('PCM restarted during recording')
                    row.update(result)
                    row['valid'] = result.get('passed', True)
                    if not row['valid']: row['error'] = 'Signal continuity screening or xruns failed'
                except (ValueError, OSError, KeyError) as error:
                    row.update(valid=False,error=str(error))
                if args.regression:
                    # Evidence only; never changes the verdict. Also runs after a
                    # rejected recording: a long SMI is what restarts the PCM.
                    try:
                        row['platform'] = platform.attribute(
                            raw, rate, quantum, result.get('faults', []) + result.get('dense_faults', []),
                            smi.status, platform.smi_events(OUT/'smi.csv'))
                    except (ValueError, OSError, KeyError, IndexError) as error:
                        row['platform'] = {'classification': 'error', 'error': str(error)}
                report['results'].append(row); save()
                if args.regression:
                    print('REGRESSION',rate,quantum,'START',repeat,'PASS' if row['valid'] else 'FAIL',
                          'platform='+row.get('platform',{}).get('classification','none'),flush=True)
                elif row['valid']:
                    values = [b['minus_live_reported_frames'] for b in row['bursts'] if b['stimulus_seconds']>=2.5]
                    print('PROFILE',rate,quantum,'START',repeat,'RESIDUAL',values,flush=True)
                else:
                    print('PROFILE',rate,quantum,'START',repeat,'INVALID',row['error'],flush=True)
                if len(report['results']) == 1 and not row['valid'] and 'correlated' in row['error']:
                    raise RuntimeError('First probe has no reliable signal; check loopback before continuing')
    finally:
        smi.__exit__(None, None, None)
        try:
            try:
                stop()
            finally:
                override.restore()
            try:
                subprocess.run(['arecord','-D','hw:Rack,0','-f','S32_LE','-r',str(original_rate),'-c','8','-d','1','-t','raw','/dev/null'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            finally:
                call('systemctl','--user','start',*active)
            time.sleep(2)
            for key in ('clock.allowed-rates','clock.rate','clock.force-rate','clock.force-quantum'):
                if key in settings: call('pw-metadata','-n','settings','0',key,settings[key])
            report['final_settings'] = dict(re.findall(r"key:'([^']+)' value:'([^']+)'", call('pw-metadata','-n','settings')))
            hardware = call('python3',str(ROOT/'tools/eleven-rack-settings.py'),'rate')
            report['final_hardware_rate'] = int(re.search(r'Hardware sample rate: (\d+)', hardware)[1])
            report['final_driver_srcversion'] = Path('/sys/module/snd_usb_audio/srcversion').read_text().strip()
            report['rate_override_restored'] = override.restored()
            report['restored'] = (report['rate_override_restored']
                and report['final_hardware_rate'] == original_rate
                and all(report['final_settings'].get(k) == settings.get(k) for k in
                        ('clock.allowed-rates','clock.rate','clock.force-rate','clock.force-quantum'))
                and all(subprocess.run(['systemctl','--user','is-active','--quiet',u]).returncode == 0 for u in active))
            if not report['restored']:
                raise RuntimeError('Original audio settings restoration could not be verified')
            print('Original audio settings restored and verified',flush=True)
        except BaseException as error:
            report['restore_error'] = str(error)
            raise
        finally:
            save()

if __name__ == '__main__': main()

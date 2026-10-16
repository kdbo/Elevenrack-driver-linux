"""Attribute regression stalls and faults to firmware SMIs.

The SMI count comes from tools/smi-counter.c, installed root-owned with
cap_perfmon so the unprivileged nightly runner can read it. Attribution is
correlation in time, not proof: an SMI event and a stall in the same interval.
"""
import bisect
import csv
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
HELPER = Path('/usr/local/libexec/eleven-rack-smi-counter')
STALL_NS = 5_000_000     # callback arriving >=5 ms later than its predecessor's frames
OVERLAP_NS = 2_000_000   # timestamp slack between helper and JACK callbacks
LIMITATIONS = ('SMI attribution is coincidence in time with a 10 ms sampler, not proof of cause. '
               'Xruns carry no timestamps; only callback stalls and analysis faults are attributed. '
               'Fault windows include round-trip slack and can match an unrelated nearby SMI.')


def helper_path():
    if HELPER.exists():
        return HELPER
    built = ROOT/'build/latency/smi-counter'
    return built if built.exists() else None


class SmiMonitor:
    """Run the helper's monitor mode for the lifetime of a matrix."""
    def __init__(self, path, period_ms=10, helper=None):
        self.path, self.period_ms = Path(path), period_ms
        self.helper = helper or helper_path()
        self.process, self.status = None, 'helper not installed'

    def __enter__(self):
        if self.helper is None:
            return self
        with self.path.open('w') as output:
            self.process = subprocess.Popen([str(self.helper), 'monitor', str(self.period_ms)],
                                            stdout=output, stderr=subprocess.PIPE, text=True)
        time.sleep(.2)
        if self.process.poll() is not None:
            self.status = 'unavailable: ' + (self.process.stderr.read().strip() or f'exit {self.process.returncode}')
            self.process.stderr.close()
            self.process = None
        else:
            self.status = 'available'
        return self

    def __exit__(self, *exc):
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process.stderr.close()
        return False

    @property
    def available(self):
        return self.status == 'available'


def smi_events(path):
    """Intervals (previous sample, sample] in which the SMI count increased."""
    events, previous = [], None
    try:
        with Path(path).open() as stream:
            for row in csv.DictReader(stream):
                sample = {k: int(v) for k, v in row.items()}
                if previous is not None and sample['smi_count'] > previous['smi_count']:
                    events.append({'start_ns': previous['realtime_ns'], 'end_ns': sample['realtime_ns'],
                                   'smi': sample['smi_count']-previous['smi_count'],
                                   'sampler_late_ns': sample['late_ns']})
                previous = sample
    except (OSError, ValueError, TypeError):
        return events
    return events


def callback_stamps(raw):
    with Path(str(raw)+'.timestamps.csv').open() as stream:
        return [(int(r['frame']), int(r['frames']), int(r['realtime_ns'])) for r in csv.DictReader(stream)]


def callback_stalls(stamps, rate, threshold_ns=STALL_NS):
    """Callbacks arriving well after the previous block's duration elapsed."""
    stalls = []
    for (_, frames, before), (frame, _, after) in zip(stamps, stamps[1:]):
        expected = before + frames*1_000_000_000//rate
        if after-expected >= threshold_ns:
            stalls.append({'frame': frame, 'start_ns': expected, 'end_ns': after, 'excess_ns': after-expected})
    return stalls


def frame_time(stamps, frames, frame):
    index = max(0, bisect.bisect_right(frames, frame)-1)
    return stamps[index][2]


def overlapping(events, start, end, slack=OVERLAP_NS):
    return [e for e in events if e['start_ns'] <= end+slack and e['end_ns'] >= start-slack]


def attribute(raw, rate, quantum, faults, monitor_status, events):
    """Mark each stall and fault window SMI-correlated or not; classify the run."""
    result = {'smi_counter': monitor_status, 'limitations': LIMITATIONS}
    if monitor_status != 'available':
        result['classification'] = 'unavailable'
        return result
    stamps = callback_stamps(raw)
    first, last = stamps[0][2], stamps[-1][2] + stamps[-1][1]*1_000_000_000//rate
    recording = overlapping(events, first, last, 0)
    stalls = callback_stalls(stamps, rate)
    for stall in stalls:
        stall['smi'] = bool(overlapping(recording, stall['start_ns'], stall['end_ns']))
    # A playback-side stall surfaces in the capture one round trip later; allow
    # four quanta plus 50 ms, and the 100 ms since the previous analysis window.
    lead = 4*quantum*1_000_000_000//rate + 50_000_000
    windows, frames = [], [s[0] for s in stamps]
    for fault in faults:
        frame = int(fault['seconds']*rate)
        start = frame_time(stamps, frames, max(0, frame-rate//10)) - lead
        end = frame_time(stamps, frames, frame) + 2*quantum*1_000_000_000//rate
        windows.append({'seconds': fault['seconds'], 'smi': bool(overlapping(recording, start, end))})
    marks = [s['smi'] for s in stalls] + [w['smi'] for w in windows]
    result.update({
        'smi_count_during_recording': sum(e['smi'] for e in recording),
        'smi_events': recording,
        'max_sampler_late_ns': max((e['sampler_late_ns'] for e in recording), default=0),
        'callback_stalls': stalls,
        'max_callback_stall_ns': max((s['excess_ns'] for s in stalls), default=0),
        'fault_windows': windows,
        'classification': ('clean' if not marks else 'smi_correlated' if all(marks)
                           else 'partly_smi' if any(marks) else 'not_smi'),
    })
    return result


def calibrate(seconds, threshold_us=100, helper=None):
    """Busy-loop gap scan without audio; gaps with no context switch are stolen time."""
    helper = helper or helper_path()
    if helper is None:
        return {'status': 'helper not installed'}
    run = subprocess.run([str(helper), 'spin', str(seconds), str(threshold_us)],
                         capture_output=True, text=True, timeout=seconds+30, check=True)
    return parse_calibration(run.stdout, threshold_us, run.stderr.strip())


def parse_calibration(text, threshold_us, note=''):
    lines = text.splitlines()
    summary = dict(item.split('=', 1) for item in lines[-1][2:].split()) if lines and lines[-1].startswith('#') else {}
    gaps = []
    for row in csv.DictReader(line for line in lines if not line.startswith('#')):
        gaps.append({'realtime_ns': int(row['realtime_ns']), 'gap_ns': int(row['gap_ns']),
                     'smi_delta': int(row['smi_delta']) if row['smi_delta'] else None,
                     'context_switches': int(row['context_switches'])})
    stolen = [g for g in gaps if g['context_switches'] == 0]
    smi_known = bool(summary.get('smi_total'))
    return {'status': 'available' if smi_known else 'gaps only; ' + note,
            'threshold_us': threshold_us,
            'duration_ns': int(summary.get('duration_ns', 0)),
            'smi_total': int(summary['smi_total']) if smi_known else None,
            'stolen_gaps': len(stolen),
            'max_stolen_gap_ns': max((g['gap_ns'] for g in stolen), default=0),
            'max_smi_gap_ns': max((g['gap_ns'] for g in stolen if g['smi_delta']), default=0) if smi_known else None,
            'gaps': gaps,
            'limitations': 'Stolen gaps had no context switch: SMI, interrupt or hypervisor time. '
                           'Only gaps with an SMI delta are firmware-attributed.'}

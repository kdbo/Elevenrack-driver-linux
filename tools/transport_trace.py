"""Attribute regression faults to USB (xHCI) or PipeWire transport events.

Delay steps without an xrun have two known transport causes: an xHCI Ring
Underrun on the playback endpoint, or a PipeWire follower resync that rewinds
or inserts silence. xHCI completion errors come from tools/xhci-trace.c,
installed root-owned with cap_dac_override so the unprivileged nightly runner
can trace. PipeWire resyncs are INFO messages; spa.alsa logging is raised only
for the PipeWire instance a test starts. Attribution is correlation in time,
like the SMI attribution, not proof.
"""
import contextlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
HELPER = Path('/usr/local/libexec/eleven-rack-xhci-trace')
PIPEWIRE_DEBUG = '2,spa.alsa:3'
RESYNC_SLACK_NS = 50_000_000   # PipeWire logs from its main loop, after the data thread
LIMITATIONS = ('Coincidence in time, not proof of cause. The xHCI trace covers the whole bus, '
               'so another device can match; slot and endpoint identify the stream. '
               'PipeWire messages carry journal timestamps and may be rate-limited.')

spec = importlib.util.spec_from_file_location('platform_noise', Path(__file__).with_name('platform_noise.py'))
platform = importlib.util.module_from_spec(spec)
spec.loader.exec_module(platform)


def helper_path():
    if HELPER.exists():
        return HELPER
    built = ROOT/'build/latency/xhci-trace'
    return built if built.exists() else None


class XhciMonitor(platform.SmiMonitor):
    """Run the xHCI trace helper for the lifetime of a matrix."""
    def __init__(self, path, helper=None):
        super().__init__(path)
        self.helper = helper or helper_path()

    def command(self):
        return [str(self.helper), 'monitor']


class FlightRecorder(XhciMonitor):
    """Keep the helper's flight recorder armed; it dumps on playback Ring Underruns."""
    def command(self):
        return [str(self.helper), 'flight']


EVENT = re.compile(r"^(-?\d+) .*?\s(\d+)\.(\d+):\s+xhci_handle_event:(.*)$")
DETAIL = re.compile(r"status '([^']*)' len (\d+) slot (\d+) ep (\d+) type '([^']*)'")


def endpoint_address(dci):
    """xHCI device context index to USB endpoint address (EP 0x03 OUT is DCI 6)."""
    return None if dci < 2 else f'0x{(0x80 if dci % 2 else 0) | dci // 2:02x}'


def xhci_events(path):
    events = []
    try:
        lines = Path(path).read_text(errors='replace').splitlines()
    except OSError:
        return events
    for line in lines:
        match = EVENT.match(line)
        if not match:
            continue
        offset, seconds, fraction, rest = match.groups()
        when = int(seconds)*1_000_000_000 + int(fraction.ljust(9, '0')[:9]) + int(offset)
        event = {'start_ns': when, 'end_ns': when}
        detail = DETAIL.search(rest)
        if detail:
            status, length, slot, dci, kind = detail.groups()
            event.update(status=status, length=int(length), slot=int(slot), ep=int(dci),
                         endpoint=endpoint_address(int(dci)), type=kind)
        else:
            event['line'] = rest.strip()
        events.append(event)
    return events


def user_environment():
    text = subprocess.check_output(['systemctl', '--user', 'show-environment'], text=True)
    return dict(line.split('=', 1) for line in text.splitlines() if '=' in line)


@contextlib.contextmanager
def pipewire_debug(enabled=True):
    """Raise spa.alsa logging for services started inside this block only."""
    if not enabled:
        yield
        return
    previous = user_environment().get('PIPEWIRE_DEBUG')
    subprocess.run(['systemctl', '--user', 'set-environment', f'PIPEWIRE_DEBUG={PIPEWIRE_DEBUG}'], check=True)
    try:
        yield
    finally:
        if previous is None:
            subprocess.run(['systemctl', '--user', 'unset-environment', 'PIPEWIRE_DEBUG'], check=True)
        else:
            subprocess.run(['systemctl', '--user', 'set-environment', f'PIPEWIRE_DEBUG={previous}'], check=True)


def pipewire_journal(start_ns, end_ns, path):
    """Save PipeWire's journal for the interval; return (status, resync/recover events)."""
    run = subprocess.run(['journalctl', '--user', '--no-pager', '-o', 'json', '-t', 'pipewire',
                          '--since', f'@{start_ns // 1_000_000_000}',
                          '--until', f'@{end_ns // 1_000_000_000 + 1}'],
                         capture_output=True, text=True)
    if run.returncode:
        return 'unavailable: ' + (run.stderr.strip() or f'exit {run.returncode}'), []
    lines, events = [], []
    for entry in run.stdout.splitlines():
        try:
            record = json.loads(entry)
        except ValueError:
            continue
        message = record.get('MESSAGE')
        if not isinstance(message, str):
            continue
        when = int(record['__REALTIME_TIMESTAMP'])*1000
        lines.append(f'{when} {message}')
        if re.search(r'resync|recover', message):
            events.append({'start_ns': when, 'end_ns': when, 'message': message})
    Path(path).write_text(''.join(line+'\n' for line in lines))
    return 'available', events


def attribute(raw, rate, quantum, faults, xhci_status, xhci, pipewire_status, resyncs):
    """Mark each fault window with coinciding xHCI errors and PipeWire resyncs."""
    result = {'xhci_trace': xhci_status, 'pipewire_log': pipewire_status, 'limitations': LIMITATIONS}
    has_xhci, has_pipewire = xhci_status == 'available', pipewire_status == 'available'
    if not has_xhci and not has_pipewire:
        result['classification'] = 'unavailable'
        return result
    stamps = platform.callback_stamps(raw)
    # Same window as the SMI attribution: one round trip back from the fault.
    lead = 4*quantum*1_000_000_000//rate + 50_000_000
    first, last = stamps[0][2] - lead, stamps[-1][2] + stamps[-1][1]*1_000_000_000//rate
    xhci = platform.overlapping(xhci, first, last, 0) if has_xhci else []
    resyncs = platform.overlapping(resyncs, first, last, 0) if has_pipewire else []
    windows, frames = [], [s[0] for s in stamps]
    for fault in faults:
        frame = int(fault['seconds']*rate)
        start = platform.frame_time(stamps, frames, max(0, frame-rate//10)) - lead
        end = platform.frame_time(stamps, frames, frame) + 2*quantum*1_000_000_000//rate
        usb = platform.overlapping(xhci, start, end)
        resync = bool(platform.overlapping(resyncs, start, end, RESYNC_SLACK_NS))
        causes = (['xhci'] if usb else []) + (['pipewire_resync'] if resync else [])
        label = '+'.join(causes) or ('unexplained' if has_xhci and has_pipewire else 'unknown')
        windows.append({'seconds': fault['seconds'], 'cause': label,
                        'xhci': sorted({f"{e.get('status')} slot {e.get('slot')} ep {e.get('endpoint')}" for e in usb})})
    labels = {w['cause'] for w in windows}
    result.update({
        'xhci_events_during_recording': xhci[:500],
        'xhci_event_count': len(xhci),
        'pipewire_resyncs_during_recording': resyncs,
        'fault_windows': windows,
        'classification': 'clean' if not windows else labels.pop() if len(labels) == 1 else 'mixed',
    })
    return result

#!/usr/bin/env python3
"""Explain playback Ring Underruns from xhci-trace flight recorder dumps.

Each dump holds the seconds before a Ring Underrun on the playback endpoint.
In implicit-feedback mode every capture URB completion releases one playback
URB, so the OUT ring only stays filled while capture completions are handled
on time. Per underrun this reports the capture completion gaps, the delay from
each capture completion to the next playback submission, empty capture URBs,
and what the handling CPU did in the window before the ring ran dry.
"""
import argparse
import json
from pathlib import Path
import re
import statistics

LINE = re.compile(r'^\s*(?P<task>.+?)-(?P<pid>\d+)\s+\[(?P<cpu>\d+)\]\s+\S+\s+'
                  r'(?P<seconds>\d+)\.(?P<fraction>\d+):\s+(?P<event>\w+):\s?(?P<rest>.*)$')
URB = re.compile(r'ep(\d+)(in|out)-isoc: urb (\S+) pipe \d+ slot (\d+) length (\d+)/(\d+)')
HANDLE = re.compile(r"status '([^']*)' len \d+ slot (\d+) ep (\d+)")
WINDOW_NS = 10_000_000      # timeline detail before the underrun
CONTEXT_EVENTS = {'irq_handler_entry', 'irq_handler_exit', 'softirq_entry', 'softirq_exit',
                  'sched_switch', 'sched_wakeup', 'cpu_idle'}


def parse(path):
    """Split the helper output into dumps of parsed trace events."""
    dumps, current = [], None
    for line in Path(path).read_text(errors='replace').splitlines():
        if line.startswith('# DUMP'):
            current = {'offset_ns': int(line.split()[-1]), 'events': []}
            continue
        if line.startswith('# END'):
            if current is not None:
                dumps.append(current)
            current = None
            continue
        match = LINE.match(line) if current is not None else None
        if not match:
            continue
        ns = int(match['seconds'])*1_000_000_000 + int(match['fraction'].ljust(9, '0')[:9])
        event = {'ns': ns, 'cpu': int(match['cpu']), 'task': match['task'].strip(),
                 'pid': int(match['pid']), 'event': match['event'], 'rest': match['rest']}
        urb = URB.search(match['rest']) if match['event'].startswith('xhci_urb_') else None
        if urb:
            event.update(ep=int(urb[1]), dir=urb[2], urb=urb[3], slot=int(urb[4]),
                         actual=int(urb[5]), length=int(urb[6]))
        handle = HANDLE.search(match['rest']) if match['event'] == 'xhci_handle_event' else None
        if handle:
            event.update(status=handle[1], slot=int(handle[2]), dci=int(handle[3]))
        current['events'].append(event)
    return dumps


def gaps(times):
    return [b-a for a, b in zip(times, times[1:])]


def summarize(values):
    if not values:
        return None
    return {'count': len(values), 'median_us': round(statistics.median(values)/1000, 1),
            'max_us': round(max(values)/1000, 1)}


def analyze_dump(dump):
    events = sorted(dump['events'], key=lambda e: e['ns'])
    underruns = [e for e in events if e.get('status') == 'Ring Underrun' and e.get('dci') == 6]
    if not underruns:
        return {'error': 'no playback Ring Underrun in dump'}
    underrun = underruns[-1]
    slot, t = underrun['slot'], underrun['ns']
    rack = [e for e in events if e.get('slot') == slot and 'ep' in e and e['ns'] <= t]
    captures = [e for e in rack if e['event'] == 'xhci_urb_giveback' and e['dir'] == 'in']
    submits = [e for e in rack if e['event'] == 'xhci_urb_enqueue' and e['dir'] == 'out']
    if not captures or not submits:
        return {'error': f'no Rack URB events for slot {slot}'}
    # Capture completion -> the playback submission it released (next OUT enqueue).
    release, index = [], 0
    for capture in captures:
        while index < len(submits) and submits[index]['ns'] < capture['ns']:
            index += 1
        if index < len(submits):
            release.append(submits[index]['ns']-capture['ns'])
    capture_gaps = gaps([c['ns'] for c in captures])
    last_capture, last_submit = captures[-1], submits[-1]
    cpus = {last_capture['cpu']} | {e['cpu'] for e in captures[-3:]}
    timeline = []
    for e in events:
        if not t-WINDOW_NS <= e['ns'] <= t:
            continue
        if e.get('slot') == slot or (e['cpu'] in cpus and e['event'] in CONTEXT_EVENTS) \
                or e['event'] == 'sched_wakeup':
            timeline.append({'us_before_underrun': round((t-e['ns'])/1000, 1), 'cpu': e['cpu'],
                             'task': f"{e['task']}-{e['pid']}", 'event': e['event'], 'detail': e['rest']})
    return {
        'underrun_realtime_ns': t + dump['offset_ns'],
        'slot': slot,
        'history_ms': round((t-events[0]['ns'])/1e6, 1),
        'capture_interval': summarize(capture_gaps),
        'capture_to_playback_submit': summarize(release),
        'empty_capture_urbs': sum(1 for c in captures if c['actual'] == 0),
        'last_capture_us_before_underrun': round((t-last_capture['ns'])/1000, 1),
        'last_playback_submit_us_before_underrun': round((t-last_submit['ns'])/1000, 1),
        'last_capture_gap_us': round(capture_gaps[-1]/1000, 1) if capture_gaps else None,
        'capture_cpus': sorted({c['cpu'] for c in captures[-20:]}),
        'timeline': timeline,
    }


def analyze(path):
    return [analyze_dump(d) for d in parse(path)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path, help='xhci-flight.log from a regression matrix')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    results = analyze(args.log)
    if args.json:
        print(json.dumps(results, indent=2))
        return
    if not results:
        print('No underrun dumps.')
    for n, r in enumerate(results):
        print(f'== Dump {n}')
        if 'error' in r:
            print(r['error'])
            continue
        for key, value in r.items():
            if key != 'timeline':
                print(f'{key}: {value}')
        print(f'timeline (last {WINDOW_NS//1_000_000} ms, Rack URBs + capture CPU context):')
        for e in r['timeline']:
            print(f"  -{e['us_before_underrun']:>8} us cpu{e['cpu']} {e['task']:<24} {e['event']}: {e['detail']}")


if __name__ == '__main__':
    main()

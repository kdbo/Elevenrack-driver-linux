#!/usr/bin/env python3
"""Read-only Eleven Rack audio diagnostics for the control panel's Monitor window.

Everything here works without root: driver counters and ALSA stream state from
/proc/asound, PipeWire graph timing and xruns from pw-dump/pw-top, and a check
of the CPU placement that decides how quickly USB completions are handled.
Run directly for a text report: python3 eleven_rack_diagnostics.py [--device ID]
or record to a log file until Ctrl+C: python3 eleven_rack_diagnostics.py --log [FILE]
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time

PROC = Path('/proc')
SYS = Path('/sys')
SCHED_NAMES = {os.SCHED_OTHER: 'normal', os.SCHED_FIFO: 'FIFO', os.SCHED_RR: 'RR'}
DRIVER_HELP = ('Counted by the driver since the Rack was connected. A playback gap means USB '
               'completions were handled too late: the Rack played a short silence and later '
               'audio shifted by that time.')


def key_values(text):
    values = {}
    for line in text.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            values[parts[0].rstrip(':')] = parts[1].strip()
    return values


def driver_stats(card, proc=PROC):
    """The driver's counters from eleven_stats, or None for a driver without them."""
    try:
        values = key_values((proc/'asound'/f'card{card}'/'eleven_stats').read_text())
    except OSError:
        return None
    result = {key: int(value) for key, value in values.items() if value.lstrip('-').isdigit()}
    if result.get('last_gap_boottime_ns'):
        result['last_gap_seconds_ago'] = max(0.0, time.clock_gettime(time.CLOCK_BOOTTIME)
                                             - result['last_gap_boottime_ns']/1e9)
    return result


def alsa_streams(card, proc=PROC):
    streams = {}
    for name, direction in (('pcm0p', 'playback'), ('pcm0c', 'capture')):
        sub = proc/'asound'/f'card{card}'/name/'sub0'
        try:
            status, params = (sub/'status').read_text(), (sub/'hw_params').read_text()
        except OSError:
            continue
        if status.strip() == 'closed':
            streams[direction] = {'state': 'closed'}
            continue
        info = key_values(params)
        info['state'] = key_values(status).get('state', 'unknown')
        streams[direction] = {k: info[k] for k in ('state', 'rate', 'period_size', 'buffer_size') if k in info}
    return streams


def rack_node_ids(objects, card_id):
    nodes = {}
    for o in objects:
        props = o.get('info', {}).get('props', {})
        if o.get('type') == 'PipeWire:Interface:Node' and props.get('api.alsa.card.id') == card_id:
            name = props.get('node.name', '')
            nodes[o['id']] = 'playback' if name.startswith('alsa_output.') else 'capture'
    return nodes


def parse_top(text):
    """Rows of the last `pw-top -b` iteration, keyed by node id."""
    rows = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) > 2 and fields[0] == 'S' and fields[1] == 'ID':
            rows = {}
        elif len(fields) >= 9 and fields[1].isdigit():
            # NAME is the last field; followers carry a "+" or "=" marker before it.
            rows[int(fields[1])] = {'quantum': fields[2], 'rate': fields[3], 'wait': fields[4],
                                    'busy': fields[5], 'wait_quantum': fields[6],
                                    'busy_quantum': fields[7], 'errors': int(fields[8]) if fields[8].isdigit() else None,
                                    'name': fields[-1] if len(fields) > 9 else ''}
    return rows


def latency_ms(value):
    """node.latency such as "2048/48000" in milliseconds, or None."""
    match = re.fullmatch(r'\s*(\d+)\s*/\s*(\d+)\s*', str(value or ''))
    return round(int(match[1]) * 1000 / int(match[2]), 1) if match and int(match[2]) else None


def desktop_streams(objects):
    """Playback streams of desktop applications (not JACK clients) and their buffer."""
    streams = []
    for o in objects:
        props = o.get('info', {}).get('props', {})
        if (o.get('type') == 'PipeWire:Interface:Node' and props.get('media.class') == 'Stream/Output/Audio'
                and props.get('client.api') != 'jack'):
            streams.append({'id': o['id'], 'name': props.get('application.name') or props.get('node.name', ''),
                            'latency_ms': latency_ms(props.get('node.latency'))})
    return streams


def pipewire_state(card_id, run=subprocess.run):
    """The Rack nodes, every node with xruns, and desktop playback streams."""
    try:
        objects = json.loads(run(['pw-dump'], capture_output=True, text=True, timeout=3, check=True).stdout)
        top = run(['pw-top', '-b', '-n', '2'], capture_output=True, text=True, timeout=4).stdout
    except (OSError, ValueError, subprocess.SubprocessError):
        return None, None
    rows = parse_top(top)
    rack = {direction: dict(rows.get(node, {}), id=node) for node, direction in rack_node_ids(objects, card_id).items()}
    graph = {'nodes_with_xruns': [{'id': node, 'name': row['name'], 'errors': row['errors']}
                                  for node, row in sorted(rows.items()) if row.get('errors')],
             'desktop_streams': desktop_streams(objects)}
    return rack, graph


def pipewire_nodes(card_id, run=subprocess.run):
    return pipewire_state(card_id, run)[0]


def cpu_list(text):
    cpus = set()
    for part in text.strip().split(','):
        if '-' in part:
            low, high = part.split('-')
            cpus.update(range(int(low), int(high)+1))
        elif part:
            cpus.add(int(part))
    return cpus


def requested_irqs(proc=PROC):
    try:
        lines = (proc/'interrupts').read_text().splitlines()
    except OSError:
        return None
    return {int(line.split(':', 1)[0]) for line in lines if line.split(':', 1)[0].strip().isdigit()}


def device_irqs(device, proc=PROC):
    """Requested IRQ numbers of a PCI device: its MSI vectors, else the legacy line.

    Drivers often allocate more MSI vectors than they request; only requested
    ones appear in /proc/interrupts and can fire.
    """
    found = []
    msi = device/'msi_irqs'
    if msi.is_dir():
        found = sorted(int(p.name) for p in msi.iterdir() if p.name.isdigit())
    if not found:
        try:
            number = int((device/'irq').read_text())
            found = [number] if number > 0 else []
        except (OSError, ValueError):
            return []
    requested = requested_irqs(proc)
    return [n for n in found if requested is None or n in requested]


def irq_cpus(irq, proc=PROC):
    for name in ('effective_affinity_list', 'smp_affinity_list'):
        try:
            return cpu_list((proc/'irq'/str(irq)/name).read_text())
        except (OSError, ValueError):
            continue
    return set()


def usb_controller(location, sys=SYS):
    """The PCI host controller above a USB device location such as 1-9."""
    try:
        path = (sys/'bus/usb/devices'/location).resolve()
    except OSError:
        return None
    pci = [p for p in (path, *path.parents) if re.fullmatch(r'[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]', p.name)]
    return pci[0] if pci else None


def network_irqs(sys=SYS, proc=PROC):
    """Requested IRQs and link state of each physical network interface."""
    found = {}
    for interface in sorted((sys/'class/net').glob('*')):
        device = interface/'device'
        if device.exists():
            irqs = device_irqs(device.resolve(), proc)
            if irqs:
                try:
                    state = (interface/'operstate').read_text().strip()
                except OSError:
                    state = 'unknown'
                found[interface.name] = {'irqs': irqs, 'up': state == 'up'}
    return found


def ksoftirqd(cpu, proc=PROC):
    for entry in proc.glob('[0-9]*'):
        try:
            if (entry/'comm').read_text().strip() == f'ksoftirqd/{cpu}':
                pid = int(entry.name)
                policy = os.sched_getscheduler(pid)
                return {'pid': pid, 'policy': SCHED_NAMES.get(policy, str(policy)),
                        'priority': os.sched_getparam(pid).sched_priority}
        except (OSError, ValueError):
            continue
    return None


SCHED_POLICY = {0: 'normal', 1: 'FIFO', 2: 'RR', 3: 'batch', 5: 'idle', 6: 'deadline'}


def thread_sched(stat_text):
    """(policy, rt_priority) from a /proc/<pid>/task/<tid>/stat line."""
    fields = stat_text.rsplit(')', 1)[1].split()
    # Field 40 is rt_priority and 41 policy; the list after ")" starts at field 3.
    return SCHED_POLICY.get(int(fields[38]), fields[38]), int(fields[37])


def limit(text, name):
    for line in text.splitlines():
        if line.startswith(name):
            value = line[len(name):].split()[0]
            return int(value) if value.isdigit() else value
    return None


def pipewire_realtime(proc=PROC, uid=None):
    """Scheduling of the user's PipeWire audio thread and the limits it got.

    Only the caller's own processes count: display managers such as SDDM run
    their own PipeWire for the login screen.
    """
    uid = os.getuid() if uid is None else uid
    for entry in sorted(proc.glob('[0-9]*'), key=lambda p: int(p.name)):
        try:
            if (entry/'comm').read_text().strip() != 'pipewire':
                continue
            if int(key_values((entry/'status').read_text())['Uid'].split()[0]) != uid:
                continue
            for task in sorted(entry.glob('task/*')):
                if (task/'comm').read_text().strip() == 'data-loop.0':
                    policy, priority = thread_sched((task/'stat').read_text())
                    limits = (entry/'limits').read_text()
                    return {'pid': int(entry.name), 'policy': policy, 'priority': priority,
                            'rtprio_limit': limit(limits, 'Max realtime priority'),
                            'nice_limit': limit(limits, 'Max nice priority')}
        except (OSError, ValueError, KeyError, IndexError):
            continue
    return None


def irq_thread_priorities(proc=PROC):
    """Real-time priority of each threaded interrupt handler, by name (with threadirqs)."""
    found = {}
    for entry in proc.glob('[0-9]*'):
        try:
            name = (entry/'comm').read_text().strip()
            if name.startswith('irq/'):
                found[name] = thread_sched((entry/'stat').read_text())[1]
        except (OSError, ValueError, IndexError):
            continue
    return found


def system_check(location, proc=PROC, sys=SYS):
    """Where USB completions for the Rack run, and what can delay them there."""
    result = {'findings': []}
    controller = usb_controller(location, sys)
    if controller is None:
        result['findings'].append(('info', 'USB controller of the Rack not found.'))
        return result
    irqs = device_irqs(controller, proc)
    cpus = set().union(*(irq_cpus(i, proc) for i in irqs)) if irqs else set()
    result.update(controller=controller.name, irqs=irqs, cpus=sorted(cpus))
    shared = {}
    for name, network in network_irqs(sys, proc).items():
        overlap = sorted(cpus & set().union(*(irq_cpus(i, proc) for i in network['irqs'])))
        if overlap:
            shared[name] = {'cpus': overlap, 'up': network['up']}
    result['shared_with_network'] = shared
    for name, network in shared.items():
        where = ','.join(map(str, network['cpus']))
        if network['up']:
            result['findings'].append(('warn', f'USB controller interrupts share CPU {where} with network '
                                               f'interface {name}. Network receive processing can delay USB '
                                               f'completions; move the USB controller IRQ to another CPU.'))
        else:
            result['findings'].append(('info', f'USB controller interrupts share CPU {where} with network '
                                               f'interface {name}, which has no link now. Once it is connected, '
                                               f'its receive processing can delay USB completions.'))
    threads = {cpu: ksoftirqd(cpu, proc) for cpu in sorted(cpus)}
    result['ksoftirqd'] = threads
    try:
        threaded = 'threadirqs' in (proc/'cmdline').read_text().split()
    except OSError:
        threaded = False
    result['threadirqs'] = threaded
    realtime = pipewire_realtime(proc)
    result['pipewire_realtime'] = realtime
    if realtime and realtime['policy'] not in ('FIFO', 'RR'):
        result['findings'].append(('warn', "PipeWire's audio thread has no real-time priority "
                                           f"({realtime['policy']}), so any busy program can delay audio "
                                           'cycles. Install rtkit, or allow real-time scheduling for your user '
                                           '(the audio group, or realtime-privileges on Arch), and log in again.'))
    elif threaded:
        irq_threads = irq_thread_priorities(proc)
        result['irq_thread_priority'] = max(irq_threads.values(), default=None)
        usb = [p for n, p in irq_threads.items() if any(n.startswith(f'irq/{i}-') for i in irqs)]
        result['usb_irq_thread_priority'] = usb[0] if usb else None
        common = sorted(irq_threads.values())[len(irq_threads)//2] if irq_threads else None
        if realtime and common is not None and realtime['priority'] < common:
            why = (' PipeWire could not lower its nice level (nice limit 0), so it fell back to RTKit;'
                   ' allow it with "@audio - nice -19" in /etc/security/limits.d/ and log in again.'
                   if realtime['nice_limit'] == 0 else '')
            result['findings'].append(('warn', f"PipeWire's audio thread runs at {realtime['policy']} "
                                               f"{realtime['priority']}, below the interrupt threads "
                                               f'({common}). Interrupts from any device can then delay '
                                               f'audio cycles and cause xruns.{why}'))
    normal = [cpu for cpu, t in threads.items() if t and t['policy'] == 'normal']
    if normal and not threaded:
        result['findings'].append(('warn', f'ksoftirqd/{",".join(map(str, normal))} runs at normal priority. '
                                           'Deferred USB completions can then wait behind desktop tasks; give it '
                                           'real-time priority or boot with threadirqs.'))
    if not any(level == 'warn' for level, _ in result['findings']):
        result['findings'].append(('ok', 'No known cause of delayed USB completions found.'))
    return result


DESKTOP_BUFFER_MS = 40


def snapshot(device):
    """All diagnostics for one entry of rack_devices.devices()."""
    rack, graph = pipewire_state(device['card_id'])
    system = system_check(device['location'])
    small = [s for s in (graph or {}).get('desktop_streams', [])
             if s['latency_ms'] is not None and s['latency_ms'] < DESKTOP_BUFFER_MS]
    if small and (os.cpu_count() or 0) <= 4:
        names = ', '.join(sorted({f"{s['name']} ({s['latency_ms']:g} ms)" for s in small}))
        system['findings'].insert(0, ('info', f'Desktop playback streams have small buffers: {names}. On a '
                                              f'{os.cpu_count()}-core CPU a short full load can make them '
                                              'deliver audio late; that is heard as a dropout but is not '
                                              'counted as an xrun. A larger pipewire-pulse buffer helps.'))
    return {'time': time.time(), 'device': device['label'], 'location': device['location'],
            'driver': driver_stats(device['card']),
            'alsa': alsa_streams(device['card']),
            'pipewire': rack, 'graph': graph,
            'system': system}


def log_directory():
    state = os.environ.get('XDG_STATE_HOME') or str(Path.home()/'.local/state')
    return Path(state)/'eleven-rack'


def environment():
    """What a bug report needs to know about the system, read once per log."""
    info = {'kernel': os.uname().release}
    for key, path in (('driver_srcversion', SYS/'module/snd_usb_audio/srcversion'),
                      ('playback_lead_ms', SYS/'module/snd_usb_audio/parameters/eleven_playback_lead_ms'),
                      ('package_version', Path(__file__).resolve().parents[1]/'VERSION'),
                      ('cmdline', PROC/'cmdline')):
        try:
            info[key] = path.read_text().strip()
        except OSError:
            pass
    return info


def watched(data):
    """The values whose change is logged as an event."""
    values = {}
    for key, value in (data.get('driver') or {}).items():
        if key != 'last_gap_seconds_ago':
            values['driver.' + key] = value
    for direction, node in (data.get('pipewire') or {}).items():
        for key in ('errors', 'quantum', 'rate'):
            values[f'pipewire.{direction}.{key}'] = node.get(key)
    for direction, stream in (data.get('alsa') or {}).items():
        for key in ('state', 'rate', 'period_size'):
            values[f'alsa.{direction}.{key}'] = stream.get(key)
    for node in (data.get('graph') or {}).get('nodes_with_xruns', []):
        values[f"graph.{node['name'] or node['id']}.errors"] = node['errors']
    system = data.get('system') or {}
    values['system.irqs'] = system.get('irqs')
    realtime = system.get('pipewire_realtime') or {}
    values['system.pipewire_realtime'] = f"{realtime.get('policy')} {realtime.get('priority')}" if realtime else None
    values['system.cpus'] = system.get('cpus')
    values['system.findings'] = [level + ': ' + text for level, text in system.get('findings', [])]
    return values


def kernel_messages(location, since, until, run=subprocess.run):
    """Kernel log lines about the Rack between two realtime seconds, or None if unreadable."""
    if until <= since:
        # A reading taken just before recording started; journalctl rejects the window.
        return []
    try:
        result = run(['journalctl', '-k', '--no-pager', '-o', 'json', '--since', f'@{since:.6f}',
                      '--until', f'@{until:.6f}'], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode:
        return None
    pattern = re.compile(r'Eleven Rack|usb %s\b|usb %s:' % (re.escape(location), re.escape(location)))
    messages = []
    for line in result.stdout.splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        message = entry.get('MESSAGE')
        if isinstance(message, str) and pattern.search(message):
            messages.append({'time': int(entry['__REALTIME_TIMESTAMP'])/1e6, 'message': message})
    return messages


class Recorder:
    """Append diagnostics to a JSON Lines file: changes as events, periodic snapshots.

    The first line holds the full snapshot and the environment. Afterwards a line
    is written only when a watched value changes, when the Rack's kernel messages
    appear, and every SNAPSHOT_SECONDS, so an idle hour stays small.
    """
    SNAPSHOT_SECONDS = 60

    def __init__(self, path=None, kernel=kernel_messages):
        if path is None:
            path = log_directory()/time.strftime('monitor-%Y%m%d-%H%M%S.jsonl')
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open('a')
        self.kernel = kernel
        self.last = None
        self.last_snapshot = 0.0
        self.kernel_since = time.time()
        self.kernel_note = False
        self.events = 0

    def write(self, record):
        self.stream.write(json.dumps(record, default=str) + '\n')
        self.stream.flush()

    def update(self, data):
        now = data['time']
        values = watched(data)
        if self.last is None:
            self.write({'type': 'start', 'time': now, 'environment': environment(), 'snapshot': data})
            self.last_snapshot = now
        else:
            changes = {key: [self.last.get(key), value] for key, value in values.items()
                       if self.last.get(key) != value}
            if changes:
                self.events += 1
                self.write({'type': 'event', 'time': now, 'device': data['device'], 'changes': changes})
            if now - self.last_snapshot >= self.SNAPSHOT_SECONDS:
                self.write({'type': 'snapshot', 'time': now, 'snapshot': data})
                self.last_snapshot = now
        self.last = values
        messages = self.kernel(data['location'], self.kernel_since, now)
        if messages is None:
            if not self.kernel_note:
                self.write({'type': 'note', 'time': now,
                            'message': 'Kernel log not readable; add the user to the systemd-journal or adm group.'})
                self.kernel_note = True
        else:
            for message in messages:
                self.events += 1
                self.write(dict(message, type='kernel'))
            self.kernel_since = now

    def close(self):
        if self.stream.closed:
            return
        try:
            self.write({'type': 'stop', 'time': time.time()})
        except OSError:
            pass
        finally:
            self.stream.close()


def report(data):
    lines = [f"Eleven Rack diagnostics · {data['device']} · {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(data['time']))}", '']
    stats = data['driver']
    lines.append('Driver')
    if stats is None:
        lines.append('  not available: this driver version has no counters')
    else:
        ago = f"{stats['last_gap_seconds_ago']:.0f} s ago" if 'last_gap_seconds_ago' in stats else 'never'
        lines.append(f"  playback gaps {stats.get('playback_gaps', 0)}  total {stats.get('gap_total_us', 0)} us  "
                     f"last {stats.get('last_gap_us', 0)} us ({ago})")
        lines.append(f"  xruns playback {stats.get('playback_xruns', 0)} capture {stats.get('capture_xruns', 0)}  "
                     f"starts playback {stats.get('playback_starts', 0)} capture {stats.get('capture_starts', 0)}")
        lines.append(f"  capture packet errors {stats.get('capture_packet_errors', 0)}  "
                     f"empty capture URBs {stats.get('capture_empty_urbs', 0)}")
    lines += ['', 'ALSA streams']
    for direction in ('playback', 'capture'):
        s = data['alsa'].get(direction)
        lines.append(f"  {direction:<8} " + (' '.join(f'{k} {v}' for k, v in s.items()) if s else 'not present'))
    lines += ['', 'PipeWire']
    if data['pipewire'] is None:
        lines.append('  not available')
    for direction, node in sorted((data['pipewire'] or {}).items()):
        lines.append(f"  {direction:<8} node {node['id']}  quantum {node.get('quantum', '-')}  rate {node.get('rate', '-')}  "
                     f"wait {node.get('wait', '-')}  busy {node.get('busy', '-')}  xruns {node.get('errors', '-')}")
    graph = data.get('graph') or {}
    if graph.get('nodes_with_xruns'):
        lines.append('  nodes with xruns: ' + ', '.join(f"{n['name'] or n['id']} {n['errors']}"
                                                         for n in graph['nodes_with_xruns']))
    for stream in graph.get('desktop_streams', []):
        lines.append(f"  desktop stream {stream['name']}: buffer {stream['latency_ms']} ms")
    system = data['system']
    lines += ['', 'System']
    if 'controller' in system:
        lines.append(f"  USB controller {system['controller']}  IRQ {','.join(map(str, system['irqs']))} "
                     f"on CPU {','.join(map(str, system['cpus'])) or '?'}  threadirqs {'yes' if system['threadirqs'] else 'no'}")
        for cpu, t in system['ksoftirqd'].items():
            lines.append(f"  ksoftirqd/{cpu}: {t['policy']} {t['priority']}" if t else f'  ksoftirqd/{cpu}: not found')
        realtime = system.get('pipewire_realtime')
        if realtime:
            lines.append(f"  PipeWire audio thread: {realtime['policy']} {realtime['priority']} "
                         f"(limits: rtprio {realtime['rtprio_limit']}, nice {realtime['nice_limit']})")
    for level, text in system['findings']:
        lines.append(f'  [{level}] {text}')
    return '\n'.join(lines)


def main():
    import importlib.util
    spec = importlib.util.spec_from_file_location('rack_devices', Path(__file__).with_name('rack_devices.py'))
    rack_devices = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rack_devices)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', help='Device id, ALSA card id or card number (default: the only Rack)')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--log', nargs='?', const='', metavar='FILE',
                        help='Record until Ctrl+C; default file in ~/.local/state/eleven-rack/')
    parser.add_argument('--interval', type=float, default=2.0, help='Seconds between readings when logging')
    args = parser.parse_args()
    device = rack_devices.select(args.device)
    if args.log is None:
        data = snapshot(device)
        print(json.dumps(data, indent=2) if args.json else report(data))
        return
    recorder = Recorder(args.log or None)
    print(f'Recording {device["label"]} to {recorder.path}; stop with Ctrl+C.', flush=True)
    try:
        while True:
            recorder.update(snapshot(rack_devices.select(device['id'])))
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        recorder.close()
        print(f'{recorder.events} events recorded in {recorder.path}')


if __name__ == '__main__':
    main()

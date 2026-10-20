#!/usr/bin/env python3
"""Read-only Eleven Rack audio diagnostics for the control panel's Monitor window.

Everything here works without root: driver counters and ALSA stream state from
/proc/asound, PipeWire graph timing and xruns from pw-dump/pw-top, and a check
of the CPU placement that decides how quickly USB completions are handled.
Run directly for a text report: python3 eleven_rack_diagnostics.py [--device ID]
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
            rows[int(fields[1])] = {'quantum': fields[2], 'rate': fields[3], 'wait': fields[4],
                                    'busy': fields[5], 'wait_quantum': fields[6],
                                    'busy_quantum': fields[7], 'errors': int(fields[8]) if fields[8].isdigit() else None}
    return rows


def pipewire_nodes(card_id, run=subprocess.run):
    try:
        objects = json.loads(run(['pw-dump'], capture_output=True, text=True, timeout=3, check=True).stdout)
        top = run(['pw-top', '-b', '-n', '2'], capture_output=True, text=True, timeout=4).stdout
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    rows = parse_top(top)
    return {direction: dict(rows.get(node, {}), id=node) for node, direction in rack_node_ids(objects, card_id).items()}


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
    normal = [cpu for cpu, t in threads.items() if t and t['policy'] == 'normal']
    if normal and not threaded:
        result['findings'].append(('warn', f'ksoftirqd/{",".join(map(str, normal))} runs at normal priority. '
                                           'Deferred USB completions can then wait behind desktop tasks; give it '
                                           'real-time priority or boot with threadirqs.'))
    if not any(level == 'warn' for level, _ in result['findings']):
        result['findings'].append(('ok', 'No known cause of delayed USB completions found.'))
    return result


def snapshot(device):
    """All diagnostics for one entry of rack_devices.devices()."""
    return {'time': time.time(), 'device': device['label'],
            'driver': driver_stats(device['card']),
            'alsa': alsa_streams(device['card']),
            'pipewire': pipewire_nodes(device['card_id']),
            'system': system_check(device['location'])}


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
    system = data['system']
    lines += ['', 'System']
    if 'controller' in system:
        lines.append(f"  USB controller {system['controller']}  IRQ {','.join(map(str, system['irqs']))} "
                     f"on CPU {','.join(map(str, system['cpus'])) or '?'}  threadirqs {'yes' if system['threadirqs'] else 'no'}")
        for cpu, t in system['ksoftirqd'].items():
            lines.append(f"  ksoftirqd/{cpu}: {t['policy']} {t['priority']}" if t else f'  ksoftirqd/{cpu}: not found')
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
    args = parser.parse_args()
    device = rack_devices.select(args.device)
    data = snapshot(device)
    print(json.dumps(data, indent=2) if args.json else report(data))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Eleven Rack interface controls through ALSA mixer, PCM, and MIDI."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import hashlib

# Also works when loaded by importlib from the GTK panel.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rack_devices

RATES = (44100, 48000, 88200, 96000)
BUFFERS = (0, 64, 128, 256, 512, 1024, 2048)
def available_buffers(rate):
    return BUFFERS


CLOCKS = {"internal": 1, "aes": 2, "spdif": 3}
RIG_INPUTS = ("guitar", "reamp", "mic", "line-l", "line-r", "line-lr",
              "digital-l", "digital-r", "digital-lr")
INPUTS = ("Guitar In", "Mic In", "Eleven Rig L", "Eleven Rig R", "Digital In L",
          "Digital In R", "Line In L", "Line In R")
OUTPUTS = ("Main Out L", "Main Out R", "Re-Amp L", "Re-Amp R", "Digital Out L", "Digital Out R")



def selected_device():
    return rack_devices.select(os.environ.get('ELEVEN_RACK_DEVICE'))


def card():
    return selected_device()['card']


CLOCK_CONTROL = 'Eleven Rack Clock Source'
MONITOR_CONTROL = 'Eleven Rack Monitoring Mode'
RATE_CONTROL = 'Eleven Rack Sample Rate'


def reported_roundtrip(objects, rate, quantum):
    totals = [0.0, 0.0]
    for prefix, direction in (('alsa_input.', 'Output'), ('alsa_output.', 'Input')):
        nodes=[o for o in objects if o.get('type')=='PipeWire:Interface:Node'
               and o.get('info',{}).get('props',{}).get('api.alsa.card.id')==selected_device()['card_id']
               and o['info']['props'].get('node.name','').startswith(prefix)]
        if len(nodes)!=1 or nodes[0]['info'].get('state')!='running':
            raise ValueError('Audio stream idle')
        entries=[e for e in nodes[0]['info'].get('params',{}).get('Latency',[]) if e.get('direction')==direction]
        if len(entries)!=1: raise ValueError('Latency unavailable')
        e=entries[0]
        # Our ALSA backend reports frames/ns directly, also in Automatic mode.
        # Quantum-dependent values cannot be evaluated without live graph timing.
        if quantum is None and any(float(e[b+'Quantum']) != 0 for b in ('min','max')):
            raise ValueError('Latency requires active graph quantum')
        for i,bound in enumerate(('min','max')):
            totals[i]+=(float(e[bound+'Quantum'])*(quantum or 0)+float(e[bound+'Rate']))*1000/rate+float(e[bound+'Ns'])/1e6
    return totals


def live_quantum(top, node):
    """Quantum the graph is running `node` with, from `pw-top -b` output."""
    rows=[]
    for line in top.splitlines():
        fields=line.split()
        if len(fields)>3 and fields[0]=='S' and fields[2]=='QUANT':
            rows=[]  # Each iteration starts with a header; keep only the last.
        elif len(fields)>3 and fields[1].isdigit() and fields[2].isdigit():
            rows.append((int(fields[2]),line.rstrip().endswith(' '+node) or line.rstrip()==node,
                         ' + ' in line))
    for i,(quantum,match,follower) in enumerate(rows):
        if match:
            # Followers show 0; their driver is the nearest row above that is not one.
            driver=next((q for q,_,f in reversed(rows[:i+1]) if not f),0) if follower else quantum
            return driver or None
    return None


def roundtrip_status(values):
    try:
        quantum=int(values.get('clock.force-quantum','0'))
        rates=set()
        for direction in ('c','p'):
            params=Path('/proc/asound/card%d/pcm0%s/sub0/hw_params' % (card(),direction)).read_text()
            match=re.search(r'^rate:\s+(\d+)',params,re.M)
            if not match: raise ValueError('Audio stream idle')
            rates.add(int(match[1]))
        if len(rates)!=1: raise ValueError('Active graph timing unavailable')
        rate=rates.pop()
        result=subprocess.run(['pw-dump'],capture_output=True,text=True,timeout=3)
        if result.returncode: raise ValueError('PipeWire unavailable')
        objects=json.loads(result.stdout)
        if quantum<=0:
            # Automatic buffer size: use the quantum the Rack is running with now.
            node=next((o['info']['props']['node.name'] for o in objects
                       if o.get('type')=='PipeWire:Interface:Node'
                       and o.get('info',{}).get('props',{}).get('api.alsa.card.id')==selected_device()['card_id']
                       and o['info']['props'].get('node.name','').startswith('alsa_input.')),None)
            top=subprocess.run(['pw-top','-b','-n','2'],capture_output=True,text=True,timeout=4)
            quantum=live_quantum(top.stdout,node) if node and not top.returncode else None
        low,high=reported_roundtrip(objects,rate,quantum)
        if abs(low-high)<.005: return 'Roundtrip latency · %.2f ms' % high
        return 'Roundtrip latency · %.2f–%.2f ms' % (low,high)
    except (OSError,RuntimeError,ValueError,KeyError,subprocess.TimeoutExpired):
        return 'Roundtrip latency unavailable'


def hardware_sample_rate():
    hz = int(mixer_value(RATE_CONTROL))
    if hz <= 0:
        raise RuntimeError('Hardware clock frequency is unavailable.')
    return hz


def monitoring(mode=None):
    modes = {'unknown': 0, 'hardware': 1, 'daw-only': 2, 'software-mix': 3}
    if mode is not None:
        mixer_value(MONITOR_CONTROL, modes[mode])
    value = int(mixer_value(MONITOR_CONTROL))
    actual = next((name for name, index in modes.items() if index == value), None)
    if actual is None:
        raise RuntimeError('Unknown monitoring control value %d.' % value)
    if mode is not None and actual != mode:
        raise RuntimeError('Monitoring command was not accepted; driver reports ' + actual)
    print('Monitoring mode:', actual)
    print('Hardware monitoring state read from the Rack.')


def mixer_value(name, value=None, interface='MIXER'):
    args = ['amixer', '-c', str(card()), 'cget' if value is None else 'cset',
            'iface=' + interface + ',name=' + name]
    if value is not None:
        args.append(str(value))
    result = subprocess.run(args, capture_output=True, text=True, timeout=4)
    if result.returncode:
        raise RuntimeError((result.stderr.strip() or 'ALSA mixer control is unavailable.') +
                           '\nIf this control is missing, reload the updated module.')
    match = re.search(r': values=([^\n]+)', result.stdout)
    if not match:
        raise RuntimeError('ALSA did not return the mixer value.')
    return match.group(1).strip()


def clock_source(source=None):
    if source is not None:
        require_idle()
        mixer_value(CLOCK_CONTROL, CLOCKS[source] - 1)
    value = int(mixer_value(CLOCK_CONTROL)) + 1
    actual = next((key for key, index in CLOCKS.items() if index == value), None)
    if actual is None:
        raise RuntimeError('Unknown ALSA clock selection %d.' % value)
    if source is not None and actual != source:
        raise RuntimeError('Clock selection did not take effect; hardware reports ' + actual)
    print('Clock:', actual)
    if actual == 'internal':
        print('Clock locked: True (internal)')
        return
    try:
        valid = mixer_value('Clock Source %d Validity' % (0x80 + value), interface='CARD')
        print('Clock locked:', valid == 'on' or valid == '1')
    except RuntimeError:
        print('Clock lock status: unavailable')


def require_idle():
    stream = Path('/proc/asound/card%d/stream0' % card())
    if stream.exists() and 'Status: Running' in stream.read_text():
        raise RuntimeError('Stop audio applications before changing clock or rate.')


async def editor_rig_input(name):
    try:
        from websockets.legacy.client import connect
    except ImportError:
        return None
    try:
        socket = await connect('ws://127.0.0.1:57121', open_timeout=1)
    except OSError:
        return None
    try:
        await socket.send(json.dumps({'cmd': 'rig_input_for_device',
                                      'deviceId': selected_device()['id'],
                                      'value': None if name is None else RIG_INPUTS.index(name)}))
        while True:
            event = json.loads(await asyncio.wait_for(socket.recv(), timeout=3))
            if event.get('type') == 'error':
                raise RuntimeError('Editor MIDI bridge: ' + event.get('message', 'request failed') +
                                   '\nRestart the updated editor and retry.')
            if event.get('type') == 'rig_input':
                if not event.get('available'):
                    return None
                value = event.get('value')
                if type(value) is not int or not 0 <= value < len(RIG_INPUTS):
                    raise RuntimeError('Invalid Rig Input reply from the editor bridge.')
                return RIG_INPUTS[value]

    finally:
        await socket.close()


def firmware_cache_path():
    directory = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'eleven-rack'
    try:
        key = hashlib.sha256(selected_device()['id'].encode()).hexdigest()[:20]
    except RuntimeError:
        return directory / 'unselected' / 'firmware.json'
    return directory / 'devices' / key / 'firmware.json'


def cached_firmware_version():
    try:
        value = json.loads(firmware_cache_path().read_text()).get('firmware')
        return value if isinstance(value, str) and 0 < len(value) < 100 else None
    except (OSError, ValueError, AttributeError):
        return None


def firmware_version():
    try:
        version = read_firmware_version()
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired):
        cached = cached_firmware_version()
        if cached:
            return cached + ' (saved)'
        raise
    try:
        path = firmware_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.%d.tmp' % os.getpid())
        temporary.write_text(json.dumps({'firmware': version}) + '\n')
        temporary.replace(path)
    except OSError:
        pass  # A preferences write failure must not hide the live version.
    return version


def read_firmware_version():
    result = subprocess.run(
        ['amidi', '-p', 'hw:%d,0,0' % card(), '-S', 'F0 7E 7F 06 01 F7', '-d', '-t', '1'],
        capture_output=True, text=True, timeout=4)
    if result.returncode:
        raise RuntimeError('Firmware unavailable (device disconnected or MIDI port busy).')
    data = bytes.fromhex(result.stdout)
    for message in data.split(b'\xf0')[1:]:
        message = message.split(b'\xf7', 1)[0]
        if len(message) >= 12 and message[0] == 0x7e and message[2:4] == b'\x06\x02':
            build = message[-4:].decode('ascii', errors='replace')
            if not re.fullmatch(r'[0-9]{4}', build):
                continue
            version = {'0157': '2.0.1', '0153': '2.0'}.get(build)
            return ('%s · Build %s' % (version, '.'.join(build)) if version
                    else 'Build ' + '.'.join(build))
    raise RuntimeError('Firmware unavailable (no identity reply).')


def rig_input(name=None):
    try:
        shared = asyncio.run(editor_rig_input(name))
    except asyncio.TimeoutError:
        raise RuntimeError('Editor MIDI bridge did not confirm Rig Input. Restart the editor and retry.')
    if shared is not None:
        return shared
    # USB-MIDI cable 0 carries editor messages. Do not probe arbitrary object values.
    command = [0xf0, 0x13, 0x0b, 0x0f, 1 if name is None else 0, 0x3d]
    if name is not None:
        command.append(RIG_INPUTS.index(name))
    command.append(0xf7)
    args = ['amidi', '-p', 'hw:%d,0,0' % card(), '-S',
            ' '.join('%02X' % b for b in command)]
    if name is None:
        args += ['-d', '-t', '1']
    result = subprocess.run(args, capture_output=True, text=True, timeout=4)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    if name is not None:
        return rig_input()
    data = bytes.fromhex(result.stdout.strip())
    start = data.find(bytes([0xf0, 0x13, 0x0b, 0x0f, 0x12, 0x3d]))
    if start < 0 or len(data) < start + 8 or data[start + 7] != 0xf7:
        raise RuntimeError('No recognized Rig Input reply (MIDI port may be busy).')
    value = data[start + 6]
    if value >= len(RIG_INPUTS):
        raise RuntimeError('Unknown Rig Input value %d.' % value)
    return RIG_INPUTS[value]


def set_hardware_sample_rate(hz):
    # ALSA owns the USB interfaces and performs the clock SET_CUR itself.
    # Use hw (no resampling) and discard a short capture to configure the rate.
    result = subprocess.run(
        ['arecord', '-D', 'hw:%d,0' % card(), '-f', 'S32_LE', '-r', str(hz),
         '-c', '8', '-d', '1', '-t', 'raw', '/dev/null'],
        capture_output=True, text=True, timeout=8)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'ALSA could not configure the sample rate.')
    if 'rate is not accurate' in result.stderr.lower():
        raise RuntimeError(result.stderr.strip())
    actual = hardware_sample_rate()
    if actual != hz:
        raise RuntimeError('Hardware clock reports %d Hz after requesting %d Hz.' % (actual, hz))


def pipewire_settings():
    result = subprocess.run(['pw-metadata', '-n', 'settings'],
                            capture_output=True, text=True, timeout=4)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'PipeWire settings unavailable.')
    return dict(re.findall(r"key:'([^']+)' value:'([^']+)'", result.stdout))


def set_pipewire_setting(key, value):
    result = subprocess.run(['pw-metadata', '-n', 'settings', '0', key, str(value)],
                            capture_output=True, text=True, timeout=4)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'PipeWire sample rate change failed.')


def set_sample_rate(hz):
    require_idle()
    previous = pipewire_settings()
    keys = ('clock.allowed-rates', 'clock.rate', 'clock.force-rate', 'clock.force-quantum')
    if any(key not in previous for key in keys):
        raise RuntimeError('PipeWire sample rate settings unavailable.')
    previous_hardware = hardware_sample_rate()
    set_hardware_sample_rate(hz)
    try:
        set_pipewire_setting('clock.allowed-rates', '[ 44100 48000 88200 96000 ]')
        set_pipewire_setting('clock.rate', hz)
        set_pipewire_setting('clock.force-rate', hz)
        quantum = int(previous['clock.force-quantum'])
        actual = pipewire_settings()
        expected_quantum = quantum
        if actual.get('clock.force-quantum') != str(expected_quantum):
            raise RuntimeError('PipeWire buffer change was not confirmed.')
        if actual.get('clock.rate') != str(hz) or actual.get('clock.force-rate') != str(hz):
            raise RuntimeError('PipeWire sample rate change was not confirmed.')
    except Exception as error:
        rollback_errors = []
        for key in keys:
            try:
                set_pipewire_setting(key, previous[key])
            except Exception as rollback:
                rollback_errors.append(str(rollback))
        try:
            set_hardware_sample_rate(previous_hardware)
        except Exception as rollback:
            rollback_errors.append(str(rollback))
        if rollback_errors:
            raise RuntimeError(str(error) + '\nRestore failed: ' + '; '.join(rollback_errors)) from error
        raise
    print('Internal clock rate:', hz, 'Hz')
    print('PipeWire session rate:', hz, 'Hz')
    print('Buffer size:', actual['clock.force-quantum'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', help='USB identity, ALSA card ID or card number; required with multiple Racks')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('devices')
    commands.add_parser('channels')
    commands.add_parser('status')
    commands.add_parser('firmware')
    commands.add_parser('gui')
    buffer = commands.add_parser('buffer'); buffer.add_argument('samples', nargs='?', type=int, choices=BUFFERS)
    clock = commands.add_parser('clock'); clock.add_argument('source', choices=CLOCKS)
    rate = commands.add_parser('rate'); rate.add_argument('hz', nargs='?', type=int, choices=RATES)
    rig = commands.add_parser('rig-input'); rig.add_argument('source', nargs='?', choices=RIG_INPUTS)
    monitor = commands.add_parser('monitor'); monitor.add_argument('mode', nargs='?', choices=('hardware', 'daw-only'))
    args = parser.parse_args()
    if args.device:
        os.environ['ELEVEN_RACK_DEVICE'] = rack_devices.select(args.device)['id']
    if args.command == 'devices':
        print(json.dumps(rack_devices.devices(), indent=2))
    elif args.command == 'gui':
        subprocess.run([sys.executable, str(Path(__file__).with_name('eleven-rack-panel.py'))], check=True)
    elif args.command == 'firmware':
        print('Firmware:', firmware_version())
    elif args.command == 'channels':
        for i, name in enumerate(INPUTS):
            print('%d  %-16s %s' % (i + 1, name, OUTPUTS[i] if i < len(OUTPUTS) else ''))
    elif args.command == 'rig-input':
        print('Rig Input:', rig_input(args.source))
    elif args.command == 'monitor':
        monitoring(args.mode)
    elif args.command == 'rate':
        if args.hz is None:
            print('Hardware sample rate:', hardware_sample_rate(), 'Hz')
        else:
            set_sample_rate(args.hz)
    elif args.command == 'clock':
        clock_source(args.source)
    elif args.command == 'status':
        clock_source()
        print('Hardware sample rate:', hardware_sample_rate(), 'Hz')
    elif args.command == 'buffer':
        if args.samples is not None:
            rate_hz = hardware_sample_rate()
            if args.samples not in available_buffers(rate_hz):
                raise RuntimeError('Unsupported buffer size.')
            result = subprocess.run(['pw-metadata', '-n', 'settings', '0', 'clock.force-quantum', str(args.samples)],
                                    capture_output=True, text=True, timeout=4)
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or 'PipeWire buffer change failed.')
        result = subprocess.run(['pw-metadata', '-n', 'settings'], capture_output=True, text=True, timeout=4)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or 'PipeWire settings unavailable.')
        values = dict(re.findall(r"key:'([^']+)' value:'([^']+)'", result.stdout))
        if 'clock.force-quantum' not in values:
            raise RuntimeError('PipeWire buffer setting unavailable.')
        forced = int(values['clock.force-quantum'])
        if args.samples is not None and forced != args.samples:
            raise RuntimeError('PipeWire buffer change was not confirmed.')
        effective = forced or int(values.get('clock.quantum', '0'))
        rate = int(values.get('clock.rate', '48000'))
        print('Buffer size:', forced)
        print('Roundtrip latency:', roundtrip_status(values))


if __name__ == '__main__':
    try:
        main()
    except PermissionError:
        sys.exit('ALSA device access denied. Check your audio device permissions.')
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as e:
        sys.exit(str(e))

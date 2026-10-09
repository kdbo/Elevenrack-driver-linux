#!/usr/bin/env python3
"""Eleven Rack interface controls through ALSA mixer, PCM, and MIDI."""
import argparse
import asyncio
import json
from pathlib import Path
import re
import subprocess
import sys

RATES = (44100, 48000, 88200, 96000)
BUFFERS = (0, 64, 128, 256, 512, 1024, 2048)
CLOCKS = {"internal": 1, "aes": 2, "spdif": 3}
RIG_INPUTS = ("guitar", "reamp", "mic", "line-l", "line-r", "line-lr",
              "digital-l", "digital-r", "digital-lr")
INPUTS = ("Guitar In", "Mic In", "Eleven Rig L", "Eleven Rig R", "Line In L",
          "Line In R", "Digital In L", "Digital In R")
OUTPUTS = ("Main Out L", "Main Out R", "Re-Amp L", "Re-Amp R", "Digital Out L", "Digital Out R")



def card():
    for p in Path('/proc/asound').glob('card*/usbid'):
        if p.read_text().strip().lower() == '0dba:b011':
            return int(p.parent.name[4:])
    raise RuntimeError('Eleven Rack is not registered with ALSA.')


CLOCK_CONTROL = 'Eleven Rack Clock Source'


def mixer_value(name, value=None, interface='MIXER'):
    args = ['amixer', '-c', str(card()), 'cget' if value is None else 'cset',
            'iface=' + interface + ',name=' + name]
    if value is not None:
        args.append(str(value))
    result = subprocess.run(args, capture_output=True, text=True, timeout=4)
    if result.returncode:
        raise RuntimeError((result.stderr.strip() or 'ALSA mixer control is unavailable.') +
                           '\nIf the clock control is missing, reload the updated module.')
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
        await socket.send(json.dumps({'cmd': 'rig_input',
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


def set_sample_rate(hz):
    require_idle()
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
    print('Internal clock rate:', hz, 'Hz')
    print('Audio apps select their own rate when opening the device.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('channels')
    commands.add_parser('status')
    commands.add_parser('gui')
    buffer = commands.add_parser('buffer'); buffer.add_argument('samples', nargs='?', type=int, choices=BUFFERS)
    clock = commands.add_parser('clock'); clock.add_argument('source', choices=CLOCKS)
    rate = commands.add_parser('rate'); rate.add_argument('hz', type=int, choices=RATES)
    rig = commands.add_parser('rig-input'); rig.add_argument('source', nargs='?', choices=RIG_INPUTS)
    args = parser.parse_args()
    if args.command == 'gui':
        subprocess.run([sys.executable, str(Path(__file__).with_name('eleven-rack-panel.py'))], check=True)
    elif args.command == 'channels':
        for i, name in enumerate(INPUTS):
            print('%d  %-16s %s' % (i + 1, name, OUTPUTS[i] if i < len(OUTPUTS) else ''))
    elif args.command == 'rig-input':
        print('Rig Input:', rig_input(args.source))
    elif args.command == 'rate':
        set_sample_rate(args.hz)
    elif args.command == 'clock':
        clock_source(args.source)
    elif args.command == 'status':
        clock_source()
    elif args.command == 'buffer':
        if args.samples is not None:
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
        print('Buffer duration: %g ms per buffer at %g kHz%s' %
              (effective * 1000 / rate, rate / 1000, ' (automatic)' if not forced else ''))


if __name__ == '__main__':
    try:
        main()
    except PermissionError:
        sys.exit('ALSA device access denied. Check your audio device permissions.')
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as e:
        sys.exit(str(e))

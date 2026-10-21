#!/usr/bin/env python3
"""Collect an Eleven Rack installation report inside a test VM or on any machine.

Runs without root. Records the distribution, kernel, package versions, DKMS
state, the loaded snd-usb-audio module, the Rack's audio devices and driver
counters, PipeWire and its real-time scheduling, the Monitor's diagnostics and
the Rack's kernel messages. With --audio-check it also plays a short tone on
Main Out through PipeWire and records Line In at the same time; with a Main
Out L -> Line In L cable this shows that playback and capture both work.
VM timing is not representative: this checks function, not latency.

    python3 vm-guest-report.py [--audio-check] [--output FILE]
"""
import argparse
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import tempfile
import time

TOOLS = Path('/usr/lib/eleven-rack/tools')


def run(*command, timeout=20, limit=20000):
    """Run a command; keep the last `limit` characters of output for the report.

    JSON output must not be cut: pass limit=None for it.
    """
    if not shutil.which(command[0]):
        return {'missing': command[0]}
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as error:
        return {'error': str(error)}
    stdout = result.stdout.strip()
    return {'exit': result.returncode, 'stdout': stdout if limit is None else stdout[-limit:],
            'stderr': result.stderr.strip()[-4000:]}


def read(path):
    try:
        return Path(path).read_text(errors='replace').strip()
    except OSError:
        return None


def os_release():
    values = {}
    for line in (read('/etc/os-release') or '').splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            values[key] = value.strip('"')
    return {k: values.get(k) for k in ('NAME', 'VERSION_ID', 'PRETTY_NAME', 'ID')}


def packages():
    names = ('eleven-rack-driver', 'eleven-rack-editor-linux', 'pipewire', 'wireplumber', 'kernel', 'linux')
    if shutil.which('dpkg-query'):
        return run('dpkg-query', '-W', '-f', '${Package} ${Version} ${Status}\n', *names, 'linux-image-' + platform.release())
    if shutil.which('rpm'):
        return run('rpm', '-q', *names, 'kernel-devel')
    if shutil.which('pacman'):
        return run('pacman', '-Q', 'eleven-rack-driver', 'eleven-rack-editor-linux', 'pipewire', 'wireplumber', 'linux', 'linux-headers')
    return {'missing': 'package manager'}


def rack_cards():
    cards = []
    for usbid in sorted(Path('/proc/asound').glob('card*/usbid')):
        if (read(usbid) or '').lower() == '0dba:b011':
            card = usbid.parent
            cards.append({'card': card.name, 'id': read(card/'id'),
                          'eleven_stats': read(card/'eleven_stats'),
                          'stream0': read(card/'stream0'),
                          'playback_status': read(card/'pcm0p/sub0/status'),
                          'capture_status': read(card/'pcm0c/sub0/status')})
    return cards


def module():
    loaded = Path('/sys/module/snd_usb_audio')
    return {'path': run('modinfo', '-n', 'snd_usb_audio').get('stdout'),
            'vermagic': run('modinfo', '-F', 'vermagic', 'snd_usb_audio').get('stdout'),
            'loaded_srcversion': read(loaded/'srcversion'),
            'parameters': {p.name: read(p) for p in sorted(loaded.glob('parameters/*'))}}


def diagnostics():
    script = TOOLS/'eleven_rack_diagnostics.py'
    if not script.exists():
        return {'missing': str(script)}
    result = run('python3', str(script), '--json', timeout=30, limit=None)
    try:
        return json.loads(result.get('stdout', ''))
    except ValueError:
        return result


def tone(path, seconds=3, rate=48000):
    """Stereo 997 Hz at -20 dBFS as raw S16LE, for pw-play."""
    frames = []
    for i in range(int(seconds*rate)):
        value = int(0.1*32767*math.sin(2*math.pi*997*i/rate))
        frames.append(struct.pack('<hh', value, value))
    Path(path).write_bytes(b''.join(frames))


def rms(path, channels=2):
    """Highest per-channel RMS (0..1) of interleaved S16LE."""
    data = Path(path).read_bytes()
    samples = struct.unpack('<%dh' % (len(data)//2), data[:len(data)//2*2])
    levels = []
    for channel in range(channels):
        own = samples[channel::channels]
        levels.append(math.sqrt(sum(s*s for s in own)/len(own))/32768 if own else 0.0)
    return max(levels)


def audio_check():
    """Play a tone on the Rack's Main Out and record its Line In L/R meanwhile."""
    dump = run('pw-dump', timeout=10, limit=None)
    try:
        objects = json.loads(dump.get('stdout') or '[]')
    except ValueError:
        return {'error': 'pw-dump unreadable'}
    nodes = {}
    for o in objects:
        props = o.get('info', {}).get('props', {})
        name = props.get('node.name', '')
        if o.get('type') == 'PipeWire:Interface:Node' and 'Eleven_Rack' in name:
            nodes['sink' if name.startswith('alsa_output.') else 'source'] = name
    if len(nodes) != 2:
        return {'error': 'Rack PipeWire nodes not found', 'nodes': nodes}
    with tempfile.TemporaryDirectory() as tmp:
        played, recorded = Path(tmp)/'tone.raw', Path(tmp)/'line-in.raw'
        tone(played)
        # Line In L/R are capture channels 7 and 8 (AUX6, AUX7). pw-record rejects a
        # one-channel map, and without dont-remix PipeWire may mix all channels.
        recorder = subprocess.Popen(['pw-record', '--raw', '--format', 's16', '--rate', '48000', '--channels', '2',
                                     '--channel-map', 'AUX6,AUX7', '-P', '{ stream.dont-remix = true }',
                                     '--target', nodes['source'], str(recorded)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        time.sleep(1)
        silence = rms(recorded) if recorded.exists() else None
        player = run('pw-play', '--raw', '--format', 's16', '--rate', '48000', '--channels', '2',
                     '--channel-map', 'AUX0,AUX1', '-P', '{ stream.dont-remix = true }',
                     '--target', nodes['sink'], str(played), timeout=15)
        time.sleep(0.5)
        recorder.terminate()
        try:
            recorder.wait(timeout=5)
        except subprocess.TimeoutExpired:
            recorder.kill()
        record_error = recorder.stderr.read().strip()[-2000:] if recorder.stderr else ''
        level = rms(recorded) if recorded.exists() else None
    return {'nodes': nodes, 'play_exit': player.get('exit'), 'play_error': player.get('stderr'),
            'record_exit': recorder.returncode, 'record_error': record_error,
            'line_in_rms_total': level, 'line_in_rms_before_tone': silence,
            'signal_detected': level is not None and level > 0.005,
            'note': 'signal_detected needs a Main Out -> Line In cable; without it only playback is checked'}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--audio-check', action='store_true', help='Play a 3 s tone and record Line In L/R')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    host = platform.node()
    output = args.output or Path.home()/f"eleven-rack-report-{os_release().get('ID', 'linux')}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    uid = os.getuid()
    rt = run('ps', '-u', str(uid), '-L', '-o', 'pid,cls,rtprio,comm')
    report = {
        'time': time.strftime('%Y-%m-%d %H:%M:%S %z'), 'host': host, 'os': os_release(),
        'kernel': platform.release(), 'cmdline': read('/proc/cmdline'),
        'virtualization': run('systemd-detect-virt').get('stdout'),
        'packages': packages(), 'dkms': run('dkms', 'status'), 'module': module(),
        'usb': run('lsusb', '-d', '0dba:b011'),
        'aplay': run('aplay', '-l'), 'arecord': run('arecord', '-l'), 'racks': rack_cards(),
        'pipewire_version': run('pipewire', '--version').get('stdout'),
        'pipewire_threads': [line for line in (rt.get('stdout') or '').splitlines()
                             if re.search(r'data-loop|pipewire|wireplumber', line)],
        'pipewire_limits': read(f"/proc/{run('pgrep', '-u', str(uid), '-x', 'pipewire').get('stdout', '').split()[0]}/limits")
                           if run('pgrep', '-u', str(uid), '-x', 'pipewire').get('stdout') else None,
        'diagnostics': diagnostics(),
        'kernel_messages': run('journalctl', '-k', '-b', '--no-pager', '-g', r'0dba|Eleven Rack|snd.usb|usb 1-|dkms|module verification'),
        'audio_check': audio_check() if args.audio_check else None,
    }
    output.write_text(json.dumps(report, indent=2, default=str) + '\n')
    racks = report['racks']
    print(f"Report: {output}")
    print(f"  {report['os'].get('PRETTY_NAME')} · kernel {report['kernel']} · {report['virtualization'] or 'native'}")
    # Kernels without CONFIG_MODULE_SRCVERSION_ALL (Fedora) have no srcversion for
    # loaded modules; the counters file then shows the patched driver is loaded.
    loaded = report['module']['loaded_srcversion'] or (
        'not loaded' if not Path('/sys/module/snd_usb_audio').exists() else 'not provided by this kernel')
    print(f"  module {report['module']['path']} (srcversion {loaded})")
    print(f"  Racks: {', '.join(r['id'] or r['card'] for r in racks) or 'none'}; counters: "
          f"{'yes' if racks and racks[0]['eleven_stats'] else 'no'}")
    if report['audio_check']:
        check = report['audio_check']
        if check.get('error'):
            print(f"  audio check: {check['error']}")
        elif check['line_in_rms_total'] is None:
            print(f"  audio check: recording failed: {check.get('record_error') or 'no data'}")
        else:
            print(f"  audio check: {'signal on Line In' if check['signal_detected'] else 'played; no signal on Line In (cable?)'}"
                  f" (level {check['line_in_rms_total']:.4f}, before tone {check['line_in_rms_before_tone'] or 0:.4f})")


if __name__ == '__main__':
    main()

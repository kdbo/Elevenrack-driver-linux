#!/usr/bin/env python3
"""Back up E1 with read-only MIDI queries before a controlled upload test."""
import asyncio
import hashlib
import json
import importlib.util
from pathlib import Path
import sys
import time
import rtmidi

ROOT = Path(__file__).resolve().parent.parent
SLOT = 16  # E1: four rigs per letter, zero-based.


async def main():
    loop = asyncio.get_running_loop()
    incoming = asyncio.Queue()
    midi_in = rtmidi.MidiIn(rtmidi.API_LINUX_ALSA, 'E1 Backup Input')
    midi_out = rtmidi.MidiOut(rtmidi.API_LINUX_ALSA, 'E1 Backup Output')
    selected = []
    for midi in (midi_in, midi_out):
        ports = midi.get_ports()
        candidates = [(i, name) for i, name in enumerate(ports)
                      if name.lower().startswith('eleven rack:') and 'external' not in name.lower()]
        if len(candidates) != 1:
            raise RuntimeError('Ambiguous Rack rig MIDI port: ' + repr(ports))
        selected.append(candidates[0])
    directory = ROOT / 'build/editor-rig-tests' / time.strftime('E1-%Y%m%d-%H%M%S')
    directory.mkdir(parents=True, exist_ok=False)
    midi_in.ignore_types(sysex=False, timing=True, active_sense=True)
    midi_in.set_callback(lambda event, _: loop.call_soon_threadsafe(incoming.put_nowait, bytes(event[0])))
    restore_needed = False
    try:
        midi_in.open_port(selected[0][0])
        midi_out.open_port(selected[1][0])
        replies = []
        for attempt in range(2):
            midi_out.send_message([240, 19, 11, 15, 1, 0, SLOT, 247])
            deadline = loop.time() + 8
            while True:
                reply = await asyncio.wait_for(incoming.get(), max(0, deadline - loop.time()))
                if reply[:7] == bytes([240, 19, 11, 15, 18, 0, SLOT]) and reply[-1] == 247:
                    (directory / ('E1-read-%d.syx' % (attempt + 1))).write_bytes(reply)
                    replies.append(reply)
                    break
        if replies[0] != replies[1]:
            raise RuntimeError('E1 reads differ; saved both captures, no upload attempted')
        upload = bytearray(replies[0])
        upload[4] = 0
        (directory / 'E1-original-upload.syx').write_bytes(upload)
        report = {'slot': 'E1', 'slot_index': SLOT, 'backup_directory': str(directory),
                  'sysex_bytes': len(upload), 'encoded_payload_bytes': len(upload) - 8,
                  'backup_sha256': hashlib.sha256(upload).hexdigest(),
                  'two_reads_match': True, 'hardware_writes': 0,
                  'matches_required_1692_sysex_bytes': len(upload) == 1692,
                  'ports': [p[1] for p in selected]}
        if '--old-upload' in sys.argv:
            spec = importlib.util.spec_from_file_location('tested_bridge', ROOT / 'editor/bridge-linux/bridge.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            bridge = module.Bridge.__new__(module.Bridge)
            owner = object()
            bridge.owner, bridge.output = owner, midi_out
            original_upload = bytes(upload)
            if '--changed-test' in sys.argv:
                source_replies = []
                for attempt in range(2):
                    midi_out.send_message([240, 19, 11, 15, 1, 0, SLOT + 1, 247])
                    deadline = loop.time() + 8
                    while True:
                        reply = await asyncio.wait_for(incoming.get(), max(0, deadline - loop.time()))
                        if reply[:7] == bytes([240, 19, 11, 15, 18, 0, SLOT + 1]) and reply[-1] == 247:
                            (directory / ('E2-source-%d.syx' % (attempt + 1))).write_bytes(reply)
                            source_replies.append(reply)
                            break
                if source_replies[0] != source_replies[1]:
                    raise RuntimeError('E2 source reads differ; no upload attempted')
                upload = bytearray(source_replies[0])
                upload[4], upload[6] = 0, SLOT
                if upload == original_upload:
                    raise RuntimeError('E2 is identical to E1; no changed-rig test attempted')
                (directory / 'E1-temporary-upload.syx').write_bytes(upload)
                report['temporary_source'] = 'Unmodified E2 rig; destination changed to E1'
                report['temporary_upload_bytes'] = len(upload)
            restore_needed = '--changed-test' in sys.argv
            await bridge.command(owner, {'cmd': 'send', 'hex': upload.hex()})
            report['hardware_writes'] = 1
            report['route'] = 'Original Bridge.command -> RtMidi.send_message, entire SysEx'
            observed = []
            deadline = loop.time() + 3
            while loop.time() < deadline:
                try:
                    reply = await asyncio.wait_for(incoming.get(), max(0, deadline - loop.time()))
                except asyncio.TimeoutError:
                    break
                observed.append(reply.hex(' '))
            report['dialogs'] = [message for message in observed
                                if bytes.fromhex(message)[:4] == bytes([240, 19, 11, 15])
                                and len(bytes.fromhex(message)) > 5 and bytes.fromhex(message)[5] == 0x78]
            report['bad_patch_data'] = any('badpatchdata' in ''.join(
                chr(b) for b in bytes.fromhex(message)[6:-1] if 32 <= b <= 126
            ).lower().replace(' ', '') for message in report['dialogs'])
            (directory / 'upload-replies.json').write_text(json.dumps(observed, indent=2) + '\n')
            after = []
            for attempt in range(2):
                midi_out.send_message([240, 19, 11, 15, 1, 0, SLOT, 247])
                deadline = loop.time() + 8
                while True:
                    reply = await asyncio.wait_for(incoming.get(), max(0, deadline - loop.time()))
                    if reply[:7] == bytes([240, 19, 11, 15, 18, 0, SLOT]) and reply[-1] == 247:
                        (directory / ('E1-after-%d.syx' % (attempt + 1))).write_bytes(reply)
                        after.append(reply)
                        break
            if '--changed-test' in sys.argv:
                expected = bytearray(upload)
                expected[4] = 18
                report['temporary_change_persisted'] = all(reply == expected for reply in after)
                await bridge.command(owner, {'cmd': 'send', 'hex': original_upload.hex()})
                report['hardware_writes'] += 1
                await asyncio.sleep(3)
                restored = []
                for attempt in range(2):
                    midi_out.send_message([240, 19, 11, 15, 1, 0, SLOT, 247])
                    deadline = loop.time() + 8
                    while True:
                        reply = await asyncio.wait_for(incoming.get(), max(0, deadline - loop.time()))
                        if reply[:7] == bytes([240, 19, 11, 15, 18, 0, SLOT]) and reply[-1] == 247:
                            (directory / ('E1-restored-%d.syx' % (attempt + 1))).write_bytes(reply)
                            restored.append(reply)
                            break
                after = restored
                restore_needed = not all(reply == replies[0] for reply in restored)
            report['readback_identical_to_backup'] = all(reply == replies[0] for reply in after)
            report['test_passed'] = (not report['bad_patch_data'] and report['readback_identical_to_backup']
                                     and report.get('temporary_change_persisted', True))
            report['test_scope'] = ('Unmodified E2 rig written to E1, exact readback, original E1 restored'
                                    if '--changed-test' in sys.argv else
                                    'Rewrite identical original rig; does not prove a changed rig persists')
        (directory / 'backup.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2), flush=True)
    finally:
        if restore_needed:
            midi_out.send_message(list(original_upload))
            print('Original E1 re-sent during cleanup; verify readback before further testing.', flush=True)
        midi_in.cancel_callback()
        midi_in.close_port()
        midi_out.close_port()


if __name__ == '__main__':
    asyncio.run(main())

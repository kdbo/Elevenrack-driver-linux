#!/usr/bin/env python3
"""Verify native ALSA spans on a private virtual port; never target hardware."""
import ctypes as C
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parents[1]))
from segmented_sysex import AlsaSpanSender, Event, rig_segments

alsa = C.CDLL('libasound.so.2')
for name, args in {
    'snd_seq_open': [C.POINTER(C.c_void_p), C.c_char_p, C.c_int, C.c_int],
    'snd_seq_close': [C.c_void_p],
    'snd_seq_client_id': [C.c_void_p],
    'snd_seq_create_simple_port': [C.c_void_p, C.c_char_p, C.c_uint, C.c_uint],
    'snd_seq_event_input': [C.c_void_p, C.POINTER(C.POINTER(Event))],
    'snd_seq_free_event': [C.POINTER(Event)],
}.items():
    fn = getattr(alsa, name)
    fn.argtypes, fn.restype = args, C.c_int
handle = C.c_void_p()
sender = None
try:
    AlsaSpanSender.check(alsa.snd_seq_open(C.byref(handle), b'default', 2, 0))
    client = AlsaSpanSender.check(alsa.snd_seq_client_id(handle))
    port = AlsaSpanSender.check(alsa.snd_seq_create_simple_port(handle, b'PRIVATE TEST RECEIVER', 2, 1 << 20))
    sender = AlsaSpanSender('%d:%d' % (client, port))
    data = bytes([240, 19, 11, 15, 0, 1] + [i % 128 for i in range(1685)] + [247])
    received = []
    for span in rig_segments(data):
        sender.send(span)
        event = C.POINTER(Event)()
        AlsaSpanSender.check(alsa.snd_seq_event_input(handle, C.byref(event)))
        assert event.contents.type == 130
        received.append(C.string_at(event.contents.data.external.pointer, event.contents.data.external.length))
        alsa.snd_seq_free_event(event)
    assert [len(s) for s in received] == [512, 512, 512, 156]
    assert b''.join(received) == data
    print(json.dumps({'destination': 'private virtual ALSA port',
                      'segments': list(map(len, received)), 'bytes_preserved': True,
                      'hardware_writes': 0, 'alsa_event_size': C.sizeof(Event)}))
finally:
    if sender is not None: sender.close()
    if handle: alsa.snd_seq_close(handle)

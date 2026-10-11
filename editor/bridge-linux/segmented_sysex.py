# SPDX-License-Identifier: MIT
"""Send SysEx spans as native ALSA events, bypassing RtMidi's MIDI encoder."""
import ctypes as C
import re

RIG_SEGMENTS = (512, 512, 512, 156)


def rig_segments(data):
    if len(data) != sum(RIG_SEGMENTS):
        raise ValueError('Rig upload requires exactly 1692 SysEx bytes; got %d. Nothing sent.' % len(data))
    offset = 0
    parts = []
    for size in RIG_SEGMENTS:
        parts.append(bytes(data[offset:offset + size]))
        offset += size
    return parts


class Address(C.Structure):
    _fields_ = [('client', C.c_ubyte), ('port', C.c_ubyte)]


class External(C.Structure):
    _pack_ = 1
    _fields_ = [('length', C.c_uint), ('pointer', C.c_void_p)]


class Data(C.Union):
    _fields_ = [('external', External), ('raw', C.c_uint * 3)]


class Event(C.Structure):
    _fields_ = [('type', C.c_ubyte), ('flags', C.c_ubyte), ('tag', C.c_ubyte),
                ('queue', C.c_ubyte), ('time', C.c_uint * 2),
                ('source', Address), ('dest', Address), ('data', Data)]


class AlsaSpanSender:
    def __init__(self, port_name):
        match = re.search(r'(\d+):(\d+)\s*$', port_name)
        if not match or any(int(v) > 255 for v in match.groups()):
            raise ValueError('Cannot resolve ALSA destination for segmented rig upload')
        self.destination = Address(*map(int, match.groups()))
        self.alsa = C.CDLL('libasound.so.2')
        signatures = {
            'snd_seq_open': [C.POINTER(C.c_void_p), C.c_char_p, C.c_int, C.c_int],
            'snd_seq_close': [C.c_void_p],
            'snd_seq_set_client_name': [C.c_void_p, C.c_char_p],
            'snd_seq_create_simple_port': [C.c_void_p, C.c_char_p, C.c_uint, C.c_uint],
            'snd_seq_client_id': [C.c_void_p],
            'snd_seq_event_output_direct': [C.c_void_p, C.POINTER(Event)],
        }
        for name, args in signatures.items():
            fn = getattr(self.alsa, name)
            fn.argtypes, fn.restype = args, C.c_int
        self.handle = C.c_void_p()
        self.check(self.alsa.snd_seq_open(C.byref(self.handle), b'default', 1, 0))
        try:
            self.check(self.alsa.snd_seq_set_client_name(self.handle, b'Eleven Rack Rig Upload'))
            self.port = self.check(self.alsa.snd_seq_create_simple_port(
                self.handle, b'Segmented SysEx', 1, 1 << 20))
            self.client = self.check(self.alsa.snd_seq_client_id(self.handle))
        except Exception:
            self.close()
            raise

    @staticmethod
    def check(result):
        if result < 0:
            raise OSError(-result, 'ALSA segmented SysEx send failed')
        return result

    def send(self, span):
        buffer = C.create_string_buffer(span)
        event = Event(type=130, flags=4, queue=253,
                      source=Address(self.client, self.port), dest=self.destination)
        event.data.external = External(len(span), C.cast(buffer, C.c_void_p))
        self.check(self.alsa.snd_seq_event_output_direct(self.handle, C.byref(event)))

    def close(self):
        if self.handle:
            self.alsa.snd_seq_close(self.handle)
            self.handle = C.c_void_p()

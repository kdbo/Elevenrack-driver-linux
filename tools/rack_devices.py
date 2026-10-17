"""Eleven Rack discovery shared by the control panel and Linux MIDI bridge."""
import ctypes
from pathlib import Path
import re


def display_name(card_id):
    if card_id == 'Rack':
        return 'Eleven Rack 1'
    match = re.fullmatch(r'Rack_(\d+)', card_id)
    return 'Eleven Rack %d' % (int(match[1]) + 1) if match else 'Eleven Rack (' + card_id + ')'


def devices(proc=Path('/proc/asound'), sound=Path('/sys/class/sound')):
    found = []
    for entry in sorted(proc.glob('card*/usbid')):
        try:
            if entry.read_text().strip().lower() != '0dba:b011':
                continue
            number = int(entry.parent.name[4:])
            interface = (sound / ('card%d' % number) / 'device').resolve()
            usb = next((p for p in (interface, *interface.parents)
                        if (p / 'idVendor').exists() and (p / 'idProduct').exists()), None)
            serial = (usb / 'serial').read_text().strip() if usb and (usb / 'serial').exists() else ''
            # Some Racks report the same USB serial. Physical USB location is
            # deliberately used even when a serial exists: no ambiguous fallback.
            identity = 'usb:' + str(usb) if usb else 'alsa:' + entry.parent.name
            card_id = (entry.parent / 'id').read_text().strip()
            location = usb.name if usb else entry.parent.name
            found.append({'id': identity, 'card': number, 'card_id': card_id,
                          'serial': serial, 'location': location,
                          'label': '%s · USB %s' % (display_name(card_id), location),
                          'name': display_name(card_id)})
        except (OSError, ValueError):
            continue
    return sorted(found, key=lambda d: d['card'])


def select(selector=None):
    found = devices()
    if selector:
        matches = [d for d in found if selector in (d['id'], d['card_id'], str(d['card']))]
        if len(matches) == 1:
            return matches[0]
        raise RuntimeError('Selected Eleven Rack is disconnected or ambiguous: ' + selector)
    if len(found) == 1:
        return found[0]
    if not found:
        raise RuntimeError('Eleven Rack is not registered with ALSA.')
    raise RuntimeError('Multiple Eleven Racks connected. Select a device with --device (see devices).')


def sequencer_cards():
    """Map ALSA sequencer client IDs to hardware card numbers, without MIDI I/O."""
    lib = ctypes.CDLL('libasound.so.2')
    ptr = ctypes.c_void_p
    lib.snd_seq_open.argtypes = [ctypes.POINTER(ptr), ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
    lib.snd_seq_client_info_malloc.argtypes = [ctypes.POINTER(ptr)]
    lib.snd_seq_client_info_set_client.argtypes = [ptr, ctypes.c_int]
    lib.snd_seq_query_next_client.argtypes = [ptr, ptr]
    lib.snd_seq_client_info_get_client.argtypes = [ptr]
    lib.snd_seq_client_info_get_card.argtypes = [ptr]
    lib.snd_seq_client_info_free.argtypes = [ptr]
    lib.snd_seq_close.argtypes = [ptr]
    seq, info = ptr(), ptr()
    if lib.snd_seq_open(ctypes.byref(seq), b'default', 3, 1) < 0:
        return {}
    try:
        if lib.snd_seq_client_info_malloc(ctypes.byref(info)) < 0:
            return {}
        lib.snd_seq_client_info_set_client(info, -1)
        result = {}
        while lib.snd_seq_query_next_client(seq, info) >= 0:
            card = lib.snd_seq_client_info_get_card(info)
            if card >= 0:
                result[lib.snd_seq_client_info_get_client(info)] = card
        return result
    finally:
        if info:
            lib.snd_seq_client_info_free(info)
        lib.snd_seq_close(seq)


def midi_identities():
    by_card = {d['card']: d for d in devices()}
    return {client: by_card[card] for client, card in sequencer_cards().items() if card in by_card}


def port_device(name, identities):
    match = re.search(r'(\d+):(\d+)\s*$', name)
    return identities.get(int(match[1])) if match else None

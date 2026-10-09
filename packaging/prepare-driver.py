#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2026 Koen de Boevé
"""Apply the Eleven Rack changes to matching distro snd-usb-audio sources.

Use stable context rather than line-number patches to accommodate kernel series.
Fail on unfamiliar source layout; never silently build an unpatched module.
"""
import argparse
from pathlib import Path
import re


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('Unsupported kernel source layout: ' + old[:80])
    return text.replace(old, new, 1)


def prepare(root):
    original = {name: (root / name).read_text() for name in
                ('quirks-table.h', 'implicit.c', 'format.c', 'quirks.c',
                 'mixer_maps.c', 'mixer.c', 'Makefile')}
    if 'Eleven Rack Linux package' in original['quirks-table.h']:
        raise RuntimeError('Source already patched; extract a clean source tree first.')
    if re.search(r'0x0dba,\s*0xb011', original['quirks-table.h']):
        raise RuntimeError('Kernel already has an Eleven Rack quirk; review before replacing it.')
    result = dict(original)
    # The explicit initializer also works before the newer QUIRK_DATA macros.
    entry = '''/* Eleven Rack Linux package: vendor interfaces with UAC2 descriptors. */
{
\tUSB_DEVICE_VENDOR_SPEC(0x0dba, 0xb011),
\t.driver_info = (unsigned long)&(const struct snd_usb_audio_quirk) {
\t\t.vendor_name = "Digidesign",
\t\t.product_name = "Eleven Rack",
\t\t.ifnum = 1,
\t\t.type = QUIRK_COMPOSITE,
\t\t.data = (const struct snd_usb_audio_quirk[]) {
\t\t\t{ .ifnum = 1, .type = QUIRK_AUDIO_STANDARD_MIXER },
\t\t\t{ .ifnum = 2, .type = QUIRK_MIDI_STANDARD_INTERFACE },
\t\t\t{ .ifnum = 3, .type = QUIRK_AUDIO_STANDARD_INTERFACE },
\t\t\t{ .ifnum = 4, .type = QUIRK_AUDIO_STANDARD_INTERFACE },
\t\t\t{ .ifnum = -1 }
\t\t}
\t}
},
'''
    result['quirks-table.h'] = replace_once(original['quirks-table.h'],
        '/* Digidesign Mbox */', entry + '/* Digidesign Mbox */')
    marker = 'static const struct snd_usb_implicit_fb_match playback_implicit_fb_quirks[] = {'
    result['implicit.c'] = replace_once(original['implicit.c'], marker,
        marker + '\n\tIMPLICIT_FB_FIXED_DEV(0x0dba, 0xb011, 0x83, 4), /* Eleven Rack */')
    marker = 'static int line6_parse_audio_format_rates_quirk('
    text = original['format.c']
    start = text.index(marker)
    switch = text.index('\tswitch (chip->usb_id) {', start)
    rates = '''
\tcase USB_ID(0x0dba, 0xb011): { /* Digidesign Eleven Rack */
\t\tstatic const unsigned int rates[] = { 44100, 48000, 88200, 96000 };
\t\t/* GET_RANGE fails; GET_CUR and SET_CUR are available. */
\t\tkfree(fp->rate_table);
\t\tfp->rate_table = kmemdup(rates, sizeof(rates), GFP_KERNEL);
\t\tif (!fp->rate_table)
\t\t\treturn -ENOMEM;
\t\tfp->nr_rates = ARRAY_SIZE(rates);
\t\tset_rate_table_min_max(fp);
\t\treturn 0;
\t}'''
    end = switch + len('\tswitch (chip->usb_id) {')
    result['format.c'] = text[:end] + rates + text[end:]
    text = original['quirks.c']
    start = text.index('void snd_usb_audioformat_attributes_quirk(')
    switch = text.index('\tswitch (chip->usb_id) {', start)
    end = switch + len('\tswitch (chip->usb_id) {')
    result['quirks.c'] = text[:end] + '''
\tcase USB_ID(0x0dba, 0xb011): /* Eleven Rack */
\t\t/* Endpoint pitch SET_CUR fails; use the clock frequency control. */
\t\tfp->attributes &= ~UAC_EP_CS_ATTR_PITCH_CONTROL;
\t\tbreak;''' + text[end:]
    maps = '''/* Eleven Rack: do not probe proprietary routing units. */
static const struct usbmix_name_map eleven_rack_map[] = {
\t{ 0x20, NULL },
\t{ 0x40, NULL },
\t{ 0x41, NULL },
\t{ 0x80, "Eleven Rack Clock Source" },
\t{}
};
static const struct usbmix_selector_map eleven_rack_selectors[] = {
\t{ .id = 0x80, .count = 3,
\t  .names = (const char *[]) { "Internal", "AES", "S/PDIF" } },
\t{}
};
'''
    marker = 'static const struct usbmix_ctl_map usbmix_ctl_maps[] = {'
    result['mixer_maps.c'] = replace_once(original['mixer_maps.c'], marker,
        maps + marker + '''
\t{
\t\t.id = USB_ID(0x0dba, 0xb011),
\t\t.map = eleven_rack_map,
\t\t.selector_map = eleven_rack_selectors,
\t},''')
    text = original['mixer.c']
    start = text.index('static int mixer_ctl_selector_put(')
    end = text.index('\n/* alsa control interface for selector unit */', start)
    callback = text[start:end]
    old_setter = '\t\tset_cur_ctl_value(cval, cval->control << 8, val);'
    checked_setter = '\t\terr = set_cur_ctl_value(cval, cval->control << 8, val);'
    rack_setter = '''
\t\terr = set_cur_ctl_value(cval, cval->control << 8, val);
\t\t/* Eleven Rack clock writes must report hardware failures. */
\t\tif (err < 0 && cval->head.mixer->chip->usb_id == USB_ID(0x0dba, 0xb011))
\t\t\treturn err;'''.lstrip('\n')
    if old_setter in callback:
        callback = replace_once(callback, old_setter, rack_setter)
    else:
        # Newer ALSA already checks setter errors. Preserve its generic error
        # handling, while still ensuring Rack errors cannot be filtered away.
        new_error_handling = checked_setter + '\n\t\tif (err < 0)\n\t\t\treturn filter_error(cval, err);'
        callback = replace_once(callback, new_error_handling,
                                rack_setter + '\n\t\tif (err < 0)\n\t\t\treturn filter_error(cval, err);')
    result['mixer.c'] = text[:start] + callback + text[end:]
    text = original['Makefile']
    marker = '# Toplevel Module Dependency'
    if marker not in text:
        raise RuntimeError('Unrecognized kernel Makefile.')
    result['Makefile'] = text[:text.index(marker)] + 'obj-m := snd-usb-audio.o\n'
    # Validate every transformation before modifying any source file.
    for name, text in result.items():
        (root / name).write_text(text)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    prepare(args.source)

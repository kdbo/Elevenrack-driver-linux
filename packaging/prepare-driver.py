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


def implicit_feedback_capacity(card, endpoint):
    """Backport upstream 76a986c980bb only when its source fix is absent.

    CVE-2026-98265: payload byte bounds do not protect iso_frame_desc[].
    Inspect source instead of kernel versions because distros backport fixes.
    Return new strings only; unfamiliar/partial fixes must never be written.
    """
    def compact(text):
        text = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
        return re.sub(r'\s+', '', text)

    c, e = compact(card), compact(endpoint)
    fixed = (
        c.count('unsignedintmax_urb_packs;') == 1
        and e.count('ep->max_urb_packs=urb_packs;') == 1
        and e.count('ctx->packets=min_t(int,packet->packets,ep->max_urb_packs);') == 1
        and e.count('memcpy(ctx->packet_size,packet->packet_size,'
                    'ctx->packets*sizeof(packet->packet_size[0]));') == 1
        and e.count('u->urb=usb_alloc_urb(u->packets,GFP_KERNEL);') == 1
        and ('ep->max_urb_packs=urb_packs;'
             'for(i=0;i<ep->nurbs;i++){structsnd_urb_ctx*u=&ep->urb[i];'
             'u->index=i;u->ep=ep;u->packets=urb_packs;') in e
        and 'ctx->packets=packet->packets;' not in e
        and 'u->packets++;' not in e
    )
    if fixed:
        return card, endpoint, 'already present'
    if 'max_urb_packs' in c or 'max_urb_packs' in e:
        raise RuntimeError('Incomplete or unfamiliar implicit-feedback capacity fix; review kernel sources')

    card = replace_once(card,
        '\tunsigned int maxframesize;      /* max packet size in frames */',
        '\tunsigned int maxframesize;      /* max packet size in frames */\n'
        '\tunsigned int max_urb_packs; /* packets allocated per data URB */')
    endpoint = replace_once(endpoint, '\t\tctx->packets = packet->packets;',
        '\t\tctx->packets = min_t(int, packet->packets,\n'
        '\t\t\t\t     ep->max_urb_packs);')
    endpoint = replace_once(endpoint,
        '\t\t       packet->packets * sizeof(packet->packet_size[0]));',
        '\t\t       ctx->packets * sizeof(packet->packet_size[0]));')
    endpoint = replace_once(endpoint,
        '\t\tif (fmt->fmt_type == UAC_FORMAT_TYPE_II)\n'
        '\t\t\tu->packets++; /* for transfer delimiter */\n', '')
    endpoint = replace_once(endpoint,
        '\t/* allocate and initialize data urbs */\n',
        '\t/* Upstream 76a986c980bb: keep feedback within allocated descriptors. */\n'
        '\tif (fmt->fmt_type == UAC_FORMAT_TYPE_II)\n'
        '\t\turb_packs++; /* for transfer delimiter */\n'
        '\tep->max_urb_packs = urb_packs;\n\n'
        '\t/* allocate and initialize data urbs */\n')
    # Validate the generated fix through the same gate used for distro backports.
    _, _, status = implicit_feedback_capacity(card, endpoint)
    assert status == 'already present'
    return card, endpoint, 'backported'


def eleven_rack_attributes(text):
    """Normalize only the known Rack playback layout for implicit feedback."""
    start = text.index('void snd_usb_audioformat_attributes_quirk(')
    switch = text.index('\tswitch (chip->usb_id) {', start)
    end = switch + len('\tswitch (chip->usb_id) {')
    return text[:end] + '''
\tcase USB_ID(0x0dba, 0xb011): /* Eleven Rack */
\t\t/* Endpoint pitch SET_CUR fails; use the clock frequency control. */
\t\tfp->attributes &= ~UAC_EP_CS_ATTR_PITCH_CONTROL;
\t\t/* Match capture's 13-frame ceiling for implicit-feedback packing.
\t\t * Capture: 416 / (8 * 4) = 13 frames; playback: 13 * 6 * 4.
\t\t * Restrict this allocation quirk to the known descriptor layout.
\t\t */
\t\tif (stream == SNDRV_PCM_STREAM_PLAYBACK && fp->iface == 3 &&
\t\t    fp->altsetting == 1 && fp->endpoint == 0x03 &&
\t\t    fp->channels == 6 && fp->datainterval == 0 &&
\t\t    fp->maxpacksize == 416)
\t\t\tfp->maxpacksize = 312;
\t\tbreak;''' + text[end:]


def eleven_playback_lead(text):
    """Optionally queue a bounded amount of silent playback at implicit-feedback start.

    Upstream submits no playback until capture returns, so the OUT ring holds only
    about one capture URB (0.5-1 ms). A late completion empties it (xHCI Ring
    Underrun) and shifts playback. QUIRK_FLAG_PLAYBACK_FIRST fixes that by queuing
    every URB, costing up to ~14 ms. This queues only the requested milliseconds.
    0 (the default) keeps the upstream behaviour.
    """
    text = replace_once(text, '#include <linux/init.h>\n',
                        '#include <linux/init.h>\n#include <linux/moduleparam.h>\n')
    text = replace_once(text, '#include "quirks.h"\n', '''#include "quirks.h"

/* Eleven Rack Linux package: bounded implicit-feedback playback lead. */
static unsigned int eleven_playback_lead_ms;
module_param(eleven_playback_lead_ms, uint, 0644);
MODULE_PARM_DESC(eleven_playback_lead_ms,
\t"Eleven Rack: ms of silent playback queued at implicit-feedback start (0 = upstream)");

static unsigned int eleven_lead_urbs(struct snd_usb_endpoint *ep)
{
\tunsigned int ms = min(READ_ONCE(eleven_playback_lead_ms), 20U);
\tunsigned int packets;

\tif (!ms || ep->chip->usb_id != USB_ID(0x0dba, 0xb011) ||
\t    !ep->nurbs || !ep->urb[0].packets)
\t\treturn 0;
\tpackets = ms * (snd_usb_get_speed(ep->chip->dev) == USB_SPEED_FULL ?
\t\t\t1 : 8 >> ep->datainterval);
\treturn clamp(DIV_ROUND_UP(packets, ep->urb[0].packets), 1U, ep->nurbs);
}
''')
    text = replace_once(text, '''int snd_usb_endpoint_start(struct snd_usb_endpoint *ep)
{
\tbool is_playback = usb_pipeout(ep->pipe);
\tint err;
\tunsigned int i;
''', '''int snd_usb_endpoint_start(struct snd_usb_endpoint *ep)
{
\tbool is_playback = usb_pipeout(ep->pipe);
\tint err;
\tunsigned int i, lead;
''')
    text = replace_once(text, '''\tif (snd_usb_endpoint_implicit_feedback_sink(ep) &&
\t    !(ep->chip->quirk_flags & QUIRK_FLAG_PLAYBACK_FIRST)) {
\t\tusb_audio_dbg(ep->chip, "No URB submission due to implicit fb sync\\n");''',
    '''\tlead = snd_usb_endpoint_implicit_feedback_sink(ep) &&
\t       !(ep->chip->quirk_flags & QUIRK_FLAG_PLAYBACK_FIRST) ?
\t       eleven_lead_urbs(ep) : 0;
\tif (snd_usb_endpoint_implicit_feedback_sink(ep) && !lead &&
\t    !(ep->chip->quirk_flags & QUIRK_FLAG_PLAYBACK_FIRST)) {
\t\tusb_audio_dbg(ep->chip, "No URB submission due to implicit fb sync\\n");''')
    # Without queued application data, fall back to waiting for capture.
    text = replace_once(text, '''\tif (!i) {
\t\tusb_audio_dbg(ep->chip, "XRUN at starting EP 0x%x\\n",''', '''\tif (!i && !lead) {
\t\tusb_audio_dbg(ep->chip, "XRUN at starting EP 0x%x\\n",''')
    return replace_once(text, '''\tfor (i = 0; i < ep->nurbs; i++) {
\t\tstruct urb *urb = ep->urb[i].urb;

\t\tif (snd_BUG_ON(!urb))
\t\t\tgoto __error;

\t\tif (is_playback)''', '''\tfor (i = 0; i < (lead ? lead : ep->nurbs); i++) {
\t\tstruct urb *urb = ep->urb[i].urb;

\t\tif (snd_BUG_ON(!urb))
\t\t\tgoto __error;

\t\tif (is_playback)''')


def prepare(root):
    original = {name: (root / name).read_text() for name in
                ('quirks-table.h', 'implicit.c', 'format.c', 'quirks.c',
                 'mixer_maps.c', 'mixer.c', 'mixer_quirks.c', 'Makefile', 'pcm.c', 'card.h', 'endpoint.c')}
    if 'Eleven Rack Linux package' in original['quirks-table.h']:
        raise RuntimeError('Source already patched; extract a clean source tree first.')
    if re.search(r'0x0dba,\s*0xb011', original['quirks-table.h']):
        raise RuntimeError('Kernel already has an Eleven Rack quirk; review before replacing it.')
    result = dict(original)
    result['card.h'], result['endpoint.c'], capacity_status = implicit_feedback_capacity(
        original['card.h'], original['endpoint.c'])
    result['endpoint.c'] = eleven_playback_lead(result['endpoint.c'])
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
    result['quirks.c'] = eleven_rack_attributes(original['quirks.c'])
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
    text = replace_once(original['mixer_quirks.c'], '#include "helper.h"',
                        '#include "helper.h"\n#include "mixer-eleven-rack.h"')
    marker = 'int snd_usb_mixer_apply_create_quirk(struct usb_mixer_interface *mixer)'
    start = text.index(marker)
    switch = text.index('\tswitch (mixer->chip->usb_id) {', start)
    end = switch + len('\tswitch (mixer->chip->usb_id) {')
    result['mixer_quirks.c'] = text[:end] + '''
\tcase USB_ID(0x0dba, 0xb011):
\t\terr = snd_eleven_monitor_create(mixer);
\t\tbreak;''' + text[end:]
    result['mixer-eleven-rack.h'] = Path(__file__).with_name('mixer-eleven-rack.h').read_text()
    text = original['Makefile']
    marker = '# Toplevel Module Dependency'
    if marker not in text:
        raise RuntimeError('Unrecognized kernel Makefile.')
    result['Makefile'] = text[:text.index(marker)] + 'obj-m := snd-usb-audio.o\n'
    # Opt-in high-resolution delay for this USB id. The upstream frame-counter
    # path remains the default and remains unchanged for every other interface.
    result['card.h'] = replace_once(result['card.h'],
        'unsigned int last_frame_number;\t/* stored frame number */',
        'unsigned int last_frame_number;\t/* stored frame number */\n\tu64 eleven_delay_ns;')
    text = replace_once(original['pcm.c'], '#include <linux/init.h>',
                        '#include <linux/init.h>\n#include <linux/ktime.h>')
    text = replace_once(text, '/* return the estimated delay based on USB frame counters */',
        'static bool eleven_delay_hires;\n'
        'module_param(eleven_delay_hires, bool, 0644);\n'
        'MODULE_PARM_DESC(eleven_delay_hires, "Eleven Rack high-resolution USB delay accounting");\n\n'
        '/* return the estimated delay based on USB frame counters */')
    text = replace_once(text, 'est_delay = frame_diff * runtime->rate / 1000;',
        'est_delay = frame_diff * runtime->rate / 1000;\n'
        '\tif (eleven_delay_hires && subs->stream->chip->usb_id == USB_ID(0x0dba, 0xb011) &&\n'
        '\t    subs->eleven_delay_ns) {\n'
        '\t\tu64 elapsed = ktime_get_ns() - subs->eleven_delay_ns;\n'
        '\t\telapsed = min_t(u64, elapsed, 256 * NSEC_PER_MSEC);\n'
        '\t\test_delay = div_u64(elapsed * runtime->rate, NSEC_PER_SEC);\n'
        '\t}')
    text = text.replace('subs->last_frame_number = 0;',
                        'subs->last_frame_number = 0;\n\tsubs->eleven_delay_ns = 0;')
    text = replace_once(text, 'subs->last_frame_number = current_frame_number;',
        'subs->last_frame_number = current_frame_number;\n'
        '\t\t\tif (subs->stream->chip->usb_id == USB_ID(0x0dba, 0xb011))\n'
        '\t\t\t\tsubs->eleven_delay_ns = ktime_get_ns();')
    timestamp = 'subs->last_frame_number = usb_get_current_frame_number(subs->dev);'
    if not text.count(timestamp):
        raise RuntimeError('Unsupported USB playback timestamp layout')
    text = text.replace(timestamp, timestamp + '\n'
        '\t\tif (subs->stream->chip->usb_id == USB_ID(0x0dba, 0xb011))\n'
        '\t\t\tsubs->eleven_delay_ns = ktime_get_ns();')
    result['pcm.c'] = text
    # Validate every transformation before modifying any source file.
    for name, text in result.items():
        (root / name).write_text(text)
    print('Implicit-feedback URB capacity fix (76a986c980bb): ' + capacity_status)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    prepare(args.source)

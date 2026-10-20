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
    # Feedback sizes are copied with memcpy (7.0) or a loop (Ubuntu 6.8 backport).
    bounded_copies = (
        e.count('memcpy(ctx->packet_size,packet->packet_size,'
                'ctx->packets*sizeof(packet->packet_size[0]));')
        + e.count('for(i=0;i<ctx->packets;i++)ctx->packet_size[i]=packet->packet_size[i];'))
    unbounded_copy = (
        'packet->packets*sizeof(packet->packet_size[0])' in e
        or 'for(i=0;i<packet->packets;i++)ctx->packet_size[i]=' in e)
    fixed = (
        c.count('unsignedintmax_urb_packs;') == 1
        and e.count('ep->max_urb_packs=urb_packs;') == 1
        and e.count('ctx->packets=min_t(int,packet->packets,ep->max_urb_packs);') == 1
        and bounded_copies == 1 and not unbounded_copy
        and e.count('u->urb=usb_alloc_urb(u->packets,GFP_KERNEL);') == 1
        and ('ep->max_urb_packs=urb_packs;'
             'for(i=0;i<ep->nurbs;i++){structsnd_urb_ctx*u=&ep->urb[i];'
             'u->index=i;u->ep=ep;u->packets=urb_packs;') in e
        and 'ctx->packets=packet->packets;' not in e
        and 'u->packets++;' not in e
    )
    if fixed:
        return card, endpoint, 'already present'
    # Before 7.0 feedback only copied sizes into the fixed-size array and never
    # resized ctx->packets, so the allocated descriptor count was never exceeded.
    unaffected = (
        'max_urb_packs' not in c and 'max_urb_packs' not in e
        and 'ctx->packets=packet->packets;' not in e
        and e.count('for(i=0;i<packet->packets;i++)'
                    'ctx->packet_size[i]=packet->packet_size[i];') == 1
        and c.count('intpacket_size[MAX_PACKS_HS];') == 1
        and c.count('uint32_tpacket_size[MAX_PACKS_HS];') == 1
    )
    if unaffected:
        return card, endpoint, 'not needed (feedback does not resize URBs)'
    if 'max_urb_packs' in c or 'max_urb_packs' in e:
        raise RuntimeError('Incomplete or unfamiliar implicit-feedback capacity fix; review kernel sources')

    card = replace_once(card,
        '\tunsigned int maxframesize;      /* max packet size in frames */',
        '\tunsigned int maxframesize;      /* max packet size in frames */\n'
        '\tunsigned int max_urb_packs; /* packets allocated per data URB */')
    endpoint = replace_once(endpoint, '\t\tctx->packets = packet->packets;',
        '\t\tctx->packets = min_t(int, packet->packets,\n'
        '\t\t\t\t     ep->max_urb_packs);')
    loop = re.compile(r'for \(i = 0; i < packet->packets; i\+\+\)(\n\t+ctx->packet_size\[i\] = '
                      r'packet->packet_size\[i\];)')
    if len(loop.findall(endpoint)) == 1:
        endpoint = loop.sub(r'for (i = 0; i < ctx->packets; i++)\1', endpoint)
    else:
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
    """Queue a bounded amount of silent playback at implicit-feedback start.

    Upstream submits no playback until capture returns, so the OUT ring holds only
    about one capture URB (0.5-1 ms). A late completion empties it (xHCI Ring
    Underrun) and shifts playback. QUIRK_FLAG_PLAYBACK_FIRST fixes that by queuing
    every URB, costing up to ~14 ms. This queues only the requested milliseconds:
    2 ms by default for the Rack, which removed the underruns in testing at a
    cost of 0.3-1.4 ms latency. 0 keeps the upstream behaviour.
    """
    text = replace_once(text, '#include <linux/init.h>\n',
                        '#include <linux/init.h>\n#include <linux/moduleparam.h>\n')
    text = replace_once(text, '#include "quirks.h"\n', '''#include "quirks.h"

/* Eleven Rack Linux package: bounded implicit-feedback playback lead. */
static unsigned int eleven_playback_lead_ms = 2;
module_param(eleven_playback_lead_ms, uint, 0644);
MODULE_PARM_DESC(eleven_playback_lead_ms,
\t"Eleven Rack: ms of silent playback queued at implicit-feedback start (default 2, 0 = upstream)");

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


def eleven_stats(usbaudio, card, endpoint, proc):
    """Count playback gaps, xruns, starts and capture errors for the Rack.

    Each capture completion releases one playback URB. When the USB giveback
    softirq is delayed for longer than the queued playback (for example behind
    another driver's softirq, or deferred to ksoftirqd), the OUT ring runs empty:
    the Rack plays silence and all later audio is shifted, without an xrun.
    URB completions are handled in hardware order however late the softirq
    runs, so the number of playback URBs still queued when one completes is
    fixed by the hardware schedule: constant while playback is contiguous, and
    one URB higher for good after each gap. For the Rack only, track the
    minimum of that level per window of completions; a lasting rise is counted
    as a gap of that many URBs, logged rate-limited and exposed in
    /proc/asound/<card>/eleven_stats. This needs no host controller support
    and does not depend on softirq timing. The same file counts driver-reported
    xruns and data endpoint starts per direction, and capture packets with a USB
    error status and capture URBs without data once a stream has settled (the
    first IN transaction after a start often fails harmlessly). Audio handling
    is unchanged.
    """
    usbaudio = replace_once(usbaudio, '\tatomic_t shutdown;\n',
                            '\tatomic_t shutdown;\n'
                            '\t/* Eleven Rack Linux package: /proc/asound/<card>/eleven_stats */\n'
                            '\tatomic_t eleven_playback_gaps;\t/* playback schedule gaps */\n'
                            '\tatomic64_t eleven_gap_us;\t/* their total length */\n'
                            '\tunsigned int eleven_last_gap;\t/* last length in us */\n'
                            '\tu64 eleven_last_gap_ns;\t\t/* boottime of the last one */\n'
                            '\tatomic_t eleven_xruns[2];\t/* driver-reported, by direction */\n'
                            '\tatomic_t eleven_starts[2];\t/* data endpoint starts */\n'
                            '\tatomic_t eleven_capture_packet_errors;\n'
                            '\tatomic_t eleven_capture_empty_urbs;\n')
    card = replace_once(card, '\tunsigned int maxframesize;      /* max packet size in frames */\n',
                        '\tunsigned int maxframesize;      /* max packet size in frames */\n'
                        '\t/* Eleven Rack: queued playback URBs at each playback completion */\n'
                        '\tint eleven_level_min;\t\t/* minimum in the current window */\n'
                        '\tint eleven_level_base;\t\t/* minimum of the last window */\n'
                        '\tunsigned int eleven_samples;\t/* completions in the current window */\n'
                        '\tunsigned int eleven_windows;\t/* windows since start */\n'
                        '\tunsigned int eleven_capture_urbs;\t/* capture URBs since start */\n')
    endpoint = replace_once(endpoint, 'static void push_back_to_ready_list(struct snd_usb_endpoint *ep,\n', '''/*
 * Eleven Rack Linux package: detect gaps in the implicit-feedback playback
 * stream. Completions arrive in hardware order, so the number of playback URBs
 * still queued when one completes is constant while playback is contiguous and
 * rises by one URB for good after each gap. Compare per-window minimums, after
 * the first windows of a stream have settled. Called from the completion
 * handler only, which runs serialized for an endpoint.
 */
#define ELEVEN_LEVEL_WINDOW 64
#define ELEVEN_SETTLE_WINDOWS 2

static void eleven_track_level(struct snd_usb_endpoint *ep, unsigned int packets)
{
\tstruct snd_usb_audio *chip = ep->chip;
\tint level, steps;
\tunsigned int gap;

\tif (chip->usb_id != USB_ID(0x0dba, 0xb011) || !ep_state_running(ep))
\t\treturn;
\tlevel = atomic_read(&ep->submitted_urbs);
\tif (!ep->eleven_samples++ || level < ep->eleven_level_min)
\t\tep->eleven_level_min = level;
\tif (ep->eleven_samples < ELEVEN_LEVEL_WINDOW)
\t\treturn;
\tep->eleven_samples = 0;
\tsteps = ep->eleven_level_min - ep->eleven_level_base;
\tep->eleven_level_base = ep->eleven_level_min;
\tif (ep->eleven_windows < ELEVEN_SETTLE_WINDOWS) {
\t\tep->eleven_windows++;
\t\treturn;
\t}
\tif (steps <= 0)
\t\treturn;
\t/* One packet per microframe for the Rack's high-speed endpoint. */
\tgap = steps * packets * 125;
\tatomic_add(steps, &chip->eleven_playback_gaps);
\tatomic64_add(gap, &chip->eleven_gap_us);
\tWRITE_ONCE(chip->eleven_last_gap, gap);
\tWRITE_ONCE(chip->eleven_last_gap_ns, ktime_get_boottime_ns());
\tdev_warn_ratelimited(&chip->dev->dev,
\t\t\t     "Eleven Rack: playback ran dry, output shifted by about %u us; USB completion handling was delayed (see /proc/asound/%s/eleven_stats)\\n",
\t\t\t     gap, chip->card->id);
}

/*
 * Eleven Rack Linux package: capture packets with a USB error, and empty URBs.
 * The first IN transaction after a capture start often fails (USB Transaction
 * Error) before any audio flows; count only once the stream has settled.
 */
#define ELEVEN_CAPTURE_SETTLE_URBS 8

static void eleven_count_capture(struct snd_usb_endpoint *ep, struct urb *urb)
{
\tunsigned int i, errors = 0, bytes = 0;

\tif (ep->chip->usb_id != USB_ID(0x0dba, 0xb011) || usb_pipeout(ep->pipe) ||
\t    ep->type != SND_USB_ENDPOINT_TYPE_DATA)
\t\treturn;
\tif (ep->eleven_capture_urbs < ELEVEN_CAPTURE_SETTLE_URBS) {
\t\tep->eleven_capture_urbs++;
\t\treturn;
\t}
\tfor (i = 0; i < urb->number_of_packets; i++) {
\t\tif (urb->iso_frame_desc[i].status)
\t\t\terrors++;
\t\telse
\t\t\tbytes += urb->iso_frame_desc[i].actual_length;
\t}
\tif (errors)
\t\tatomic_add(errors, &ep->chip->eleven_capture_packet_errors);
\tif (!bytes)
\t\tatomic_inc(&ep->chip->eleven_capture_empty_urbs);
}

static void push_back_to_ready_list(struct snd_usb_endpoint *ep,
''')
    endpoint = replace_once(endpoint, '''\t\t\tif (atomic_dec_and_test(&ep->submitted_urbs) &&
\t\t\t    !snd_usb_endpoint_implicit_feedback_sink(ep))
\t\t\t\tnotify_xrun(ep);
\t\t\treturn;''', '''\t\t\tif (atomic_dec_and_test(&ep->submitted_urbs) &&
\t\t\t    !snd_usb_endpoint_implicit_feedback_sink(ep))
\t\t\t\tnotify_xrun(ep);
\t\t\tif (snd_usb_endpoint_implicit_feedback_sink(ep))
\t\t\t\televen_track_level(ep, ctx->packets);
\t\t\treturn;''')
    endpoint = replace_once(endpoint, '\tep->sample_accum = 0;\n',
                            '\tep->sample_accum = 0;\n'
                            '\tep->eleven_samples = ep->eleven_windows = 0;\n'
                            '\tep->eleven_capture_urbs = 0;\n')
    endpoint = replace_once(endpoint, '\t\tsnd_pcm_stop_xrun(psubs);\n',
                            '\t\tif (ep->chip->usb_id == USB_ID(0x0dba, 0xb011))\n'
                            '\t\t\tatomic_inc(&ep->chip->eleven_xruns[!usb_pipeout(ep->pipe)]);\n'
                            '\t\tsnd_pcm_stop_xrun(psubs);\n')
    endpoint = replace_once(endpoint, '\tif (atomic_inc_return(&ep->running) != 1)\n\t\treturn 0;\n',
                            '\tif (atomic_inc_return(&ep->running) != 1)\n\t\treturn 0;\n'
                            '\tif (ep->chip->usb_id == USB_ID(0x0dba, 0xb011) &&\n'
                            '\t    ep->type == SND_USB_ENDPOINT_TYPE_DATA)\n'
                            '\t\tatomic_inc(&ep->chip->eleven_starts[!is_playback]);\n')
    endpoint = replace_once(endpoint, '\t} else {\n\t\tretire_inbound_urb(ep, ctx);\n',
                            '\t} else {\n\t\televen_count_capture(ep, urb);\n'
                            '\t\tretire_inbound_urb(ep, ctx);\n')
    proc = replace_once(proc, 'void snd_usb_audio_create_proc(struct snd_usb_audio *chip)\n{', '''/* Eleven Rack Linux package: playback gaps, xruns, starts and capture errors. */
static void proc_eleven_stats_read(struct snd_info_entry *entry,
\t\t\t\t   struct snd_info_buffer *buffer)
{
\tstruct snd_usb_audio *chip = entry->private_data;

\tsnd_iprintf(buffer, "playback_gaps %d\\n", atomic_read(&chip->eleven_playback_gaps));
\tsnd_iprintf(buffer, "gap_total_us %lld\\n",
\t\t    (long long)atomic64_read(&chip->eleven_gap_us));
\tsnd_iprintf(buffer, "last_gap_us %u\\n", READ_ONCE(chip->eleven_last_gap));
\tsnd_iprintf(buffer, "last_gap_boottime_ns %llu\\n",
\t\t    (unsigned long long)READ_ONCE(chip->eleven_last_gap_ns));
\tsnd_iprintf(buffer, "playback_xruns %d\\ncapture_xruns %d\\n",
\t\t    atomic_read(&chip->eleven_xruns[0]), atomic_read(&chip->eleven_xruns[1]));
\tsnd_iprintf(buffer, "playback_starts %d\\ncapture_starts %d\\n",
\t\t    atomic_read(&chip->eleven_starts[0]), atomic_read(&chip->eleven_starts[1]));
\tsnd_iprintf(buffer, "capture_packet_errors %d\\ncapture_empty_urbs %d\\n",
\t\t    atomic_read(&chip->eleven_capture_packet_errors),
\t\t    atomic_read(&chip->eleven_capture_empty_urbs));
}

void snd_usb_audio_create_proc(struct snd_usb_audio *chip)
{
\tif (chip->usb_id == USB_ID(0x0dba, 0xb011))
\t\tsnd_card_ro_proc_new(chip->card, "eleven_stats", chip, proc_eleven_stats_read);''')
    return usbaudio, card, endpoint, proc


def prepare(root):
    original = {name: (root / name).read_text() for name in
                ('quirks-table.h', 'implicit.c', 'format.c', 'quirks.c',
                 'mixer_maps.c', 'mixer.c', 'mixer_quirks.c', 'Makefile', 'pcm.c', 'card.h', 'endpoint.c',
                 'usbaudio.h', 'proc.c')}
    if 'Eleven Rack Linux package' in original['quirks-table.h']:
        raise RuntimeError('Source already patched; extract a clean source tree first.')
    if re.search(r'0x0dba,\s*0xb011', original['quirks-table.h']):
        raise RuntimeError('Kernel already has an Eleven Rack quirk; review before replacing it.')
    result = dict(original)
    result['card.h'], result['endpoint.c'], capacity_status = implicit_feedback_capacity(
        original['card.h'], original['endpoint.c'])
    result['endpoint.c'] = eleven_playback_lead(result['endpoint.c'])
    result['usbaudio.h'], result['card.h'], result['endpoint.c'], result['proc.c'] = eleven_stats(
        original['usbaudio.h'], result['card.h'], result['endpoint.c'], original['proc.c'])
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

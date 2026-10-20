#!/usr/bin/env python3
"""Compile the generated Rack quirk and verify its device/layout boundaries."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prepare', ROOT/'packaging/prepare-driver.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)

QUIRK = '''void snd_usb_audioformat_attributes_quirk(struct snd_usb_audio *chip,
        struct audioformat *fp, int stream)
{
\tswitch (chip->usb_id) {
    default: break;
    }
}
'''


class PacketNormalization(unittest.TestCase):
    def test_compiled_quirk_preserves_other_devices_and_layouts(self):
        source = r'''
#include <assert.h>
#define USB_ID(v, p) (((v) << 16) | (p))
#define SNDRV_PCM_STREAM_PLAYBACK 0
#define UAC_EP_CS_ATTR_PITCH_CONTROL 2
struct snd_usb_audio { unsigned int usb_id; };
struct audioformat {
    unsigned int attributes, iface, altsetting, endpoint, channels;
    unsigned int datainterval, maxpacksize;
};
''' + prepare.eleven_rack_attributes(QUIRK) + r'''
int main(void) {
    const struct audioformat original = { 2, 3, 1, 0x03, 6, 0, 416 };
    for (int i = 0; i < 10; ++i) {
        struct audioformat fp = original;
        struct snd_usb_audio chip = { USB_ID(0x0dba, 0xb011) };
        int stream = 0;
        switch (i) {
        case 1: chip.usb_id = USB_ID(0x0dba, 0xb012); break;
        case 2: chip.usb_id = USB_ID(0x0dbb, 0xb011); break;
        case 3: stream = 1; break;
        case 4: fp.iface = 4; break;
        case 5: fp.altsetting = 2; break;
        case 6: fp.endpoint = 0x83; break;
        case 7: fp.channels = 8; break;
        case 8: fp.datainterval = 1; break;
        case 9: fp.maxpacksize = 512; break;
        }
        snd_usb_audioformat_attributes_quirk(&chip, &fp, stream);
        assert(fp.maxpacksize == (i == 0 ? 312 : i == 9 ? 512 : 416));
        assert(fp.attributes == (i == 1 || i == 2 ? 2 : 0));
    }
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            c, binary = Path(tmp)/'quirk.c', Path(tmp)/'quirk'
            c.write_text(source)
            subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', str(c), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

    def test_playback_lead_applies_to_clean_source_and_rejects_unknown_layout(self):
        archive = Path('/usr/src/linux-source-7.0.0.tar.bz2')
        if not archive.exists():
            self.skipTest('Ubuntu 7.0 kernel source archive not installed')
        endpoint = subprocess.run(['tar', '-xjOf', str(archive),
                                   'linux-source-7.0.0/sound/usb/endpoint.c'],
                                  check=True, capture_output=True, text=True).stdout
        patched = prepare.eleven_playback_lead(endpoint)
        self.assertIn('static unsigned int eleven_playback_lead_ms = 2;', patched)
        self.assertIn('module_param(eleven_playback_lead_ms, uint, 0644);', patched)
        self.assertIn('for (i = 0; i < (lead ? lead : ep->nurbs); i++) {', patched)
        self.assertIn('if (!i && !lead) {', patched)
        self.assertIn('ep->chip->usb_id != USB_ID(0x0dba, 0xb011)', patched)
        with self.assertRaises(RuntimeError):
            prepare.eleven_playback_lead(endpoint.replace('No URB submission due to implicit fb sync',
                                                          'Changed upstream message'))

    def test_eleven_stats_apply_to_clean_source_and_reject_unknown_layout(self):
        archive = Path('/usr/src/linux-source-7.0.0.tar.bz2')
        if not archive.exists():
            self.skipTest('Ubuntu 7.0 kernel source archive not installed')
        names = ('usbaudio.h', 'card.h', 'endpoint.c', 'proc.c')
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(['tar', '-xjf', str(archive), '-C', tmp,
                            *[f'linux-source-7.0.0/sound/usb/{n}' for n in names]], check=True)
            usbaudio, card, endpoint, proc = (
                (Path(tmp)/'linux-source-7.0.0/sound/usb'/n).read_text() for n in names)
        new_usbaudio, new_card, new_endpoint, new_proc = prepare.eleven_stats(
            usbaudio, card, prepare.eleven_playback_lead(endpoint), proc)
        self.assertIn('atomic_t eleven_playback_gaps;', new_usbaudio)
        self.assertIn('atomic_inc(&ep->chip->eleven_xruns[!usb_pipeout(ep->pipe)]);\n\t\tsnd_pcm_stop_xrun(psubs);', new_endpoint)
        self.assertIn('atomic_inc(&ep->chip->eleven_starts[!is_playback]);', new_endpoint)
        self.assertIn('\t} else {\n\t\televen_count_capture(ep, urb);\n\t\tretire_inbound_urb(ep, ctx);', new_endpoint)
        self.assertIn('int eleven_level_min;', new_card)
        # The queue level is sampled at each implicit-feedback playback completion.
        self.assertIn('\t\t\t\tnotify_xrun(ep);\n\t\t\tif (snd_usb_endpoint_implicit_feedback_sink(ep))\n'
                      '\t\t\t\televen_track_level(ep, ctx->packets);\n\t\t\treturn;', new_endpoint)
        self.assertIn('\tep->sample_accum = 0;\n\tep->eleven_samples = ep->eleven_windows = 0;\n'
                      '\tep->eleven_capture_urbs = 0;', new_endpoint)
        self.assertIn('if (ep->eleven_capture_urbs < ELEVEN_CAPTURE_SETTLE_URBS) {', new_endpoint)
        self.assertIn('if (chip->usb_id != USB_ID(0x0dba, 0xb011) || !ep_state_running(ep))', new_endpoint)
        # The upstream xrun path for other devices is untouched.
        self.assertIn('if (atomic_dec_and_test(&ep->submitted_urbs) &&\n\t\t\t    !snd_usb_endpoint_implicit_feedback_sink(ep))', new_endpoint)
        self.assertIn('"eleven_stats"', new_proc)
        self.assertIn('if (chip->usb_id == USB_ID(0x0dba, 0xb011))', new_proc)
        with self.assertRaises(RuntimeError):
            prepare.eleven_stats(usbaudio, card, endpoint.replace(
                'snd_pcm_stop_xrun(psubs);', 'stop_for_xrun(psubs);'), proc)

    def test_unrecognized_function_layout_is_rejected(self):
        with self.assertRaises(ValueError):
            prepare.eleven_rack_attributes(QUIRK.replace('snd_usb_audioformat_attributes_quirk', 'other'))


if __name__ == '__main__':
    unittest.main()

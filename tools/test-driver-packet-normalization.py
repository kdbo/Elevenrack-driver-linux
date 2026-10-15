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

    def test_unrecognized_function_layout_is_rejected(self):
        with self.assertRaises(ValueError):
            prepare.eleven_rack_attributes(QUIRK.replace('snd_usb_audioformat_attributes_quirk', 'other'))


if __name__ == '__main__':
    unittest.main()

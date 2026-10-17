#!/usr/bin/env python3
"""Device isolation tests: selection, unplugging, MIDI routing and caching."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import rack_devices

spec=importlib.util.spec_from_file_location('settings',Path(__file__).with_name('eleven-rack-settings.py'))
settings=importlib.util.module_from_spec(spec);spec.loader.exec_module(settings)

A={'id':'usb:a','card':1,'card_id':'Rack'}
B={'id':'usb:b','card':2,'card_id':'Rack_1'}

class DeviceTests(unittest.TestCase):
    def test_ambiguous_default_and_explicit_selection(self):
        with patch.object(rack_devices,'devices',return_value=[A,B]):
            with self.assertRaisesRegex(RuntimeError,'Multiple'):
                rack_devices.select()
            self.assertEqual(B,rack_devices.select('Rack_1'))
            self.assertEqual(A,rack_devices.select('usb:a'))
        with patch.object(rack_devices,'devices',return_value=[B]):
            self.assertEqual(B,rack_devices.select())
            with self.assertRaisesRegex(RuntimeError,'disconnected'):
                rack_devices.select('usb:a')

    def test_usb_identity_does_not_follow_card_renumbering(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);proc=root/'proc';sound=root/'sound';usb=root/'usb'/'1-9';interface=usb/'1-9:1.1'
            interface.mkdir(parents=True);(usb/'idVendor').write_text('0dba');(usb/'idProduct').write_text('b011')
            (usb/'serial').write_text('duplicate')
            for n in [1,2]:
                card=proc/f'card{n}';card.mkdir(parents=True);(card/'usbid').write_text('0dba:b011');(card/'id').write_text(f'Rack{n}')
                node=sound/f'card{n}';node.mkdir(parents=True);(node/'device').symlink_to(interface)
            found=rack_devices.devices(proc,sound)
            self.assertEqual(found[0]['id'],found[1]['id'])
            self.assertTrue(found[0]['id'].startswith('usb:'))

    def test_selected_mixer_and_cache_are_isolated(self):
        with patch.object(rack_devices,'devices',return_value=[A,B]):
            paths=[]
            for device in [A,B]:
                with patch.dict(os.environ,{'ELEVEN_RACK_DEVICE':device['id']}):
                    self.assertEqual(device['card'],settings.card())
                    paths.append(settings.firmware_cache_path())
            self.assertNotEqual(*paths)
        with patch.object(rack_devices,'devices',return_value=[B]),patch.dict(os.environ,{'ELEVEN_RACK_DEVICE':'usb:a'}):
            with self.assertRaises(RuntimeError):settings.card()

    def test_port_identity_uses_client_not_name(self):
        self.assertEqual(B,rack_devices.port_device('Eleven Rack Rig 24:0',{20:A,24:B}))
        self.assertIsNone(rack_devices.port_device('Eleven Rack Rig',{}))

if __name__=='__main__':unittest.main()

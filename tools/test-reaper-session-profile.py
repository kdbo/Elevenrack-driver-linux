#!/usr/bin/env python3
"""Verify session offsets and isolation of the ordinary REAPER profile."""
import configparser
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('profile', Path(__file__).with_name('reaper-session-profile.py'))
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


class ProfileTest(unittest.TestCase):
    def test_new_session_replaces_offset_without_changing_normal_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root/'normal'
            source.mkdir()
            original = '[REAPER]\nadjrecmanlatin=205\nadjrecmanlat=19\nlastproject=/tmp/test.RPP\n'
            (source/'reaper.ini').write_text(original)
            (source/'Effects').mkdir()
            (source/'Effects/custom.jsfx').write_text('test resource')
            destination = root/'calibrated'
            config = profile.prepare(destination, 197, source)
            profile.prepare(destination, 223, source)
            saved = configparser.RawConfigParser()
            saved.read(config)
            self.assertEqual(saved.getint('REAPER', 'adjrecmanlatin'), 223)
            self.assertEqual(saved.getint('REAPER', 'adjrecmanlat'), 0)
            self.assertEqual(saved.getint('REAPER', 'adjreclat'), 1)
            self.assertEqual(saved.get('REAPER', 'lastproject'), '/tmp/test.RPP')
            self.assertEqual((source/'reaper.ini').read_text(), original)
            self.assertEqual((destination/'Effects/custom.jsfx').read_text(), 'test resource')

    def test_unowned_profile_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp)
            config = destination/'reaper.ini'
            config.write_text('[REAPER]\nadjrecmanlatin=205\n')
            with self.assertRaises(RuntimeError):
                profile.prepare(destination, 200)
            self.assertEqual(config.read_text(), '[REAPER]\nadjrecmanlatin=205\n')


if __name__ == '__main__':
    unittest.main()

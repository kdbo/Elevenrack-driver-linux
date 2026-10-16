#!/usr/bin/env python3
"""Exercise preservation of existing, absent and invalid rate overrides."""
import importlib.util
from pathlib import Path
import stat
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('matrix', Path(__file__).with_name('test-full-latency-matrix.py'))
matrix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(matrix)


class OverrideRestoration(unittest.TestCase):
    def test_existing_config_bytes_permissions_and_backup_survive_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root/'override.conf'
            original = b'# existing user config\r\naudio.rate = 88200\r\n'
            path.write_bytes(original)
            path.chmod(0o640)
            override = matrix.RateOverride(path, root)
            with self.assertRaisesRegex(RuntimeError, 'recording failed'):
                try:
                    path.write_text('audio.rate = 48000\n')
                    path.chmod(0o600)
                    raise RuntimeError('recording failed')
                finally:
                    override.restore()
            self.assertTrue(override.restored())
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)
            self.assertEqual((root/'original-rate-override.conf').read_bytes(), original)

    def test_absent_config_is_removed_and_can_be_restored_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'override.conf'
            override = matrix.RateOverride(path, Path(tmp))
            path.write_text('temporary')
            override.restore()
            override.restore()
            self.assertTrue(override.restored())
            self.assertFalse(path.exists())

    def test_empty_existing_file_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'override.conf'
            path.touch()
            override = matrix.RateOverride(path, Path(tmp))
            path.write_text('temporary')
            override.restore()
            self.assertTrue(path.exists())
            self.assertEqual(path.read_bytes(), b'')

    def test_symlink_is_rejected_without_changing_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            target, path = Path(tmp)/'target', Path(tmp)/'override.conf'
            target.write_text('original')
            path.symlink_to(target)
            with self.assertRaisesRegex(RuntimeError, 'regular file'):
                matrix.RateOverride(path, Path(tmp))
            self.assertEqual(target.read_text(), 'original')


if __name__ == '__main__':
    unittest.main()

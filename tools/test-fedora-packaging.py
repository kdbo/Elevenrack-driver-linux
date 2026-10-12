#!/usr/bin/env python3
"""Check Fedora source guards and scriptlets without touching audio or DKMS."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fedora', ROOT/'tools/build-fedora-package-set.py')
fedora = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fedora)


class FedoraPackaging(unittest.TestCase):
    def test_scripts_target_explicit_kernel_not_runner(self):
        text = fedora.driver_scripts('0.1.2~beta8', '7.0.1-1.fc44.x86_64')
        self.assertNotIn('uname', text)
        for action in ('build', 'install'):
            self.assertIn(f'dkms {action} -m eleven-rack -v 0.1.2~beta8 -k 7.0.1-1.fc44.x86_64', text)
        for section in text.split('%')[1:]:
            body = section.split('\n', 1)[1]
            subprocess.run(['sh', '-n'], input=body, text=True, check=True)

    def test_config_preservation_and_kernel_pin(self):
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary)
            fedora.write(stage, 'etc/wireplumber/test.conf', 'test')
            fedora.write(stage, 'usr/bin/test', 'test')
            text = fedora.spec('eleven-rack-driver', '0.1.2~beta8', stage,
                               ['kernel-devel = 7.0.1-1.fc44'])
            self.assertIn('%config(noreplace) /etc/wireplumber/test.conf', text)
            self.assertIn('Requires: kernel-devel = 7.0.1-1.fc44', text)
            self.assertIn('/usr/bin/test', text)

    def test_editor_rejects_incomplete_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(RuntimeError, 'Missing built Editor'):
                fedora.editor_payload(Path(temporary)/'stage', Path(temporary))

    def test_kernel_mismatch_fails_before_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            script = root/'build-driver.sh'
            script.write_text((ROOT/'packaging/fedora/build-driver.sh').read_text())
            (root/'prepared-kernel').mkdir()
            (root/'prepared-kernel/kernel-release').write_text('7.0.1-1.fc44.x86_64\n')
            result = subprocess.run(['bash', str(script), '7.0.2-1.fc44.x86_64'], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('not 7.0.2-1.fc44.x86_64', result.stderr)


if __name__ == '__main__':
    unittest.main()

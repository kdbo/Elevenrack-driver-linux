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
    def test_bundled_rtmidi_uses_host_python_abi(self):
        import sys
        dependencies = fedora.editor_dependencies()
        self.assertNotIn('python3-rtmidi', dependencies)
        self.assertIn(f'python(abi) = {sys.version_info.major}.{sys.version_info.minor}', dependencies)

    def test_editor_requires_bundled_rtmidi(self):
        with tempfile.TemporaryDirectory() as temporary:
            editor = Path(temporary)/'editor'
            for name in ('eleven-rack-editor-linux', 'resources/app.asar', 'resources/bridge-linux/bridge.py'):
                fedora.write(editor, name, 'test')
            with self.assertRaisesRegex(RuntimeError, 'rtmidi/__init__.py'):
                fedora.editor_payload(Path(temporary)/'stage', editor)

    def test_scripts_target_explicit_kernel_not_runner(self):
        text = fedora.driver_scripts('0.1.2~beta8', '7.0.1-1.fc44.x86_64')
        self.assertNotIn('uname', text)
        for action in ('build', 'install'):
            self.assertIn(f'dkms {action} -m eleven-rack -v 0.1.2~beta8 -k "$kernel" --kernelsourcedir "/usr/src/kernels/$kernel"', text)
        self.assertIn('for kernel in 7.0.1-1.fc44.x86_64; do', text)
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

    def test_additional_kernel_selects_its_own_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            script = root/'build-driver.sh'
            script.write_text((ROOT/'packaging/fedora/build-driver.sh').read_text())
            (root/'prepared-kernel').mkdir()
            (root/'prepared-kernel/kernel-release').write_text('7.2.9-201.fc44.x86_64\n')
            old = root/'prepared-kernels/6.19.10-300.fc44.x86_64'
            old.mkdir(parents=True)
            (old/'kernel-release').write_text('6.19.10-300.fc44.x86_64\n')
            (root/'build-driver-common.sh').write_text('#!/bin/bash\nprintf "%s\\n" "$1" "$2" "$3"\n')
            result = subprocess.run(['bash', str(script), '6.19.10-300.fc44.x86_64', '/test/headers'], capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout.splitlines(), ['6.19.10-300.fc44.x86_64', '/test/headers', str(old/'sound/usb')])

    def test_scriptlets_build_all_bundled_kernels(self):
        text = fedora.driver_scripts('0.1.2~beta8', ['6.19.10-300.fc44.x86_64', '7.2.9-201.fc44.x86_64'])
        self.assertIn('for kernel in 6.19.10-300.fc44.x86_64 7.2.9-201.fc44.x86_64; do', text)
        for section in text.split('%')[1:]:
            subprocess.run(['sh', '-n'], input=section.split('\n', 1)[1], text=True, check=True)


if __name__ == '__main__':
    unittest.main()

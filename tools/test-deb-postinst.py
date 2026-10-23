#!/usr/bin/env python3
"""Run the Ubuntu postinst against fake kernels and a fake dkms, without touching the system."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def run_postinst(running, kernels):
    """kernels: {release: 'ok' | 'fails' | 'old' | 'no-headers'}; returns (result, dkms calls)."""
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for kernel, state in kernels.items():
            (root/'modules'/kernel).mkdir(parents=True)
            if state != 'no-headers':
                (root/'modules'/kernel/'build').mkdir()
                (root/'modules'/kernel/'build/Makefile').write_text('')
        failing = ' '.join(k for k, s in kernels.items() if s == 'fails')
        old = ' '.join(k for k, s in kernels.items() if s == 'old')
        bin = root/'bin'
        bin.mkdir()
        scripts = {
            'uname': f'echo {running}',
            'dkms': (f'echo "$*" >> {root}/dkms.log\n'
                     f'for k in {failing}; do [ "$1" = build ] && [ "$7" = "$k" ] && exit 10; done\n'
                     f'for k in {old}; do [ "$1" = build ] && [ "$7" = "$k" ] && exit 77; done\nexit 0'),
            'update-initramfs': 'exit 0',
        }
        for name, body in scripts.items():
            (bin/name).write_text('#!/bin/sh\n'+body+'\n')
            (bin/name).chmod(0o755)
        text = (ROOT/'packaging/postinst').read_text().replace('@VERSION@', '0.1.2~beta16')
        text = text.replace('/lib/modules/', f'{root}/modules/').replace('/var/lib/dkms/', f'{root}/dkms/')
        env = {**os.environ, 'PATH': f'{bin}:{os.environ["PATH"]}'}
        result = subprocess.run(['sh', '-c', text, 'postinst', 'configure'], capture_output=True, text=True, env=env)
        log = (root/'dkms.log').read_text() if (root/'dkms.log').exists() else ''
        return result, log


class UbuntuPostinst(unittest.TestCase):
    def test_failing_old_kernel_does_not_block_the_running_one(self):
        result, log = run_postinst('7.0.0-38-generic', {'6.17.0-40-generic': 'fails', '7.0.0-38-generic': 'ok'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('install -m eleven-rack -v 0.1.2~beta16 -k 7.0.0-38-generic', log)
        self.assertIn('  6.17.0-40-generic: NOT built', result.stdout)
        self.assertIn('  7.0.0-38-generic: ready', result.stdout)
        self.assertIn('remove the headers of kernels you no longer use', result.stdout)
        self.assertIn('Reboot to activate', result.stdout)

    def test_running_kernel_failure_stops_configuration(self):
        result, _ = run_postinst('7.0.0-38-generic', {'7.0.0-38-generic': 'fails', '7.0.0-40-generic': 'ok'})
        self.assertEqual(result.returncode, 1)
        self.assertIn('  7.0.0-40-generic: ready', result.stdout)
        self.assertIn('sudo dpkg --configure -a', result.stderr)
        self.assertNotIn('Reboot to activate', result.stdout)

    def test_unsupported_and_headerless_kernels(self):
        result, log = run_postinst('7.0.0-38-generic', {'6.5.0-1-generic': 'old', '7.0.0-38-generic': 'no-headers'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('  6.5.0-1-generic: not supported', result.stdout)
        self.assertNotIn('-k 7.0.0-38-generic', log)
        self.assertIn('install linux-headers-7.0.0-38-generic', result.stderr)

    def test_registers_sources_once(self):
        _, log = run_postinst('7.0.0-38-generic', {'7.0.0-38-generic': 'ok'})
        self.assertEqual(log.splitlines()[0], 'add -m eleven-rack -v 0.1.2~beta16')


if __name__ == '__main__':
    unittest.main()

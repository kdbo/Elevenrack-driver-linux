#!/usr/bin/env python3
"""Regression checks for automatic HWE source preparation (no network or root)."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('fetch_source', ROOT / 'packaging/fetch-kernel-source.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class SourceTests(unittest.TestCase):
    def test_deb822_preserves_signing_and_mirror(self):
        text = ('Types: deb\n deb-src\nURIs: https://example.test/ubuntu\n'
                'Suites: noble noble-updates\nComponents: main\n'
                'Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n')
        converted = helper.source_entries(text, True)
        self.assertIn('Types: deb-src\nURIs:', converted)
        self.assertIn('Suites: noble noble-updates', converted)
        self.assertIn('Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg', converted)

    def test_disabled_and_unsigned_entries_are_excluded(self):
        for field in ('Enabled: no', 'Trusted: yes', 'Allow-Insecure: yes', 'Allow-Weak: yes'):
            self.assertEqual('', helper.source_entries(f'Types: deb\n{field}\n', True))
        self.assertEqual('', helper.source_entries('deb [trusted=yes] https://example.test noble main', False))

    def test_legacy_lists_preserve_options(self):
        converted = helper.source_entries(
            '# deb https://disabled.test noble main\n'
            'deb [signed-by=/key.gpg] https://example.test noble main\n', False)
        self.assertEqual('deb-src [signed-by=/key.gpg] https://example.test noble main\n', converted)

    def test_identifies_exact_hwe_version(self):
        result = subprocess.CompletedProcess([], 0, 'installed linux-hwe-7.0 7.0.0-38.38~24.04.4', '')
        with patch.object(helper.subprocess, 'run', return_value=result):
            self.assertEqual(('linux-hwe-7.0', '7.0.0-38.38~24.04.4'), helper.kernel_source('7.0.0-38-generic'))

    def test_unknown_kernel_fails(self):
        result = subprocess.CompletedProcess([], 1, '', 'not installed')
        with patch.object(helper.subprocess, 'run', return_value=result):
            with self.assertRaises(RuntimeError):
                helper.kernel_source('7.0.0-38-generic')

    def test_cache_avoids_network(self):
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp)
            archive = cache / 'linux-hwe-7.0_7.0.0-38.38~24.04.4.tar.bz2'
            archive.write_bytes(b'cached')
            with patch.object(helper.subprocess, 'run') as run:
                self.assertEqual(archive, helper.fetch('linux-hwe-7.0', '7.0.0-38.38~24.04.4', cache, cache))
                run.assert_not_called()

    def test_failed_download_does_not_create_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / 'apt'
            config.mkdir()
            (config / 'sources.list').write_text('deb https://example.test noble main\n')
            with patch.object(helper.subprocess, 'run', side_effect=subprocess.CalledProcessError(100, 'apt-get')):
                with self.assertRaises(subprocess.CalledProcessError):
                    helper.fetch('linux-hwe-7.0', '7.0.0-38.38~24.04.4', config, root / 'cache')
            self.assertEqual([], list((root / 'cache').iterdir()))

    def test_fetch_uses_isolated_authenticated_apt_and_keeps_config(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / 'apt/sources.list.d'
            config.mkdir(parents=True)
            original = 'Types: deb\nURIs: https://example.test\nSuites: noble\nComponents: main\nSigned-By: /key.gpg\n'
            (config / 'ubuntu.sources').write_text(original)
            calls = []

            def simulate(command, **kwargs):
                calls.append(command)
                work = Path(kwargs['cwd'])
                if command[0] == 'apt-get':
                    self.assertIn('APT::Get::AllowUnauthenticated=false', command)
                    self.assertIn(f'Dir::State::lists={work / "lists"}', command)
                    self.assertIn('Types: deb-src', (work / 'sources.list.d/repo-0.sources').read_text())
                    if 'source' in command:
                        self.assertEqual('linux-hwe-7.0=7.0.0-38.38~24.04.4', command[-1])
                        (work / 'kernel.dsc').write_text('fixture')
                else:
                    usb = Path(command[-1]) / 'sound/usb'
                    usb.mkdir(parents=True)
                    (usb / 'Makefile').write_text('fixture')

            with patch.object(helper.subprocess, 'run', side_effect=simulate):
                archive = helper.fetch('linux-hwe-7.0', '7.0.0-38.38~24.04.4', root / 'apt', root / 'cache')
            self.assertTrue(archive.is_file())
            self.assertEqual(original, (config / 'ubuntu.sources').read_text())
            self.assertEqual(3, len(calls))


if __name__ == '__main__':
    unittest.main()

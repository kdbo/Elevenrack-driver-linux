#!/usr/bin/env python3
"""Check universal backend selection, upgrade failure cleanup and source integrity."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('installer', ROOT / 'tools/install-latency-backend.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class UniversalBackendTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'source'
        self.destination = self.root / 'installation'
        for folder in ('archives', 'packaging', 'config', 'tools'):
            (self.source / folder).mkdir(parents=True)
        archive = self.source / 'archives/pipewire-1.0.5.tar.gz'
        archive.write_bytes(b'fixture archive')
        (self.source / 'packaging/pipewire-sources.json').write_text(json.dumps({
            '1.0.5': {'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}}))
        (self.source / 'packaging/pipewire-eleven-latency.patch').write_text('fixture patch')
        (self.source / 'config/52-eleven-rack-latency.conf').write_text('fixture defaults')
        (self.source / 'tools/spa-eleven-alsa.c').write_text('fixture wrapper')
        (self.source / 'tools/build-latency-backend.py').write_text('fixture builder')
        self.detected = SimpleNamespace(installed_version=lambda: '1.0.5',
                                        plugin_directory=lambda: Path('/usr/lib/test/spa-0.2'))

    def compile(self, command, **kwargs):
        if command[1].endswith('build-latency-backend.py'):
            self.assertEqual(Path(command[command.index('--archive') + 1]).name, 'pipewire-1.0.5.tar.gz')
            output = Path(command[command.index('--output') + 1])
            library = output / 'libspa-eleven-latency.so'
            library.write_bytes(b'fixture compiled backend')
            metadata = {'pipewire_version': '1.0.5', 'spa_plugin_dir': '/usr/lib/test/spa-0.2',
                        'source_sha256': hashlib.sha256((self.source / 'archives/pipewire-1.0.5.tar.gz').read_bytes()).hexdigest(),
                        'library_sha256': hashlib.sha256(library.read_bytes()).hexdigest(),
                        'patch_sha256': hashlib.sha256((self.source / 'packaging/pipewire-eleven-latency.patch').read_bytes()).hexdigest(),
                        'correction_config_sha256': hashlib.sha256((self.source / 'config/52-eleven-rack-latency.conf').read_bytes()).hexdigest()}
            (output / 'backend-build.json').write_text(json.dumps(metadata))

    def test_detects_backend_and_reuses_only_matching_build(self):
        with patch.object(installer, 'builder', return_value=self.detected), patch.object(installer.subprocess, 'run', side_effect=self.compile) as run:
            installer.install(self.source, self.destination)
            self.assertEqual(run.call_count, 2)
            run.reset_mock()
            installer.install(self.source, self.destination)
            run.assert_not_called()
            (self.source / 'tools/spa-eleven-alsa.c').write_text('updated wrapper')
            installer.install(self.source, self.destination)
            self.assertEqual(run.call_count, 2)
        dropin = self.destination / installer.GENERATED[1]
        self.assertIn('/usr/lib/eleven-rack/spa:/usr/lib/test/spa-0.2', dropin.read_text())

    def test_corrupt_archive_is_rejected_before_compilation(self):
        (self.source / 'archives/pipewire-1.0.5.tar.gz').write_bytes(b'corrupt')
        with patch.object(installer, 'builder', return_value=self.detected), patch.object(installer.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'checksum mismatch'):
                installer.install(self.source, self.destination)
            run.assert_not_called()

    def test_unknown_version_requests_package_update_without_version_prompt(self):
        detected = SimpleNamespace(installed_version=lambda: '9.9.9', plugin_directory=self.detected.plugin_directory)
        with patch.object(installer, 'builder', return_value=detected):
            with self.assertRaisesRegex(RuntimeError, 'updated Eleven Rack driver package'):
                installer.install(self.source, self.destination)

    def test_removal_leaves_other_audio_files_untouched(self):
        for name in installer.GENERATED:
            target = self.destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('generated')
        other = self.destination / 'usr/lib/systemd/user/pipewire.service.d/custom.conf'
        other.write_text('user settings')
        installer.remove(self.destination)
        self.assertTrue(other.exists())
        self.assertTrue(all(not (self.destination / name).exists() for name in installer.GENERATED))

    def test_failed_cli_install_disables_previous_backend(self):
        # An empty catalog rejects any installed version without compiling or fetching.
        (self.source / 'packaging/pipewire-sources.json').write_text('{}')
        for name in installer.GENERATED:
            target = self.destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('old backend')
        result = subprocess.run([sys.executable, str(ROOT / 'tools/install-latency-backend.py'),
                                 '--source-root', str(self.source), '--destination', str(self.destination)],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('backend installation failed', result.stderr)
        self.assertTrue(all(not (self.destination / name).exists() for name in installer.GENERATED))


if __name__ == '__main__':
    unittest.main()

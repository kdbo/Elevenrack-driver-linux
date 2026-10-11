#!/usr/bin/env python3
"""Check packaging guards and target configuration without root, network or audio hardware."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('backend_package', ROOT / 'tools/build-latency-package.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)
build_spec = importlib.util.spec_from_file_location('backend_build', ROOT / 'tools/build-latency-backend.py')
builder = importlib.util.module_from_spec(build_spec)
build_spec.loader.exec_module(builder)


class VersionTests(unittest.TestCase):
    def test_runtime_version_takes_precedence_over_development_headers(self):
        with patch.object(builder, 'run', return_value=(
                'pipewire\nCompiled with libpipewire 1.6.2\nLinked with libpipewire 1.6.9')) as command:
            self.assertEqual('1.6.9', builder.installed_version())
            command.assert_called_once_with('pipewire', '--version')

    def test_missing_runtime_uses_development_metadata(self):
        with patch.object(builder, 'run', side_effect=[FileNotFoundError('pipewire'), '1.6.9']) as command:
            self.assertEqual('1.6.9', builder.installed_version())
            self.assertEqual(('pkg-config', '--modversion', 'libpipewire-0.3'), command.call_args.args)

    def test_missing_version_has_actionable_error(self):
        with patch.object(builder, 'run', side_effect=FileNotFoundError()):
            with self.assertRaisesRegex(RuntimeError, 'install pipewire'):
                builder.installed_version()


class PackageTests(unittest.TestCase):
    def fixture(self, root, spa='/usr/lib64/spa-0.2'):
        build = root / 'build'
        build.mkdir()
        data = b'fixture library'
        (build / 'libspa-eleven-latency.so').write_bytes(data)
        metadata = {'library_sha256': hashlib.sha256(data).hexdigest(),
                    'pipewire_version': '1.6.9', 'machine': 'x86_64',
                    'spa_plugin_dir': spa, 'system_alsa_plugin': spa + '/alsa/libspa-alsa.so'}
        for field, path in (
                ('patch_sha256', ROOT / 'packaging/pipewire-eleven-latency.patch'),
                ('correction_config_sha256', ROOT / 'config/52-eleven-rack-latency.conf')):
            metadata[field] = hashlib.sha256(path.read_bytes()).hexdigest()
        (build / 'backend-build.json').write_text(json.dumps(metadata))
        return build, metadata

    def test_tampered_library_cannot_be_packaged(self):
        with tempfile.TemporaryDirectory() as directory:
            build, _ = self.fixture(Path(directory))
            (build / 'libspa-eleven-latency.so').write_bytes(b'other build')
            with self.assertRaisesRegex(RuntimeError, 'metadata'):
                package.check_build(build)

    def test_package_cannot_target_different_architecture(self):
        with tempfile.TemporaryDirectory() as directory:
            build, _ = self.fixture(Path(directory))
            with patch.object(package, 'read_command', return_value='aarch64'):
                with self.assertRaisesRegex(RuntimeError, 'architecture'):
                    package.check_build(build)

    def test_native_dependency_retains_epoch_and_rejects_wrong_upstream(self):
        metadata = {'pipewire_version': '1.6.9'}
        with patch.object(package, 'read_command', return_value='pipewire 1:1.6.9-1'):
            self.assertEqual('1:1.6.9-1', package.dependency_version('arch', metadata))
        with patch.object(package, 'read_command', return_value='0:1.6.9-1.fc44'):
            self.assertEqual('0:1.6.9-1.fc44', package.dependency_version('rpm', metadata))
        with patch.object(package, 'read_command', return_value='1.6.2-1ubuntu1.2'):
            with self.assertRaisesRegex(RuntimeError, 'installed PipeWire'):
                package.dependency_version('deb', metadata)

    def test_distro_paths_preserve_defaults_and_stock_factories(self):
        for spa in ('/usr/lib/spa-0.2', '/usr/lib64/spa-0.2', '/usr/lib/x86_64-linux-gnu/spa-0.2'):
            with self.subTest(spa=spa), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                build, metadata = self.fixture(root, spa)
                stage = root / 'stage'
                package.stage_payload(stage, build, metadata)
                for unit in ('pipewire.service', 'wireplumber.service'):
                    content = (stage / f'usr/lib/systemd/user/{unit}.d/60-eleven-rack-latency.conf').read_text()
                    self.assertIn('SPA_PLUGIN_DIR=/usr/lib/eleven-rack/spa:' + spa, content)
                config = stage / 'etc/wireplumber/wireplumber.conf.d/52-eleven-rack-latency.conf'
                self.assertEqual((ROOT / 'config/52-eleven-rack-latency.conf').read_bytes(), config.read_bytes())
                self.assertFalse((stage / spa.lstrip('/') / 'alsa/libspa-alsa.so').exists())


if __name__ == '__main__':
    unittest.main()

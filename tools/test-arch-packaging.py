#!/usr/bin/env python3
"""Exercise native package staging and two-package validation without an Arch host or hardware."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare_driver = load('prepare_driver', 'prepare-arch-package.py')
prepare_editor = load('prepare_editor', 'prepare-arch-editor.py')
checker = load('check_set', 'check-arch-package-set.py')


class ArchPackageTests(unittest.TestCase):
    def prepare_driver(self, root, release='7.2.9-arch1-1'):
        source = root / 'kernel'
        usb = source / 'sound/usb'
        usb.mkdir(parents=True)
        (source / 'version').write_text(release + '\n')
        (usb / 'Makefile').write_text('# fixture\n')
        (usb / 'quirks-table.h').write_text('/* clean source */\n')
        build = root / 'backend'
        build.mkdir()
        library = build / 'libspa-eleven-latency.so'
        library.write_bytes(b'fixture backend')
        metadata = {'pipewire_version': '1.6.9', 'machine': 'x86_64',
                    'spa_plugin_dir': '/usr/lib/spa-0.2',
                    'system_alsa_plugin': '/usr/lib/spa-0.2/alsa/libspa-alsa.so',
                    'library_sha256': hashlib.sha256(library.read_bytes()).hexdigest()}
        for key, path in (('patch_sha256', ROOT / 'packaging/pipewire-eleven-latency.patch'),
                          ('correction_config_sha256', ROOT / 'config/52-eleven-rack-latency.conf')):
            metadata[key] = hashlib.sha256(path.read_bytes()).hexdigest()
        (build / 'backend-build.json').write_text(json.dumps(metadata))
        output = root / 'driver-inputs'
        argv = ['prepare', '--kernel-source', str(source), '--kernel-release', '7.2.9-arch1-1',
                '--linux-package-version', '7.2.9.arch1-1', '--backend-build', str(build), '--output', str(output)]
        def command(args, **kwargs):
            if args == ('uname', '-m'):
                return 'x86_64\n'
            if args == ('pacman', '-Q', 'pipewire'):
                return 'pipewire 1:1.6.9-1\n'
            raise AssertionError(f'Unexpected command: {args}')
        with patch.object(sys, 'argv', argv), patch.object(subprocess, 'check_output', side_effect=command):
            prepare_driver.main()
        return output

    def editor_fixture(self, root):
        unpacked = root / 'unpacked'
        for name in ('eleven-rack-editor-linux', 'chrome-sandbox', 'resources/app.asar',
                     'resources/eleven-rack-updates.py',
                     'resources/bridge-linux/bridge.py', 'resources/bridge-linux/segmented_sysex.py',
                     'resources/eleven-rack-editor-logo.png', 'resources/LICENSE', 'resources/NOTICE'):
            path = unpacked / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'fixture')
        return unpacked

    def stage(self, inputs, root):
        sources = root / 'src'
        sources.mkdir()
        for archive in inputs.glob('*.tar.gz'):
            with tarfile.open(archive) as bundle:
                bundle.extractall(sources, filter='data')
        stage = root / 'pkg'
        stage.mkdir()
        # Execute the actual PKGBUILD package() with the real install/cp commands.
        subprocess.run(['bash', '-e', '-c', '''
source "$1"
srcdir=$2
pkgdir=$3
package
printf 'pkgname = %s\npkgver = %s-%s\narch = %s\n' "$pkgname" "$pkgver" "$pkgrel" "${arch[0]}" > "$pkgdir/.PKGINFO"
printf 'depend = %s\n' "${depends[@]}" >> "$pkgdir/.PKGINFO"
''', 'stage', str(inputs / 'PKGBUILD'), str(sources), str(stage)], check=True)
        return stage

    def archive(self, stage, output):
        subprocess.run(['tar', '--zstd', '-cf', str(output), '-C', str(stage),
                        *sorted(p.name for p in stage.iterdir())], check=True)

    def test_complete_two_package_set(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            driver = self.prepare_driver(root)
            target = json.loads((driver / 'package-target.json').read_text())
            editor = prepare_editor.prepare(self.editor_fixture(root), root / 'editor-inputs')
            for path in (root / 'driver', root / 'editor', root / 'set'):
                path.mkdir()
            driver_stage = self.stage(driver, root / 'driver')
            editor_stage = self.stage(editor, root / 'editor')
            self.archive(driver_stage, root / 'set/driver.pkg.tar.zst')
            self.archive(editor_stage, root / 'set/editor.pkg.tar.zst')
            checked = checker.check(root / 'set', target)
            self.assertEqual({'eleven-rack-driver', 'eleven-rack-editor-linux'}, set(checked))
            config = (driver_stage / ('usr/src/eleven-rack-' + target['version']) / 'dkms.conf').read_text()
            self.assertIn('BUILD_EXCLUSIVE_KERNEL="^7\\.2\\.9\\-arch1\\-1$"', config)
            self.assertEqual(0o4755, (editor_stage / 'opt/eleven-rack-editor/chrome-sandbox').stat().st_mode & 0o7777)
            # Missing the backend must invalidate a superficially complete driver/editor set.
            (driver_stage / 'usr/lib/eleven-rack/spa/alsa/libspa-alsa.so').unlink()
            self.archive(driver_stage, root / 'set/driver.pkg.tar.zst')
            with self.assertRaises(subprocess.CalledProcessError):
                checker.check(root / 'set', target)

    def test_mismatched_kernel_is_rejected_before_packaging(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SystemExit):
                self.prepare_driver(Path(directory), release='7.2.8-arch1-1')

    def test_editor_requires_bridge_and_segmentation_module(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unpacked = self.editor_fixture(root)
            (unpacked / 'resources/bridge-linux/segmented_sysex.py').unlink()
            with self.assertRaisesRegex(RuntimeError, 'segmented_sysex'):
                prepare_editor.prepare(unpacked, root / 'output')

    def test_extra_backend_package_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('driver', 'editor', 'backend'):
                (root / (name + '.pkg.tar.zst')).touch()
            with self.assertRaisesRegex(RuntimeError, 'exactly two'):
                checker.check(root, {})


if __name__ == '__main__':
    unittest.main()

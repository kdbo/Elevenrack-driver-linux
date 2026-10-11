#!/usr/bin/env python3
"""Check a built package without installing it or loading its driver."""
import argparse
import ast
import hashlib
import json
import re
from pathlib import Path
import subprocess
import tempfile


def check(package, version, with_backend=False):
    arch = subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip() if with_backend else 'all'
    fields = subprocess.check_output(
        ['dpkg-deb', '-f', str(package), 'Package', 'Version', 'Architecture'], text=True)
    assert fields == f'Package: eleven-rack-driver\nVersion: {version}\nArchitecture: {arch}\n', fields
    with tempfile.TemporaryDirectory(prefix='eleven-package-check-') as temp:
        root = Path(temp)
        subprocess.run(['dpkg-deb', '-x', str(package), temp], check=True)
        control = root / 'DEBIAN'
        subprocess.run(['dpkg-deb', '-e', str(package), str(control)], check=True)
        if with_backend:
            metadata = json.loads((root / 'usr/share/doc/eleven-rack-latency-backend/backend-build.json').read_text())
            library = root / 'usr/lib/eleven-rack/spa/alsa/libspa-alsa.so'
            assert hashlib.sha256(library.read_bytes()).hexdigest() == metadata['library_sha256']
            config = root / 'etc/wireplumber/wireplumber.conf.d/52-eleven-rack-latency.conf'
            assert hashlib.sha256(config.read_bytes()).hexdigest() == metadata['correction_config_sha256']
            depends = subprocess.check_output(['dpkg-deb', '-f', str(package), 'Depends'], text=True)
            pw = subprocess.check_output(['dpkg-query', '-W', '-f=${Version}', 'pipewire'], text=True)
            assert f'pipewire (= {pw})' in depends
            assert f'libspa-0.2-modules (= {pw})' in depends
            for unit in ('pipewire.service', 'wireplumber.service'):
                text = (root / f'usr/lib/systemd/user/{unit}.d/60-eleven-rack-latency.conf').read_text()
                assert f'SPA_PLUGIN_DIR=/usr/lib/eleven-rack/spa:{metadata["spa_plugin_dir"]}' in text
            assert '/etc/modprobe.d/eleven-rack-latency.conf' in (control / 'conffiles').read_text()
            lua = (root / 'etc/wireplumber/main.lua.d/52-eleven-rack-latency.lua').read_text()
            defaults = dict(re.findall(r'^\s*(api\.alsa\.eleven-[\w-]+)\s*=\s*(true|-?\d+)\s*$', config.read_text(), re.M))
            lua_defaults = dict(re.findall(r'\["(api\.alsa\.eleven-[\w-]+)"\]\s*=\s*(true|-?\d+)', lua))
            assert len(defaults) == 26 and defaults == lua_defaults, 'WirePlumber 0.4 defaults differ'
            assert '"api.alsa.card.id", "equals", "Rack"' in lua
        for line in (control / 'md5sums').read_text().splitlines():
            expected, filename = line.split('  ', 1)
            assert hashlib.md5((root / filename).read_bytes(), usedforsecurity=False).hexdigest() == expected, filename
        for name in ('postinst', 'prerm', 'postrm'):
            script = control / name
            assert script.stat().st_mode & 0o111, name
            assert '@VERSION@' not in script.read_text(), name
            subprocess.run(['sh', '-n', str(script)], check=True)
        source = root / f'usr/src/eleven-rack-{version}'
        assert f'PACKAGE_VERSION="{version}"' in (source / 'dkms.conf').read_text()
        assert '@VERSION@' not in (source / 'dkms.conf').read_text()
        for name in ('build-driver.sh', 'build-driver-common.sh', 'prepare-driver.py', 'fetch-kernel-source.py'):
            assert (source / name).stat().st_mode & 0o111, name
        assert (source / 'mixer-eleven-rack.h').is_file()
        for path in root.rglob('*.py'):
            ast.parse(path.read_text(), filename=str(path))
        launcher = root / 'usr/share/applications/eleven-rack-driver.desktop'
        subprocess.run(['desktop-file-validate', str(launcher)], check=True)
        assert 'Name=Eleven Rack Control\n' in launcher.read_text()
        icon = root / 'usr/share/pixmaps/eleven-rack-driver.png'
        assert icon.read_bytes() == (root / 'usr/lib/eleven-rack/assets/eleven-rack-control-logo-v2.png').read_bytes()
        assert (root / 'usr/bin/eleven-rack-control').stat().st_mode & 0o111
        for path in root.rglob('*'):
            assert path.stat().st_mode & 0o004, f'Not world-readable: {path}'
            if path.is_dir():
                assert path.stat().st_mode & 0o001, f'Not traversable: {path}'
    print(f'Package checks passed: {package}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--version', required=True)
    parser.add_argument('--with-backend', action='store_true')
    args = parser.parse_args()
    check(args.package, args.version, args.with_backend)

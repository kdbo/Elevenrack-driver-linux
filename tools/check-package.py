#!/usr/bin/env python3
"""Check a built package without installing it or loading its driver."""
import argparse
import ast
import hashlib
from pathlib import Path
import subprocess
import tempfile


def check(package, version):
    fields = subprocess.check_output(
        ['dpkg-deb', '-f', str(package), 'Package', 'Version', 'Architecture'], text=True)
    assert fields == f'Package: eleven-rack-driver\nVersion: {version}\nArchitecture: all\n', fields
    with tempfile.TemporaryDirectory(prefix='eleven-package-check-') as temp:
        root = Path(temp)
        subprocess.run(['dpkg-deb', '-x', str(package), temp], check=True)
        control = root / 'DEBIAN'
        subprocess.run(['dpkg-deb', '-e', str(package), str(control)], check=True)
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
        for name in ('build-driver.sh', 'prepare-driver.py', 'fetch-kernel-source.py'):
            assert (source / name).stat().st_mode & 0o111, name
        for path in root.rglob('*.py'):
            ast.parse(path.read_text(), filename=str(path))
        launcher = root / 'usr/share/applications/eleven-rack-driver.desktop'
        subprocess.run(['desktop-file-validate', str(launcher)], check=True)
        assert 'Name=Eleven Rack Control\n' in launcher.read_text()
        icon = root / 'usr/share/pixmaps/eleven-rack-driver.png'
        assert icon.read_bytes() == (root / 'usr/lib/eleven-rack/assets/eleven-rack-linux-logo-v1.png').read_bytes()
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
    args = parser.parse_args()
    check(args.package, args.version)

#!/usr/bin/env python3
"""Inspect the complete Fedora RPM set before installation/publication."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import subprocess
import tempfile


def query(package, *args):
    return subprocess.check_output(['rpm', '-qp', *args, str(package)], text=True).strip()


def check(directory):
    target = json.loads((directory/'package-target.json').read_text())
    packages = list(directory.glob('*.rpm'))
    if len(packages) != 2:
        raise RuntimeError('Expected exactly two RPMs')
    names = {}
    for package in packages:
        name = query(package, '--qf', '%{NAME}')
        if name in names or query(package, '--qf', '%{VERSION}') != target['version']:
            raise RuntimeError('Duplicate package or version mismatch')
        if query(package, '--qf', '%{ARCH}') != 'x86_64':
            raise RuntimeError('Expected native x86_64 RPMs')
        names[name] = package
    if set(names) != {'eleven-rack-driver', 'eleven-rack-editor-linux'}:
        raise RuntimeError('Expected complete driver and Editor')
    driver = names['eleven-rack-driver']
    dependencies = query(driver, '--requires').splitlines()
    for dependency in ('kernel-devel = '+target['kernel_devel_version'],
                       'pipewire = '+target['pipewire_package_version'],
                       'pipewire-libs = '+target['pipewire_package_version']):
        if dependency not in dependencies:
            raise RuntimeError('Missing exact dependency: '+dependency)
    source = '/usr/src/eleven-rack-'+target['version']
    files = query(driver, '--list').splitlines()
    for name in ('/usr/bin/eleven-rack-control', '/usr/lib/eleven-rack/tools/eleven-rack-settings.py',
                 '/usr/lib/eleven-rack/tools/eleven-rack-panel.py',
                 '/usr/lib/eleven-rack/spa/alsa/libspa-alsa.so',
                 '/etc/wireplumber/wireplumber.conf.d/51-eleven-rack.conf',
                 '/etc/wireplumber/wireplumber.conf.d/52-eleven-rack-latency.conf',
                 '/etc/modprobe.d/eleven-rack-latency.conf', source+'/dkms.conf',
                 source+'/prepared-kernel/sound/usb/Makefile'):
        if name not in files:
            raise RuntimeError('Missing driver payload: '+name)
    editor_files = query(names['eleven-rack-editor-linux'], '--list').splitlines()
    for name in ('/usr/bin/eleven-rack-editor-linux',
                 '/usr/share/applications/eleven-rack-editor-linux.desktop',
                 '/opt/eleven-rack-editor/eleven-rack-editor-linux',
                 '/opt/eleven-rack-editor/resources/app.asar',
                 '/opt/eleven-rack-editor/resources/bridge-linux/bridge.py'):
        if name not in editor_files:
            raise RuntimeError('Missing Editor payload: '+name)
    with tempfile.TemporaryDirectory(prefix='fedora-check-') as temporary:
        root = Path(temporary)
        archive = subprocess.Popen(['rpm2cpio', str(driver.resolve())], stdout=subprocess.PIPE)
        try:
            subprocess.run(['cpio', '-idm', '--quiet'], stdin=archive.stdout, cwd=root, check=True)
        finally:
            archive.stdout.close()
        if archive.wait() != 0:
            raise RuntimeError('Cannot extract driver')
        if (root/source.lstrip('/')/'prepared-kernel/kernel-release').read_text().strip() != target['kernel_release']:
            raise RuntimeError('Kernel source mismatch')
        metadata = json.loads((root/'usr/share/doc/eleven-rack-latency-backend/backend-build.json').read_text())
        upstream = re.match(r'(?:\d+:)?(\d+\.\d+\.\d+)', target['pipewire_package_version'])[1]
        if metadata['pipewire_version'] != upstream or metadata['spa_plugin_dir'] != '/usr/lib64/spa-0.2':
            raise RuntimeError('Packaged backend does not match Fedora PipeWire')
        defaults = root/'etc/wireplumber/wireplumber.conf.d/52-eleven-rack-latency.conf'
        if hashlib.sha256(defaults.read_bytes()).hexdigest() != metadata['correction_config_sha256']:
            raise RuntimeError('Packaged correction defaults changed')
        if hashlib.sha256((root/'usr/lib/eleven-rack/spa/alsa/libspa-alsa.so').read_bytes()).hexdigest() != metadata['library_sha256']:
            raise RuntimeError('Backend checksum mismatch')
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=Path('build/fedora-set'))
    args = parser.parse_args()
    target = check(args.directory)
    (args.directory/'README.txt').write_text(f'''Eleven Rack Fedora package set

Exactly two RPMs: eleven-rack-driver and eleven-rack-editor-linux.
Kernel: {target['kernel_release']}
kernel-devel: {target['kernel_devel_version']}
PipeWire: {target['pipewire_package_version']}

Extract the artifact ZIP, then:
  sha256sum --check SHA256SUMS
  sudo dnf install ./*.rpm
  dkms status
  sudo reboot

Run eleven-rack-control gui and eleven-rack-editor-linux after reboot.
Use the matching kernel and PipeWire packages above; rebuild the set before
upgrading them. Fedora hardware latency is not validated; Ubuntu measurement
defaults are included. Secure Boot requires trusting the DKMS signing key.
Container checks establish installation/build compatibility, not USB audio quality.
''')
    print('Verified complete Fedora driver and Editor set')


if __name__ == '__main__':
    main()

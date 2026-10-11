#!/usr/bin/env python3
"""Verify the downloadable Arch set contains exactly one complete driver and one editor."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def read_member(archive, name):
    return subprocess.check_output(['tar', '--zstd', '-xOf', str(archive), name])


def info(archive):
    result = {}
    for line in read_member(archive, '.PKGINFO').decode().splitlines():
        if ' = ' in line:
            key, value = line.split(' = ', 1)
            result.setdefault(key, []).append(value)
    return result


def check(directory, target):
    files = list(directory.glob('*.pkg.tar.*'))
    if len(files) != 2:
        raise RuntimeError(f'Expected exactly two packages, found {len(files)}')
    packages = {}
    for path in files:
        metadata = info(path)
        name = metadata['pkgname'][0]
        if name in packages:
            raise RuntimeError('Duplicate package name')
        if metadata['pkgver'] != [target['version'] + '-1'] or metadata['arch'] != ['x86_64']:
            raise RuntimeError('Package version or architecture mismatch')
        packages[name] = path, metadata
    if set(packages) != {'eleven-rack-driver', 'eleven-rack-editor-linux'}:
        raise RuntimeError('Set must contain the complete driver and editor')
    driver, metadata = packages['eleven-rack-driver']
    for dependency in ('linux=' + target['linux_package_version'],
                       'linux-headers=' + target['linux_package_version'],
                       'pipewire=' + target['pipewire_package_version'],
                       'pipewire-audio=' + target['pipewire_package_version']):
        if dependency not in metadata.get('depend', []):
            raise RuntimeError(f'Missing exact dependency: {dependency}')
    source = 'usr/src/eleven-rack-' + target['version']
    for name in ('usr/bin/eleven-rack-control', 'usr/lib/eleven-rack/tools/eleven-rack-panel.py',
                 'usr/lib/eleven-rack/tools/eleven-rack-settings.py',
                 'usr/lib/eleven-rack/tools/eleven-rack-meters.c',
                 'etc/wireplumber/wireplumber.conf.d/51-eleven-rack.conf',
                 'etc/modprobe.d/eleven-rack-latency.conf',
                 'usr/share/libalpm/hooks/95-eleven-rack-initramfs.hook',
                 source + '/dkms.conf', source + '/prepared-kernel/sound/usb/Makefile'):
        read_member(driver, name)
    release = read_member(driver, source + '/prepared-kernel/kernel-release').decode().strip()
    if release != target['kernel_release']:
        raise RuntimeError('Packaged kernel sources do not match the target')
    backend = json.loads(read_member(driver, 'usr/share/doc/eleven-rack-latency-backend/backend-build.json'))
    expected_upstream = re.match(r'(?:\d+:)?(\d+\.\d+\.\d+)', target['pipewire_package_version'])[1]
    if backend['pipewire_version'] != expected_upstream or backend['spa_plugin_dir'] != '/usr/lib/spa-0.2':
        raise RuntimeError('Backend does not match Arch PipeWire')
    for member, checksum in (
            ('usr/lib/eleven-rack/spa/alsa/libspa-alsa.so', backend['library_sha256']),
            ('etc/wireplumber/wireplumber.conf.d/52-eleven-rack-latency.conf', backend['correction_config_sha256'])):
        if hashlib.sha256(read_member(driver, member)).hexdigest() != checksum:
            raise RuntimeError(f'Packaged backend/defaults changed: {member}')
    editor, _ = packages['eleven-rack-editor-linux']
    for name in ('usr/bin/eleven-rack-editor-linux', 'usr/share/applications/eleven-rack-editor-linux.desktop',
                 'opt/eleven-rack-editor/eleven-rack-editor-linux', 'opt/eleven-rack-editor/chrome-sandbox',
                 'opt/eleven-rack-editor/resources/app.asar',
                 'opt/eleven-rack-editor/resources/bridge-linux/bridge.py',
                 'opt/eleven-rack-editor/resources/bridge-linux/segmented_sysex.py',
                 'usr/share/licenses/eleven-rack-editor-linux/LICENSE',
                 'usr/share/doc/eleven-rack-editor-linux/NOTICE'):
        read_member(editor, name)
    return packages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--target', type=Path, required=True)
    args = parser.parse_args()
    target = json.loads(args.target.read_text())
    packages = check(args.directory, target)
    (args.directory / 'README.txt').write_text(f'''Eleven Rack Arch Linux package set

Kernel release: {target['kernel_release']}
linux / linux-headers package: {target['linux_package_version']}
PipeWire package: {target['pipewire_package_version']}

This set has exactly two packages:
  {packages['eleven-rack-driver'][0].name}
  {packages['eleven-rack-editor-linux'][0].name}

The driver includes DKMS sources, Control, the latency backend and configuration.
The editor includes Electron and the Linux MIDI bridge.

In the Arch VM, extract the downloaded artifact ZIP and open a terminal there:
  sha256sum --check SHA256SUMS
  uname -r
  pacman -Q linux linux-headers pipewire
  sudo pacman -U ./*.pkg.tar.zst

Use the matching kernel and PipeWire versions above. Pacman resolves standard
Arch dependencies and DKMS builds the patched module. Inspect the DKMS result,
then reboot and start eleven-rack-control gui or eleven-rack-editor-linux.
Rebuild this set before updating its pinned kernel or PipeWire packages.
Ubuntu measurement corrections are included; physical latency on Arch is
not yet validated. The VM build check does not establish hardware audio accuracy.
''')
    print('Verified exactly two matching Arch packages, including driver, Control, backend and editor')


if __name__ == '__main__':
    main()

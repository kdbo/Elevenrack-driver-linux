#!/usr/bin/env python3
"""Verify the downloadable Arch set contains exactly one complete driver and one editor."""
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent.parent


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
    depends = metadata.get('depend', [])
    # Exact pins block every Arch kernel/PipeWire update; sources follow the system instead.
    pinned = [d for d in depends if re.match(r'(linux|linux-headers|pipewire|pipewire-audio)=', d)]
    if pinned:
        raise RuntimeError('Driver must not pin exact versions: ' + ', '.join(pinned))
    for dependency in ('dkms', 'linux-headers', 'pipewire', 'pipewire-audio', 'patch', 'zstd'):
        if dependency not in depends:
            raise RuntimeError(f'Missing dependency: {dependency}')
    source = 'usr/src/eleven-rack-' + target['version']
    bundle = 'usr/lib/eleven-rack/backend-source'
    for name in ('usr/bin/eleven-rack-control', 'usr/lib/eleven-rack/tools/eleven-rack-panel.py',
                 'usr/lib/eleven-rack/tools/eleven-rack-updates.py',
                 'usr/lib/eleven-rack/tools/eleven_rack_diagnostics.py',
                 'usr/lib/eleven-rack/tools/eleven-rack-settings.py',
                 'usr/lib/eleven-rack/tools/eleven-rack-meters.c',
                 'etc/wireplumber/wireplumber.conf.d/51-eleven-rack.conf',
                 'etc/modprobe.d/eleven-rack-latency.conf',
                 'usr/share/libalpm/hooks/95-eleven-rack-initramfs.hook',
                 'usr/share/libalpm/hooks/96-eleven-rack-backend.hook', '.INSTALL',
                 source + '/fetch-arch-kernel-source.py', source + '/build-driver.sh',
                 source + '/prepared-kernel/sound/usb/Makefile',
                 bundle + '/tools/install-latency-backend.py', bundle + '/packaging/pipewire-sources.json',
                 *(f'{bundle}/archives/pipewire-{v}.tar.gz' for v in target['pipewire_versions'])):
        read_member(driver, name)
    if f'PACKAGE_VERSION="{target["version"]}"' not in read_member(driver, source + '/dkms.conf').decode():
        raise RuntimeError('dkms.conf does not carry the package version')
    release = read_member(driver, source + '/prepared-kernel/kernel-release').decode().strip()
    if release != target['kernel_release']:
        raise RuntimeError('Packaged kernel sources do not match the target')
    config = ROOT / 'config/52-eleven-rack-latency.conf'
    if read_member(driver, 'etc/wireplumber/wireplumber.conf.d/52-eleven-rack-latency.conf') != config.read_bytes():
        raise RuntimeError('Packaged latency defaults changed')
    editor, _ = packages['eleven-rack-editor-linux']
    for name in ('usr/bin/eleven-rack-editor-linux', 'usr/share/applications/eleven-rack-editor-linux.desktop',
                 'opt/eleven-rack-editor/eleven-rack-editor-linux', 'opt/eleven-rack-editor/chrome-sandbox',
                 'opt/eleven-rack-editor/resources/app.asar',
                 'opt/eleven-rack-editor/resources/eleven-rack-updates.py',
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

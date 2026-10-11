#!/usr/bin/env python3
"""Package a portable backend build as deb, Arch, RPM or a distro-specific tarball."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent.parent
NAME = 'eleven-rack-latency-backend'


def read_command(*command):
    return subprocess.check_output(command, text=True).strip()


def check_build(build):
    metadata = json.loads((build / 'backend-build.json').read_text())
    library = build / 'libspa-eleven-latency.so'
    if hashlib.sha256(library.read_bytes()).hexdigest() != metadata['library_sha256']:
        raise RuntimeError('Backend does not match build metadata; rebuild first')
    for field, path in (
            ('patch_sha256', ROOT / 'packaging/pipewire-eleven-latency.patch'),
            ('correction_config_sha256', ROOT / 'config/52-eleven-rack-latency.conf')):
        if hashlib.sha256(path.read_bytes()).hexdigest() != metadata.get(field):
            raise RuntimeError('Patch or correction defaults changed after the build; rebuild first')
    if not re.fullmatch(r'\d+\.\d+\.\d+', metadata['pipewire_version']):
        raise RuntimeError('Invalid build version')
    if not re.fullmatch(r'/[A-Za-z0-9_./+-]+', metadata['spa_plugin_dir']):
        raise RuntimeError('Invalid system SPA directory')
    if metadata['system_alsa_plugin'] != metadata['spa_plugin_dir'] + '/alsa/libspa-alsa.so':
        raise RuntimeError('Inconsistent system ALSA plugin path')
    if metadata['machine'] != read_command('uname', '-m'):
        raise RuntimeError('Package on the build architecture')
    return metadata


def write(stage, name, content, mode=0o644):
    path = stage / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(mode)


def copy(stage, source, name):
    path = stage / name
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, path)
    path.chmod(0o644)


def stage_payload(stage, build, metadata):
    copy(stage, build / 'libspa-eleven-latency.so', 'usr/lib/eleven-rack/spa/alsa/libspa-alsa.so')
    copy(stage, ROOT / 'config/52-eleven-rack-latency.conf',
         'etc/wireplumber/wireplumber.conf.d/52-eleven-rack-latency.conf')
    write(stage, 'etc/modprobe.d/eleven-rack-latency.conf',
          '# Requires the Eleven Rack patched snd_usb_audio driver.\noptions snd_usb_audio eleven_delay_hires=1\n')
    for unit in ('pipewire.service', 'wireplumber.service'):
        write(stage, f'usr/lib/systemd/user/{unit}.d/60-eleven-rack-latency.conf',
              '[Service]\nEnvironment=SPA_PLUGIN_DIR=/usr/lib/eleven-rack/spa:' + metadata['spa_plugin_dir'] + '\n')
    doc = f'usr/share/doc/{NAME}'
    copy(stage, build / 'backend-build.json', f'{doc}/backend-build.json')
    copy(stage, ROOT / 'LICENSES/PipeWire-MIT.txt', f'usr/share/licenses/{NAME}/PipeWire-MIT.txt')
    copy(stage, ROOT / 'packaging/pipewire-eleven-latency.patch', f'{doc}/pipewire-eleven-latency.patch')
    copy(stage, ROOT / 'docs/backend-building.md', f'{doc}/README.md')


def upstream_version(value):
    match = re.match(r'(?:\d+:)?(\d+\.\d+\.\d+)(?:[-+.~]|$)', value)
    if not match:
        raise RuntimeError(f'Cannot determine upstream version of {value!r}')
    return match[1]


def dependency_version(fmt, metadata):
    commands = {
        'deb': ('dpkg-query', '-W', '-f=${Version}', 'pipewire'),
        'arch': ('pacman', '-Q', 'pipewire'),
        'rpm': ('rpm', '-q', '--qf', '%{EPOCHNUM}:%{VERSION}-%{RELEASE}', 'pipewire'),
    }
    value = read_command(*commands[fmt])
    if fmt == 'arch':
        value = value.split()[1]
    if upstream_version(value) != metadata['pipewire_version']:
        raise RuntimeError('Native packages must be built for the installed PipeWire version; '
                           'use a matching build environment or --format tar for cross-version build checks')
    return value


def archive_payload(stage, archive):
    with tarfile.open(archive, 'w:gz') as bundle:
        for path in sorted(stage.rglob('*')):
            info = bundle.gettarinfo(str(path), arcname=str(path.relative_to(stage)))
            info.uid = info.gid = 0
            info.uname = info.gname = 'root'
            if path.is_file():
                with path.open('rb') as data:
                    bundle.addfile(info, data)
            else:
                bundle.addfile(info)


def refresh_script():
    return ('if command -v update-initramfs >/dev/null 2>&1; then\n'
            '  update-initramfs -u -k all\n'
            'elif command -v dracut >/dev/null 2>&1; then\n'
            '  dracut --regenerate-all --force\n'
            'fi\n'
            'echo "Restart the audio session or reboot to apply the backend change."\n')


def build_deb(stage, output, version, driver_version, pw_version):
    arch = read_command('dpkg', '--print-architecture')
    alsa = 'libasound2'
    try:
        if read_command('dpkg-query', '-W', '-f=${db:Status-Status}', 'libasound2t64') == 'installed':
            alsa = 'libasound2t64'
    except subprocess.CalledProcessError:
        pass
    libc_version = read_command('dpkg-query', '-W', '-f=${Version}', 'libc6')
    alsa_version = read_command('dpkg-query', '-W', '-f=${Version}', alsa)
    write(stage, 'DEBIAN/control', f'''Package: {NAME}
Version: {version}
Architecture: {arch}
Section: sound
Priority: optional
Maintainer: Eleven Rack Linux contributors <noreply@localhost>
Depends: eleven-rack-driver (>= {driver_version}), pipewire (= {pw_version}), wireplumber (>= 0.5), libc6 (>= {libc_version}), {alsa} (>= {alsa_version})
Description: Eleven Rack runtime latency reporting for PipeWire
 USB and PCM queue accounting with Ubuntu measurement defaults.
 Corrections on other distributions are not hardware validated.
''')
    write(stage, 'DEBIAN/conffiles',
          '/etc/wireplumber/wireplumber.conf.d/52-eleven-rack-latency.conf\n'
          '/etc/modprobe.d/eleven-rack-latency.conf\n')
    for script in ('postinst', 'postrm'):
        write(stage, f'DEBIAN/{script}', '#!/bin/sh\nset -e\n' + refresh_script(), 0o755)
    files = sorted(p for p in stage.rglob('*') if p.is_file() and p.relative_to(stage).parts[0] != 'DEBIAN')
    write(stage, 'DEBIAN/md5sums', ''.join(
        f'{hashlib.md5(p.read_bytes(), usedforsecurity=False).hexdigest()}  {p.relative_to(stage)}\n' for p in files))
    package = output / f'{NAME}_{version}_{arch}.deb'
    subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(stage), str(package)], check=True)
    return [package]


def build_arch(stage, work, output, version, pw_version):
    if os.geteuid() == 0:
        raise RuntimeError('Run Arch packaging as a regular user (makepkg refuses root)')
    version = version.replace('~', '')
    archive = work / 'payload.tar.gz'
    archive_payload(stage, archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    write(work, 'PKGBUILD', f'''pkgname={NAME}
pkgver={version}
pkgrel=1
pkgdesc='Eleven Rack runtime latency reporting with Ubuntu measurement defaults'
arch=('{read_command('uname', '-m')}')
license=('MIT')
options=('!strip')
depends=('eleven-rack-driver-dkms' 'pipewire={pw_version}' 'pipewire-audio={pw_version}' 'wireplumber>=0.5' 'alsa-lib' 'glibc')
install=backend.install
backup=('etc/modprobe.d/eleven-rack-latency.conf' 'etc/wireplumber/wireplumber.conf.d/52-eleven-rack-latency.conf')
source=('payload.tar.gz')
sha256sums=('{digest}')
package() {{
    cp -a "$srcdir/etc" "$srcdir/usr" "$pkgdir/"
}}
''')
    write(work, 'backend.install', '''refresh() {
    if command -v mkinitcpio >/dev/null 2>&1; then
        mkinitcpio -P
    fi
    echo 'Restart the audio session or reboot to apply the backend change.'
}
post_install() { refresh; }
post_upgrade() { refresh; }
post_remove() { refresh; }
''')
    subprocess.run(['makepkg', '--nodeps', '--cleanbuild', '--noconfirm'], cwd=work, check=True)
    packages = []
    for path in work.glob('*.pkg.tar.*'):
        dest = output / path.name
        shutil.copy2(path, dest)
        packages.append(dest)
    if not packages:
        raise RuntimeError('makepkg produced no package')
    return packages


def build_rpm(stage, work, output, version, metadata, pw_version):
    for directory in ('SOURCES', 'SPECS', 'BUILD', 'BUILDROOT', 'RPMS', 'SRPMS'):
        (work / directory).mkdir()
    archive_payload(stage, work / 'SOURCES/payload.tar.gz')
    manifest = '\n'.join(('%config(noreplace) ' if p.parts[0] == 'etc' else '') + '/' + str(p)
                         for p in sorted(p.relative_to(stage) for p in stage.rglob('*') if p.is_file()))
    write(work, 'SPECS/backend.spec', f'''Name: {NAME}
%global debug_package %{{nil}}
%global __strip /bin/true
Version: {version}
Release: 1%{{?dist}}
Summary: Eleven Rack runtime latency reporting with Ubuntu measurement defaults
License: MIT
Source0: payload.tar.gz
Requires: eleven-rack-driver-dkms
Requires: pipewire = {pw_version}
Requires: pipewire-libs = {pw_version}
Requires: wireplumber >= 0.5
%description
USB and PCM queue accounting with Ubuntu measurement defaults.
Corrections on other distributions are not hardware validated.
%prep
mkdir payload
tar -xzf %{{SOURCE0}} -C payload
%build
%install
mkdir -p %{{buildroot}}
cp -a payload/etc payload/usr %{{buildroot}}/
%post
{refresh_script()}
%postun
{refresh_script()}
%files
{manifest}
''')
    subprocess.run(['rpmbuild', '--define', f'_topdir {work}', '-bb', str(work / 'SPECS/backend.spec')], check=True)
    packages = []
    for path in (work / 'RPMS').rglob('*.rpm'):
        dest = output / path.name
        shutil.copy2(path, dest)
        packages.append(dest)
    if not packages:
        raise RuntimeError('rpmbuild produced no package')
    return packages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--format', choices=('deb', 'arch', 'rpm', 'tar'), required=True)
    parser.add_argument('--build', type=Path, default=ROOT / 'build/latency')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/packages')
    parser.add_argument('--version')
    args = parser.parse_args()
    driver_version = (ROOT / 'VERSION').read_text().strip()
    version = args.version or driver_version
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:~(?:alpha|beta|rc)\d+)?', version):
        parser.error('Invalid package version')
    metadata = check_build(args.build)
    pw_version = dependency_version(args.format, metadata) if args.format != 'tar' else None
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='eleven-package-') as directory:
        work = Path(directory)
        stage = work / 'stage'
        stage.mkdir()
        stage_payload(stage, args.build, metadata)
        if args.format == 'deb':
            packages = build_deb(stage, output, version, driver_version, pw_version)
        elif args.format == 'arch':
            packages = build_arch(stage, work, output, version, pw_version)
        elif args.format == 'rpm':
            packages = build_rpm(stage, work, output, version, metadata, pw_version)
        else:
            package = output / f'{NAME}_{version}_pw{metadata["pipewire_version"]}_{metadata["machine"]}.tar.gz'
            archive_payload(stage, package)
            packages = [package]
    for package in packages:
        checksum = hashlib.sha256(package.read_bytes()).hexdigest()
        package.with_name(package.name + '.sha256').write_text(f'{checksum}  {package.name}\n')
        print(package)


if __name__ == '__main__':
    main()

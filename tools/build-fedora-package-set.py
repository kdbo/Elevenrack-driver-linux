#!/usr/bin/env python3
"""Build two Fedora RPMs from distribution-prepared sources and an Electron directory."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def copy(stage, source, destination, executable=False):
    target = stage / destination
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    target.chmod(0o755 if executable else 0o644)


def write(stage, destination, value, executable=False):
    target = stage / destination
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(value)
    target.chmod(0o755 if executable else 0o644)


def spec(name, version, stage, dependencies, scripts=''):
    files = []
    for path in sorted(stage.rglob('*')):
        relative = path.relative_to(stage)
        if path.is_dir():
            # Own private directories, never shared system directories.
            if str(relative).startswith(('usr/src/eleven-rack-', 'opt/eleven-rack-editor',
                                          'usr/lib/eleven-rack/', 'usr/share/doc/'+name,
                                          'usr/share/licenses/'+name)):
                files.append('%dir /'+str(relative))
            continue
        prefix = '%config(noreplace) ' if relative.parts[0] == 'etc' else ''
        files.append(prefix+'/'+str(relative))
    return f'''Name: {name}
Version: {version}
Release: 1%{{?dist}}
Summary: Eleven Rack Linux {'driver, Control and PipeWire backend' if name == 'eleven-rack-driver' else 'Editor and MIDI bridge'}
License: {'MIT AND GPL-2.0-or-later' if name == 'eleven-rack-driver' else 'MIT'}
URL: https://github.com/kdbo/Elevenrack-driver-linux
Source0: payload.tar.gz
%global debug_package %{{nil}}
%global __strip /bin/true
%global __brp_strip /bin/true
{''.join('Requires: '+d+chr(10) for d in dependencies)}
{('Provides: eleven-rack-driver-dkms = '+version+chr(10)+'Conflicts: eleven-rack-latency-backend') if name == 'eleven-rack-driver' else ''}
%description
Eleven Rack Linux {'DKMS sources, Control panel, latency backend and configuration' if name == 'eleven-rack-driver' else 'Electron Editor with Linux MIDI bridge'}.
%prep
mkdir payload
tar -xzf %{{SOURCE0}} -C payload
%build
%install
mkdir -p %{{buildroot}}
cp -a payload/. %{{buildroot}}/
{scripts}
%files
{chr(10).join(files)}
'''


def driver_payload(stage, version, kernel, source, backend_build, backend, extra_sources=()):
    metadata = backend.check_build(backend_build)
    if metadata['spa_plugin_dir'] != '/usr/lib64/spa-0.2':
        raise RuntimeError('Build the x86_64 backend inside Fedora')
    if not (source / 'sound/usb/Makefile').is_file():
        raise RuntimeError('Missing prepared Fedora sound/usb source')
    if (source / 'include/config/kernel.release').read_text().strip() != kernel:
        raise RuntimeError('Prepared source identity does not match kernel-devel')
    backend.stage_payload(stage, backend_build, metadata)
    for name in ('eleven-rack-panel.py', 'eleven-rack-settings.py'):
        copy(stage, ROOT/'tools'/name, 'usr/lib/eleven-rack/tools/'+name, True)
    copy(stage, ROOT/'tools/eleven-rack-meters.c', 'usr/lib/eleven-rack/tools/eleven-rack-meters.c')
    write(stage, 'usr/lib/eleven-rack/VERSION', version+'\n')
    for destination in ('usr/lib/eleven-rack/assets/eleven-rack-control-logo-v2.png',
                        'usr/share/pixmaps/eleven-rack-driver.png'):
        copy(stage, ROOT/'assets/eleven-rack-control-logo-v2.png', destination)
    copy(stage, ROOT/'config/eleven-rack-driver.desktop', 'usr/share/applications/eleven-rack-driver.desktop')
    copy(stage, ROOT/'config/51-eleven-rack.conf', 'etc/wireplumber/wireplumber.conf.d/51-eleven-rack.conf')
    write(stage, 'usr/bin/eleven-rack-control', '#!/bin/sh\nexec /usr/bin/python3 /usr/lib/eleven-rack/tools/eleven-rack-settings.py "$@"\n', True)
    destination = 'usr/src/eleven-rack-'+version
    for name in ('build-driver-common.sh', 'prepare-driver.py', 'mixer-eleven-rack.h'):
        copy(stage, ROOT/'packaging'/name, destination+'/'+name)
    copy(stage, ROOT/'packaging/fedora/build-driver.sh', destination+'/build-driver.sh')
    dkms = (ROOT/'packaging/dkms.conf').read_text().replace('@VERSION@', version)
    kernels = [kernel]
    for extra in extra_sources:
        release = (extra/'include/config/kernel.release').read_text().strip()
        if not re.fullmatch(r'[0-9][A-Za-z0-9_.+-]*', release) or release in kernels:
            raise RuntimeError('Invalid or duplicate additional kernel release')
        kernels.append(release)
        shutil.copytree(extra/'sound/usb', stage/destination/'prepared-kernels'/release/'sound/usb')
        write(stage, destination+'/prepared-kernels/'+release+'/kernel-release', release+'\n')
    dkms += 'BUILD_EXCLUSIVE_KERNEL="^('+('|'.join(re.escape(k) for k in kernels))+')$"\n'
    write(stage, destination+'/dkms.conf', dkms)
    shutil.copytree(source/'sound/usb', stage/destination/'prepared-kernel/sound/usb')
    write(stage, destination+'/prepared-kernel/kernel-release', kernel+'\n')
    for name in ('LICENSE', 'LICENSING.md', 'CREDITS.md'):
        copy(stage, ROOT/name, 'usr/share/doc/eleven-rack-driver/'+name)
    copy(stage, ROOT/'LICENSES/GPL-2.0.txt', 'usr/share/licenses/eleven-rack-driver/GPL-2.0.txt')
    return metadata


def driver_scripts(version, kernel):
    kernels = [kernel] if isinstance(kernel, str) else kernel
    kernel = ' '.join(kernels)
    return f'''%post
set -e
dkms add -m eleven-rack -v {version} || test -d /var/lib/dkms/eleven-rack/{version}
for kernel in {kernel}; do
    test -f /usr/src/kernels/$kernel/Makefile || {{ echo "Missing kernel-devel files for $kernel" >&2; exit 1; }}
    dkms build -m eleven-rack -v {version} -k "$kernel" --kernelsourcedir "/usr/src/kernels/$kernel"
    dkms install -m eleven-rack -v {version} -k "$kernel" --kernelsourcedir "/usr/src/kernels/$kernel"
    depmod -a "$kernel"
    if [ -f /boot/vmlinuz-$kernel ]; then dracut --force --kver "$kernel"; fi
done
echo 'Eleven Rack installed. Reboot to activate the driver and audio configuration.'
%preun
if [ "$1" -eq 0 ]; then dkms remove -m eleven-rack -v {version} --all; fi
%postun
if [ "$1" -eq 0 ]; then
    for kernel in {kernel}; do
        if [ -d /lib/modules/$kernel ]; then
            depmod -a "$kernel"
            if [ -f /boot/vmlinuz-$kernel ]; then dracut --force --kver "$kernel"; fi
        fi
    done
fi
'''


def editor_payload(stage, editor):
    for required in ('eleven-rack-editor-linux', 'resources/app.asar', 'resources/bridge-linux/bridge.py',
                     'resources/bridge-linux/rtmidi/__init__.py'):
        if not (editor/required).is_file():
            raise RuntimeError('Missing built Editor file: '+required)
    shutil.copytree(editor, stage/'opt/eleven-rack-editor', symlinks=True)
    write(stage, 'usr/bin/eleven-rack-editor-linux', '#!/bin/sh\nexec /opt/eleven-rack-editor/eleven-rack-editor-linux "$@"\n', True)
    write(stage, 'usr/share/applications/eleven-rack-editor-linux.desktop', '''[Desktop Entry]
Type=Application
Name=Eleven Rack Editor
Exec=eleven-rack-editor-linux
Icon=/opt/eleven-rack-editor/resources/eleven-rack-editor-logo.png
Terminal=false
Categories=AudioVideo;Audio;
''')
    for name in ('LICENSE', 'NOTICE'):
        copy(stage, ROOT/'editor'/name, 'usr/share/doc/eleven-rack-editor-linux/'+name)


def editor_dependencies():
    # RtMidi is bundled next to bridge.py and compiled for this Python ABI.
    return ['python3', f'python(abi) = {sys.version_info.major}.{sys.version_info.minor}',
            'python3-websockets', 'gtk3', 'nss', 'alsa-lib', 'mesa-libgbm', 'libdrm',
            'cups-libs', 'libxkbcommon', 'libXScrnSaver', 'libXtst', 'at-spi2-core',
            'libnotify', 'xdg-utils']


def build_rpm(stage, output, recipe, backend):
    with tempfile.TemporaryDirectory(prefix='fedora-rpm-') as temporary:
        work = Path(temporary)
        for name in ('SOURCES', 'SPECS', 'BUILD', 'BUILDROOT', 'RPMS', 'SRPMS'):
            (work/name).mkdir()
        backend.archive_payload(stage, work/'SOURCES/payload.tar.gz')
        path = work/'SPECS/package.spec'
        path.write_text(recipe)
        subprocess.run(['rpmbuild', '--define', '_topdir '+str(work), '-bb', str(path)], check=True)
        packages = list((work/'RPMS').rglob('*.rpm'))
        if len(packages) != 1:
            raise RuntimeError('Expected one binary RPM')
        shutil.copy2(packages[0], output/packages[0].name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--distro', choices=('fedora', 'centos-stream10'), default='fedora')
    parser.add_argument('--kernel-source', type=Path, required=True)
    parser.add_argument('--kernel-release', required=True)
    parser.add_argument('--kernel-devel-version', required=True)
    parser.add_argument('--extra-kernel-source', type=Path, action='append', default=[])
    parser.add_argument('--backend-build', type=Path, default=ROOT/'build/latency')
    parser.add_argument('--editor', type=Path, default=ROOT/'editor/dist/linux-unpacked')
    parser.add_argument('--output', type=Path, default=ROOT/'build/fedora-set')
    args = parser.parse_args()
    version = (ROOT/'VERSION').read_text().strip()
    targets = [{'kernel_release': args.kernel_release, 'kernel_devel_version': args.kernel_devel_version}]
    for source in args.extra_kernel_source:
        release = (source/'include/config/kernel.release').read_text().strip()
        if not re.fullmatch(r'[0-9][A-Za-z0-9_.+-]*\.x86_64', release):
            parser.error('Invalid additional kernel release')
        targets.append({'kernel_release': release, 'kernel_devel_version': release.removesuffix('.x86_64')})
    for value in (version, args.kernel_release, args.kernel_devel_version):
        if not re.fullmatch(r'[0-9][A-Za-z0-9_.+~:-]*', value):
            parser.error('Invalid package or kernel version')
    spec_module = importlib.util.spec_from_file_location('backend', ROOT/'tools/build-latency-package.py')
    backend = importlib.util.module_from_spec(spec_module)
    spec_module.loader.exec_module(backend)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if list(output.glob('*.rpm')):
        parser.error('Refusing to mix with an existing RPM set')
    with tempfile.TemporaryDirectory(prefix='fedora-payload-') as temporary:
        stage = Path(temporary)/'driver'
        stage.mkdir()
        metadata = driver_payload(stage, version, args.kernel_release, args.kernel_source.resolve(), args.backend_build, backend, args.extra_kernel_source)
        pw = backend.dependency_version('rpm', metadata)
        dependencies = ['dkms', 'gcc', 'make', 'python3', 'python3-gobject', 'python3-websockets',
                        'gtk3', 'alsa-utils', 'alsa-lib', 'wireplumber >= 0.5', 'kmod', 'dracut',
                        'kernel-devel = '+args.kernel_devel_version,
                        'kernel-devel-matched = '+args.kernel_devel_version, 'pipewire = '+pw,
                        'pipewire-libs = '+pw, 'pipewire-jack-audio-connection-kit = '+pw]
        for target in targets[1:]:
            dependencies += ['kernel-devel = '+target['kernel_devel_version'], 'kernel-core = '+target['kernel_devel_version']]
        recipe = spec('eleven-rack-driver', version, stage, dependencies, driver_scripts(version, [t['kernel_release'] for t in targets]))
        build_rpm(stage, output, recipe, backend)
        stage = Path(temporary)/'editor'
        stage.mkdir()
        editor_payload(stage, args.editor.resolve())
        dependencies = editor_dependencies()
        build_rpm(stage, output, spec('eleven-rack-editor-linux', version, stage, dependencies), backend)
    target = {'distro': args.distro, 'version': version, 'kernel_release': args.kernel_release,
              'kernel_devel_version': args.kernel_devel_version, 'pipewire_package_version': pw,
              'kernels': targets}
    (output/'package-target.json').write_text(json.dumps(target, indent=2)+'\n')
    print('Built complete Fedora package set:', output)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Build the combined GUI + experimental DKMS .deb without root."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def build(version, output, backend_build=None, backend_sources=None):
    if backend_build is not None and backend_sources is not None:
        raise RuntimeError('Choose either a prebuilt backend or bundled backend sources')
    arch = 'all'
    extra_dependencies = ''
    replacement_fields = ''
    backend = metadata = None
    if backend_build is not None:
        spec = importlib.util.spec_from_file_location('latency_packager', ROOT / 'tools/build-latency-package.py')
        backend = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(backend)
        metadata = backend.check_build(backend_build)
        pw_version = backend.dependency_version('deb', metadata)
        arch = backend.read_command('dpkg', '--print-architecture')
        alsa = 'libasound2t64' if backend.read_command('dpkg-query', '-W', '-f=${db:Status-Status}', 'libasound2t64') == 'installed' else 'libasound2'
        libc = backend.read_command('dpkg-query', '-W', '-f=${Version}', 'libc6')
        alsa_version = backend.read_command('dpkg-query', '-W', '-f=${Version}', alsa)
        extra_dependencies = f', pipewire (= {pw_version}), libspa-0.2-modules (= {pw_version}), libc6 (>= {libc}), {alsa} (>= {alsa_version})'
        replacement_fields = 'Conflicts: eleven-rack-latency-backend\nReplaces: eleven-rack-latency-backend\n'
    if backend_sources is not None:
        extra_dependencies = ', pipewire, libasound2-dev, patch, pkg-config'
        replacement_fields = 'Conflicts: eleven-rack-latency-backend\nReplaces: eleven-rack-latency-backend\n'
    output.mkdir(parents=True, exist_ok=True)
    package = output / f'eleven-rack-driver_{version}_{arch}.deb'
    with tempfile.TemporaryDirectory(prefix='deb-stage-', dir=output) as temp:
        stage = Path(temp)
        if backend is not None:
            backend.stage_payload(stage, backend_build, metadata)
        if backend is not None or backend_sources is not None:
            # WirePlumber 0.4 uses Lua rules; derive them from the same defaults.
            import re
            properties = re.findall(r'^\s*(api\.alsa\.eleven-[\w-]+)\s*=\s*(true|-?\d+)\s*$',
                                    (ROOT / 'config/52-eleven-rack-latency.conf').read_text(), re.M)
            assert len(properties) == 26, 'Incomplete latency defaults'
            lua = 'local rule = {\n  matches = {\n'
            for direction in ('input', 'output'):
                lua += '    { { "node.name", "matches", "alsa_' + direction + '.usb-Digidesign_Eleven_Rack.*" }, { "api.alsa.card.id", "equals", "Rack" } },\n'
            lua += '  },\n  apply_properties = {\n'
            lua += ''.join(f'    ["{key}"] = {value},\n' for key, value in properties)
            lua += '  },\n}\ntable.insert(alsa_monitor.rules, rule)\n'
            target = stage / 'etc/wireplumber/main.lua.d/52-eleven-rack-latency.lua'
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(lua)

        def write(path, content, executable=False):
            target = stage / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            target.chmod(0o755 if executable else 0o644)

        def copy(source, target, executable=False):
            dest = stage / target
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / source, dest)
            dest.chmod(0o755 if executable else 0o644)

        if backend_sources is not None:
            bundle = 'usr/lib/eleven-rack/backend-source'
            catalog = json.loads((ROOT / 'packaging/pipewire-sources.json').read_text())
            for release, source in catalog.items():
                archive = backend_sources / f'pipewire-{release}.tar.gz'
                if hashlib.sha256(archive.read_bytes()).hexdigest() != source['sha256']:
                    raise RuntimeError(f'Invalid bundled PipeWire {release} source')
                copy(archive, f'{bundle}/archives/{archive.name}')
            for name in ('build-latency-backend.py', 'check-latency-backend.py',
                         'install-latency-backend.py', 'spa-eleven-alsa.c'):
                copy('tools/' + name, f'{bundle}/tools/{name}')
            copy('packaging/pipewire-sources.json', f'{bundle}/packaging/pipewire-sources.json')
            for name in {'pipewire-eleven-latency.patch', *(source.get('patch', 'pipewire-eleven-latency.patch') for source in catalog.values())}:
                copy('packaging/' + name, f'{bundle}/packaging/{name}')
            copy('config/52-eleven-rack-latency.conf', f'{bundle}/config/52-eleven-rack-latency.conf')
            copy('config/52-eleven-rack-latency.conf', 'etc/wireplumber/wireplumber.conf.d/52-eleven-rack-latency.conf')
            copy('LICENSES/PipeWire-MIT.txt', 'usr/share/doc/eleven-rack-driver/PipeWire-MIT.txt')
            write('etc/modprobe.d/eleven-rack-latency.conf',
                  'options snd_usb_audio eleven_delay_hires=1\n')
            # PipeWire upgrades automatically rebuild for the newly installed version.
            write('DEBIAN/triggers', 'interest-noawait /usr/bin/pipewire\n'
                  'interest-noawait /usr/lib/x86_64-linux-gnu/spa-0.2\n'
                  'interest-noawait /usr/lib/aarch64-linux-gnu/spa-0.2\n')

        write('DEBIAN/control', f'''Package: eleven-rack-driver
Version: {version}
Section: sound
Priority: optional
Architecture: {arch}
Maintainer: Eleven Rack Linux contributors <noreply@localhost>
Depends: python3 (>= 3.12), python3-gi, python3-websockets, gir1.2-gtk-3.0, gir1.2-gdkpixbuf-2.0, alsa-utils, pipewire-bin, pipewire-jack, libjack-jackd2-0 | libjack0, wireplumber (>= 0.4), dkms (>= 2.8.7), build-essential, apt, dpkg-dev, ca-certificates, bzip2, xz-utils, linux-source (>= 6.8), linux-headers-generic | linux-headers-generic-hwe-24.04{extra_dependencies}
{replacement_fields}Recommends: mokutil
Description: Eleven Rack Linux audio driver and control panel (experimental)
 Patched snd-usb-audio built for the host kernel using DKMS, with a native
 GTK control panel, ALSA controls, and WirePlumber routing configuration.
 Targets Ubuntu 24.04, 24.10, 25.04, 25.10 and 26.04; 26.10 is preliminary.
 Matching kernel source and headers
 are required. Kernel compatibility must be validated per series.
''')
        for name in ('postinst', 'prerm', 'postrm'):
            text = (ROOT / 'packaging' / name).read_text().replace('@VERSION@', version)
            if backend_sources is not None:
                installer = '/usr/lib/eleven-rack/backend-source/tools/install-latency-backend.py'
                if name == 'postinst':
                    text = text.replace('    configure)\n', f'    triggered)\n        python3 {installer}\n        ;;\n    configure)\n        python3 {installer}\n')
                elif name == 'postrm':
                    # postrm survives unpacked-file removal, so cleanup is self-contained.
                    cleanup = '\n'.join('        rm -f /' + path for path in (
                        'usr/lib/eleven-rack/spa/alsa/libspa-alsa.so',
                        'usr/lib/systemd/user/pipewire.service.d/60-eleven-rack-latency.conf',
                        'usr/lib/systemd/user/wireplumber.service.d/60-eleven-rack-latency.conf',
                        'var/lib/eleven-rack/latency/backend-build.json'))
                    text = text.replace('    remove)\n', '    remove|purge)\n' + cleanup + '\n')
            write(f'DEBIAN/{name}', text, True)
        source_dir = f'usr/src/eleven-rack-{version}'
        for name in ('build-driver.sh', 'build-driver-common.sh', 'prepare-driver.py', 'fetch-kernel-source.py', 'mixer-eleven-rack.h'):
            copy('packaging/' + name, source_dir + '/' + name, True)
        text = (ROOT / 'packaging/dkms.conf').read_text().replace('@VERSION@', version)
        write(source_dir + '/dkms.conf', text)
        for name in ('eleven-rack-panel.py', 'eleven-rack-settings.py', 'eleven-rack-updates.py'):
            copy('tools/' + name, 'usr/lib/eleven-rack/tools/' + name, True)
        write('usr/lib/eleven-rack/VERSION', version + '\n')
        copy('tools/eleven-rack-meters.c', 'usr/lib/eleven-rack/tools/eleven-rack-meters.c')
        copy('assets/eleven-rack-control-logo-v2.png',
             'usr/lib/eleven-rack/assets/eleven-rack-control-logo-v2.png')
        copy('assets/eleven-rack-control-logo-v2.png', 'usr/share/pixmaps/eleven-rack-driver.png')
        copy('config/eleven-rack-driver.desktop',
             'usr/share/applications/eleven-rack-driver.desktop')
        copy('config/51-eleven-rack.conf',
             'etc/wireplumber/wireplumber.conf.d/51-eleven-rack.conf')
        copy('config/51-eleven-rack.lua',
             'etc/wireplumber/main.lua.d/51-eleven-rack.lua')
        write('DEBIAN/conffiles', '/etc/wireplumber/wireplumber.conf.d/51-eleven-rack.conf\n'
              '/etc/wireplumber/main.lua.d/51-eleven-rack.lua\n' +
              ('/etc/wireplumber/wireplumber.conf.d/52-eleven-rack-latency.conf\n'
               '/etc/modprobe.d/eleven-rack-latency.conf\n' if backend or backend_sources else ''))
        if backend or backend_sources:
            with (stage / 'DEBIAN/conffiles').open('a') as conffiles:
                conffiles.write('/etc/wireplumber/main.lua.d/52-eleven-rack-latency.lua\n')
        write('usr/bin/eleven-rack-control', '#!/bin/sh\n'
              'exec /usr/bin/python3 /usr/lib/eleven-rack/tools/eleven-rack-settings.py "$@"\n', True)
        copy('docs/packaging.md', 'usr/share/doc/eleven-rack-driver/README.md')
        copy('LICENSE', 'usr/share/doc/eleven-rack-driver/LICENSE')
        copy('LICENSING.md', 'usr/share/doc/eleven-rack-driver/LICENSING.md')
        copy('LICENSES/GPL-2.0.txt', 'usr/share/doc/eleven-rack-driver/GPL-2.0.txt')
        copy('CREDITS.md', 'usr/share/doc/eleven-rack-driver/CREDITS.md')
        copy('docs/interface-settings.md', 'usr/share/doc/eleven-rack-driver/interface-settings.md')
        copy('docs/compatibility-builds.json',
             'usr/share/doc/eleven-rack-driver/compatibility-builds.json')
        copy('docs/hwe-build.json', 'usr/share/doc/eleven-rack-driver/hwe-build.json')
        copy('packaging/ubuntu-kernels.json', 'usr/share/doc/eleven-rack-driver/ubuntu-kernels.json')
        # Do not copy developer umask permissions onto system directories.
        stage.chmod(0o755)
        for path in stage.rglob('*'):
            if path.is_dir():
                path.chmod(0o755)
        installed_files = sorted(p for p in stage.rglob('*')
                                 if p.is_file() and p.relative_to(stage).parts[0] != 'DEBIAN')
        write('DEBIAN/md5sums', ''.join(
            f'{hashlib.md5(p.read_bytes(), usedforsecurity=False).hexdigest()}  '
            f'{p.relative_to(stage)}\n' for p in installed_files))
        installed_size = sum((p.stat().st_size + 1023) // 1024 for p in installed_files)
        control = stage / 'DEBIAN/control'
        control.write_text(control.read_text().replace(f'Architecture: {arch}\n',
                           f'Architecture: {arch}\nInstalled-Size: {installed_size}\n'))
        # Root ownership without requiring fakeroot/sudo.
        subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(stage), str(package)],
                       check=True)
    return package


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', default=(ROOT / 'VERSION').read_text().strip())
    parser.add_argument('--output', type=Path, default=ROOT / 'build/packages')
    parser.add_argument('--backend-build', type=Path, help='Include a verified backend built for this Ubuntu environment')
    parser.add_argument('--backend-sources', type=Path, help='Bundle verified PipeWire archives and build automatically during installation')
    args = parser.parse_args()
    # Version is embedded in paths and DKMS shell config, so constrain it.
    import re
    if not re.fullmatch(r'[0-9][0-9A-Za-z.+~]*', args.version):
        parser.error('Version must start with a digit and contain only letters, digits, . + ~')
    print(build(args.version, args.output.resolve(), args.backend_build, args.backend_sources))

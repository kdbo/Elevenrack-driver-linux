#!/usr/bin/env python3
"""Build the combined GUI + experimental DKMS .deb without root."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def build(version, output):
    output.mkdir(parents=True, exist_ok=True)
    package = output / f'eleven-rack-driver_{version}_all.deb'
    with tempfile.TemporaryDirectory(prefix='deb-stage-', dir=output) as temp:
        stage = Path(temp)

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

        write('DEBIAN/control', f'''Package: eleven-rack-driver
Version: {version}
Section: sound
Priority: optional
Architecture: all
Maintainer: Eleven Rack Linux contributors <noreply@localhost>
Depends: python3 (>= 3.12), python3-gi, gir1.2-gtk-3.0, gir1.2-gdkpixbuf-2.0, alsa-utils, pipewire-bin, wireplumber (>= 0.4), dkms (>= 2.8.7), build-essential, linux-source (>= 6.8), linux-headers-generic | linux-headers-generic-hwe-24.04
Recommends: mokutil
Description: Eleven Rack Linux audio driver and control panel (experimental)
 Patched snd-usb-audio built for the host kernel using DKMS, with a native
 GTK control panel, ALSA controls, and WirePlumber routing configuration.
 Targets Ubuntu 24.04, 24.10, 25.04, 25.10 and 26.04; 26.10 is preliminary.
 Matching kernel source and headers
 are required. Kernel compatibility must be validated per series.
''')
        for name in ('postinst', 'prerm', 'postrm'):
            text = (ROOT / 'packaging' / name).read_text().replace('@VERSION@', version)
            write(f'DEBIAN/{name}', text, True)
        source_dir = f'usr/src/eleven-rack-{version}'
        for name in ('build-driver.sh', 'prepare-driver.py'):
            copy('packaging/' + name, source_dir + '/' + name, True)
        text = (ROOT / 'packaging/dkms.conf').read_text().replace('@VERSION@', version)
        write(source_dir + '/dkms.conf', text)
        for name in ('eleven-rack-panel.py', 'eleven-rack-settings.py'):
            copy('tools/' + name, 'usr/lib/eleven-rack/tools/' + name, True)
        copy('assets/eleven-rack-linux-logo-v1.png',
             'usr/lib/eleven-rack/assets/eleven-rack-linux-logo-v1.png')
        copy('assets/eleven-rack-linux-logo-v1.png', 'usr/share/pixmaps/eleven-rack-driver.png')
        copy('config/eleven-rack-driver.desktop',
             'usr/share/applications/eleven-rack-driver.desktop')
        copy('config/51-eleven-rack.conf',
             'etc/wireplumber/wireplumber.conf.d/51-eleven-rack.conf')
        copy('config/51-eleven-rack.lua',
             'etc/wireplumber/main.lua.d/51-eleven-rack.lua')
        write('DEBIAN/conffiles', '/etc/wireplumber/wireplumber.conf.d/51-eleven-rack.conf\n'
              '/etc/wireplumber/main.lua.d/51-eleven-rack.lua\n')
        write('usr/bin/eleven-rack-control', '#!/bin/sh\n'
              'exec /usr/bin/python3 /usr/lib/eleven-rack/tools/eleven-rack-settings.py "$@"\n', True)
        copy('docs/packaging.md', 'usr/share/doc/eleven-rack-driver/README.md')
        copy('docs/interface-settings.md', 'usr/share/doc/eleven-rack-driver/interface-settings.md')
        copy('docs/compatibility-builds.json',
             'usr/share/doc/eleven-rack-driver/compatibility-builds.json')
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
        control.write_text(control.read_text().replace('Architecture: all\n',
                           f'Architecture: all\nInstalled-Size: {installed_size}\n'))
        # Root ownership without requiring fakeroot/sudo.
        subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(stage), str(package)],
                       check=True)
    return package


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', default='0.1.0~beta4')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/packages')
    args = parser.parse_args()
    # Version is embedded in paths and DKMS shell config, so constrain it.
    import re
    if not re.fullmatch(r'[0-9][0-9A-Za-z.+~]*', args.version):
        parser.error('Version must start with a digit and contain only letters, digits, . + ~')
    print(build(args.version, args.output.resolve()))

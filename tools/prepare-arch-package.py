#!/usr/bin/env python3
"""Prepare local Arch package inputs from this checkout and prepared kernel sources."""
import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
import re
import tarfile

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / 'packaging/pipewire-sources.json'
BUNDLE = 'usr/lib/eleven-rack/backend-source'


def stage_backend_sources(stage, archives):
    """The verified PipeWire sources and tools the pacman hook builds the backend from."""
    def copy(source, target):
        dest = stage / target
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
    catalog = json.loads(CATALOG.read_text())
    for release, source in catalog.items():
        archive = archives / f'pipewire-{release}.tar.gz'
        if hashlib.sha256(archive.read_bytes()).hexdigest() != source['sha256']:
            raise RuntimeError(f'Invalid bundled PipeWire {release} source')
        copy(archive, f'{BUNDLE}/archives/{archive.name}')
    for name in ('build-latency-backend.py', 'check-latency-backend.py',
                 'install-latency-backend.py', 'spa-eleven-alsa.c'):
        copy(ROOT / 'tools' / name, f'{BUNDLE}/tools/{name}')
    copy(CATALOG, f'{BUNDLE}/packaging/pipewire-sources.json')
    for name in {'pipewire-eleven-latency.patch',
                 *(source.get('patch', 'pipewire-eleven-latency.patch') for source in catalog.values())}:
        copy(ROOT / 'packaging' / name, f'{BUNDLE}/packaging/{name}')
    copy(ROOT / 'config/52-eleven-rack-latency.conf', f'{BUNDLE}/config/52-eleven-rack-latency.conf')
    copy(ROOT / 'config/52-eleven-rack-latency.conf', 'etc/wireplumber/wireplumber.conf.d/52-eleven-rack-latency.conf')
    copy(ROOT / 'LICENSES/PipeWire-MIT.txt', 'usr/share/licenses/eleven-rack-driver/PipeWire-MIT.txt')
    modprobe = stage / 'etc/modprobe.d/eleven-rack-latency.conf'
    modprobe.parent.mkdir(parents=True, exist_ok=True)
    modprobe.write_text('# Requires the Eleven Rack patched snd_usb_audio driver.\n'
                        'options snd_usb_audio eleven_delay_hires=1\n')
    return sorted(catalog)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel-source', required=True, type=Path,
                        help='Clean Arch kernel tree after its distribution prepare() step')
    parser.add_argument('--kernel-release', required=True)
    parser.add_argument('--backend-sources', required=True, type=Path,
                        help='Verified PipeWire archives from tools/fetch-latency-sources.py')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/arch')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_.+-]+', args.kernel_release):
        parser.error('Invalid kernel release')
    source = args.kernel_source.resolve()
    if not (source / 'version').is_file() or (source / 'version').read_text().strip() != args.kernel_release:
        parser.error('Prepared Arch source version must match the target kernel release')
    usb = source / 'sound/usb'
    if not (usb / 'Makefile').is_file():
        parser.error('Kernel source must contain sound/usb/Makefile')
    if 'Eleven Rack Linux package' in (usb / 'quirks-table.h').read_text():
        parser.error('Supply clean sources without the Eleven Rack patches')
    output = args.output.resolve()
    if output == usb or usb in output.parents or output in usb.parents:
        parser.error('Output and kernel source directory must not overlap')
    version = (ROOT / 'VERSION').read_text().strip().replace('~', '')
    if not re.fullmatch(r'[A-Za-z0-9_.+]+', version):
        parser.error('Unsupported package version')
    output.mkdir(parents=True, exist_ok=True)
    project = output / 'eleven-rack-source.tar.gz'
    files = ['VERSION', 'LICENSE', 'LICENSING.md', 'CREDITS.md',
             'LICENSES/GPL-2.0.txt', 'assets/eleven-rack-control-logo-v2.png',
             'config/51-eleven-rack.conf', 'config/eleven-rack-driver.desktop',
             'tools/eleven-rack-panel.py', 'tools/eleven-rack-settings.py', 'tools/rack_devices.py',
             'tools/eleven-rack-updates.py',
             'tools/eleven-rack-meters.c', 'packaging/dkms.conf',
             'packaging/build-driver-common.sh', 'packaging/prepare-driver.py',
             'packaging/mixer-eleven-rack.h', 'packaging/fetch-arch-kernel-source.py',
             'packaging/arch/build-driver.sh', 'packaging/arch/eleven-rack-control',
             'packaging/arch/95-eleven-rack-initramfs.hook',
             'packaging/arch/96-eleven-rack-backend.hook']
    with tarfile.open(project, 'w:gz') as archive:
        for name in files:
            archive.add(ROOT / name, arcname='eleven-rack-source/' + name)
    release = output / 'kernel-release'
    release.write_text(args.kernel_release + '\n')
    kernel = output / 'eleven-rack-kernel.tar.gz'
    with tarfile.open(kernel, 'w:gz') as archive:
        archive.add(usb, arcname='eleven-rack-kernel/sound/usb')
        archive.add(release, arcname='eleven-rack-kernel/kernel-release')
    backend = output / 'eleven-rack-backend.tar.gz'
    with tempfile.TemporaryDirectory(prefix='arch-backend-') as directory:
        stage = Path(directory)
        pipewire_versions = stage_backend_sources(stage, args.backend_sources.resolve())
        with tarfile.open(backend, 'w:gz') as archive:
            archive.add(stage, arcname='eleven-rack-backend')
    recipe = (ROOT / 'packaging/arch/PKGBUILD').read_text()
    # Only pkgver: package() fills dkms.conf's own @VERSION@ from $pkgver at build time.
    recipe = recipe.replace('pkgver=@VERSION@', 'pkgver=' + version, 1)
    for marker, path in (('@PROJECT_SHA256@', project), ('@KERNEL_SHA256@', kernel), ('@BACKEND_SHA256@', backend)):
        with path.open('rb') as stream:
            recipe = recipe.replace(marker, hashlib.file_digest(stream, 'sha256').hexdigest())
    (output / 'PKGBUILD').write_text(recipe)
    shutil.copyfile(ROOT / 'packaging/arch/eleven-rack-driver.install', output / 'eleven-rack-driver.install')
    (output / 'package-target.json').write_text(json.dumps({
        'kernel_release': args.kernel_release, 'pipewire_versions': pipewire_versions, 'version': version,
    }, indent=2) + '\n')
    print('Prepared local Arch inputs:', output)
    print('Bundled kernel sources:', args.kernel_release, '(other Arch kernels are fetched by DKMS)')


if __name__ == '__main__':
    main()

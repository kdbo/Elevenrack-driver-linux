#!/usr/bin/env python3
"""Prepare local Arch package inputs from this checkout and prepared kernel sources."""
import argparse
import hashlib
from pathlib import Path
import re
import tarfile

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel-source', required=True, type=Path,
                        help='Clean Arch kernel tree after its distribution prepare() step')
    parser.add_argument('--kernel-release', required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/arch')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_.+-]+', args.kernel_release):
        parser.error('Invalid kernel release')
    usb = args.kernel_source.resolve() / 'sound/usb'
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
             'tools/eleven-rack-panel.py', 'tools/eleven-rack-settings.py',
             'tools/eleven-rack-meters.c', 'packaging/dkms.conf',
             'packaging/build-driver-common.sh', 'packaging/prepare-driver.py',
             'packaging/mixer-eleven-rack.h', 'packaging/arch/build-driver.sh',
             'packaging/arch/eleven-rack-control']
    with tarfile.open(project, 'w:gz') as archive:
        for name in files:
            archive.add(ROOT / name, arcname='eleven-rack-source/' + name)
    release = output / 'kernel-release'
    release.write_text(args.kernel_release + '\n')
    kernel = output / 'eleven-rack-kernel.tar.gz'
    with tarfile.open(kernel, 'w:gz') as archive:
        archive.add(usb, arcname='eleven-rack-kernel/sound/usb')
        archive.add(release, arcname='eleven-rack-kernel/kernel-release')
    recipe = (ROOT / 'packaging/arch/PKGBUILD').read_text()
    recipe = recipe.replace('pkgver=0.1.2beta7', 'pkgver=' + version)
    for marker, path in (('@PROJECT_SHA256@', project), ('@KERNEL_SHA256@', kernel)):
        with path.open('rb') as stream:
            recipe = recipe.replace(marker, hashlib.file_digest(stream, 'sha256').hexdigest())
    (output / 'PKGBUILD').write_text(recipe)
    print('Prepared local Arch inputs:', output)
    print('Pinned kernel:', args.kernel_release)


if __name__ == '__main__':
    main()

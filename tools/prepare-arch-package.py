#!/usr/bin/env python3
"""Prepare local Arch package inputs from this checkout and prepared kernel sources."""
import argparse
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path
import re
import tarfile

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel-source', required=True, type=Path,
                        help='Clean Arch kernel tree after its distribution prepare() step')
    parser.add_argument('--kernel-release', required=True)
    parser.add_argument('--backend-build', required=True, type=Path)
    parser.add_argument('--linux-package-version', required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/arch')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_.+-]+', args.kernel_release):
        parser.error('Invalid kernel release')
    if not re.fullmatch(r'[0-9][A-Za-z0-9_.:+-]*', args.linux_package_version):
        parser.error('Invalid linux package version')
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
    spec = importlib.util.spec_from_file_location('backend_package', ROOT / 'tools/build-latency-package.py')
    backend_package = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backend_package)
    metadata = backend_package.check_build(args.backend_build)
    if metadata['spa_plugin_dir'] != '/usr/lib/spa-0.2':
        parser.error('Build the backend in Arch using its /usr/lib/spa-0.2 plugin directory')
    pipewire_version = backend_package.dependency_version('arch', metadata)
    version = (ROOT / 'VERSION').read_text().strip().replace('~', '')
    if not re.fullmatch(r'[A-Za-z0-9_.+]+', version):
        parser.error('Unsupported package version')
    output.mkdir(parents=True, exist_ok=True)
    project = output / 'eleven-rack-source.tar.gz'
    files = ['VERSION', 'LICENSE', 'LICENSING.md', 'CREDITS.md',
             'LICENSES/GPL-2.0.txt', 'assets/eleven-rack-control-logo-v2.png',
             'config/51-eleven-rack.conf', 'config/eleven-rack-driver.desktop',
             'tools/eleven-rack-panel.py', 'tools/eleven-rack-settings.py',
             'tools/eleven-rack-updates.py',
             'tools/eleven-rack-meters.c', 'packaging/dkms.conf',
             'packaging/build-driver-common.sh', 'packaging/prepare-driver.py',
             'packaging/mixer-eleven-rack.h', 'packaging/arch/build-driver.sh',
             'packaging/arch/eleven-rack-control',
             'packaging/arch/95-eleven-rack-initramfs.hook']
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
        backend_package.stage_payload(stage, args.backend_build, metadata)
        with tarfile.open(backend, 'w:gz') as archive:
            archive.add(stage, arcname='eleven-rack-backend')
    recipe = (ROOT / 'packaging/arch/PKGBUILD').read_text()
    recipe = recipe.replace('@VERSION@', version).replace('@LINUX_VERSION@', args.linux_package_version)
    recipe = recipe.replace('@PIPEWIRE_VERSION@', pipewire_version)
    recipe = recipe.replace('@KERNEL_REGEX@', re.escape(args.kernel_release))
    for marker, path in (('@PROJECT_SHA256@', project), ('@KERNEL_SHA256@', kernel), ('@BACKEND_SHA256@', backend)):
        with path.open('rb') as stream:
            recipe = recipe.replace(marker, hashlib.file_digest(stream, 'sha256').hexdigest())
    (output / 'PKGBUILD').write_text(recipe)
    (output / 'package-target.json').write_text(json.dumps({
        'kernel_release': args.kernel_release, 'linux_package_version': args.linux_package_version,
        'pipewire_package_version': pipewire_version, 'version': version,
    }, indent=2) + '\n')
    print('Prepared local Arch inputs:', output)
    print('Pinned kernel:', args.kernel_release)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Prepare the exact Fedora source RPM matching installed kernel-devel (CI only)."""
import argparse
import json
import hashlib
from pathlib import Path
import shutil
import subprocess


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=Path('build/fedora-kernel'))
    parser.add_argument('--prep-only-dependencies', action='store_true',
                        help='Install source-preparation tools instead of full kernel build dependencies')
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    # A container's uname is the runner kernel, not Fedora's build target.
    releases = run('rpm', '-q', 'kernel-devel', '--qf', '%{VERSION}-%{RELEASE}.%{ARCH}\n').splitlines()
    if len(releases) != 1:
        raise RuntimeError('Install exactly one kernel-devel package in the CI container')
    kernel = releases[0]
    package = 'kernel-devel-'+kernel
    version = run('rpm', '-q', package, '--qf', '%{VERSION}-%{RELEASE}')
    expected = run('rpm', '-q', package, '--qf', '%{SOURCERPM}')
    headers = Path('/usr/src/kernels')/kernel
    if (headers/'include/config/kernel.release').read_text().strip() != kernel:
        raise RuntimeError('kernel-devel release mismatch')
    downloads = work/'download'
    downloads.mkdir()
    subprocess.run(['dnf', 'download', '--source', '--destdir', str(downloads), 'kernel-'+version], check=True)
    archives = list(downloads.glob('*.src.rpm'))
    if len(archives) != 1 or archives[0].name != expected:
        raise RuntimeError('Downloaded source RPM does not match kernel-devel')
    source_rpm = archives[0]
    signature = run('rpm', '--checksig', str(source_rpm))
    if 'signatures OK' not in signature:
        raise RuntimeError('Fedora source RPM must have a trusted signature: '+signature)
    actual = run('rpm', '-qp', '--qf', '%{NAME}-%{VERSION}-%{RELEASE}.src.rpm', str(source_rpm))
    if actual != expected:
        raise RuntimeError('Source RPM metadata mismatch')
    if args.prep_only_dependencies:
        # CentOS SRPM build requirements include tools for full kernel images,
        # documentation and selftests. We only execute its source %prep stage.
        subprocess.run(['dnf', 'install', '-y', 'bc', 'bison', 'flex', 'perl-core',
                        'openssl-devel', 'elfutils-libelf-devel', 'findutils',
                        'diffutils', 'tar', 'gzip', 'bzip2', 'xz', 'patch',
                        'redhat-rpm-config', 'python3-rpm-macros'], check=True)
    else:
        subprocess.run(['dnf', 'builddep', '-y', str(source_rpm)], check=True)
    top = work/'rpmbuild'
    for name in ('SOURCES', 'SPECS', 'BUILD', 'BUILDROOT', 'RPMS', 'SRPMS'):
        (top/name).mkdir(parents=True)
    subprocess.run(['rpm', '--define', '_topdir '+str(top), '-i', str(source_rpm)], check=True)
    # The RPM %prep applies Fedora patches; no full kernel image is built.
    subprocess.run(['chown', '-R', 'builder:builder', str(top)], check=True)
    dependency_flags = ['--nodeps'] if args.prep_only_dependencies else []
    subprocess.run(['runuser', '-u', 'builder', '--', 'rpmbuild', *dependency_flags, '--define', '_topdir '+str(top),
                    '--define', '_smp_mflags -j2', '-bp', '--target', 'x86_64',
                    str(top/'SPECS/kernel.spec')], check=True)
    trees = [path.parents[2] for path in (top/'BUILD').rglob('sound/usb/Makefile')]
    if len(trees) != 1:
        raise RuntimeError('Cannot select one prepared Fedora kernel tree')
    prepared = work/'prepared'
    shutil.copytree(trees[0]/'sound/usb', prepared/'sound/usb')
    identity = prepared/'include/config/kernel.release'
    identity.parent.mkdir(parents=True)
    identity.write_text(kernel+'\n')
    target = {'kernel_release': kernel, 'kernel_devel_version': version,
              'source_rpm': expected, 'source_rpm_signature': signature,
              'source_rpm_sha256': hashlib.sha256(source_rpm.read_bytes()).hexdigest()}
    (work/'target.json').write_text(json.dumps(target, indent=2)+'\n')
    print('Prepared exact Fedora kernel:', kernel)


if __name__ == '__main__':
    main()

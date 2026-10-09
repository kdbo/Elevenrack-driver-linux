#!/usr/bin/env python3
"""Cache exact Ubuntu kernel USB sources using isolated, authenticated APT lists.

No system repository files or installed packages are changed. Called by DKMS
only when a matching source archive is unavailable, or for an HWE kernel.
"""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile


def kernel_source(kernel):
    for package in (f'linux-modules-{kernel}', f'linux-image-{kernel}',
                    f'linux-headers-{kernel}'):
        result = subprocess.run(
            ['dpkg-query', '-W', '-f=${db:Status-Status} ${source:Package} ${source:Version}', package],
            capture_output=True, text=True)
        fields = result.stdout.split()
        if result.returncode == 0 and len(fields) == 3 and fields[0] == 'installed':
            name, version = fields[1:]
            if re.fullmatch(r'linux(?:-[a-z0-9.+-]+)?', name):
                return name, version
    raise RuntimeError(f'Cannot determine the installed source package for {kernel}')


def source_entries(text, deb822):
    """Preserve mirror, suite, components and signing options; enable sources only."""
    if deb822:
        entries = []
        for stanza in re.split(r'\n\s*\n', text):
            if re.search(r'^Enabled:\s*no\s*$', stanza, re.M | re.I):
                continue
            if not re.search(r'^Types:\s*(?:deb|deb-src)(?:\s|$)', stanza, re.M):
                continue
            # Refuse repositories that explicitly bypass signature verification.
            if re.search(r'^(?:Trusted|Allow-Insecure|Allow-Weak):\s*yes\s*$', stanza, re.M | re.I):
                continue
            entries.append(re.sub(r'^Types:[^\n]*(?:\n[ \t]+[^\n]*)*',
                                  'Types: deb-src', stanza, flags=re.M).strip())
        return '\n\n'.join(entries) + '\n' if entries else ''
    entries = []
    for line in text.splitlines():
        if re.match(r'^\s*deb(?:-src)?\s', line) and not re.search(
                r'(?:trusted|allow-insecure|allow-weak)\s*=\s*yes', line, re.I):
            entries.append(re.sub(r'^(\s*)deb(?:-src)?\s+', r'\1deb-src ', line))
    return '\n'.join(entries) + '\n' if entries else ''


def fetch(name, version, apt_dir, cache):
    if not re.fullmatch(r'linux(?:-[a-z0-9.+-]+)?', name):
        raise RuntimeError('Unsupported kernel source package name')
    if not re.fullmatch(r'[0-9][0-9A-Za-z.+~:-]*', version):
        raise RuntimeError('Invalid kernel source version')
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / f'{name}_{version}.tar.bz2'
    if archive.is_file():
        return archive
    print(f'Fetching exact kernel sources: {name}={version}', file=sys.stderr)
    with tempfile.TemporaryDirectory(prefix='fetch-', dir=cache) as temp:
        work = Path(temp)
        parts = work / 'sources.list.d'
        parts.mkdir()
        candidates = [apt_dir / 'sources.list']
        candidates += sorted((apt_dir / 'sources.list.d').glob('*.list'))
        candidates += sorted((apt_dir / 'sources.list.d').glob('*.sources'))
        count = 0
        for source in candidates:
            if not source.is_file():
                continue
            content = source_entries(source.read_text(), source.suffix == '.sources')
            if content:
                suffix = '.sources' if source.suffix == '.sources' else '.list'
                (parts / f'repo-{count}{suffix}').write_text(content)
                count += 1
        if not count:
            raise RuntimeError('No signed APT repositories available for kernel source retrieval')
        lists = work / 'lists'
        (lists / 'partial').mkdir(parents=True)
        config = work / 'apt.conf'
        config.write_text('#clear APT::Update::Post-Invoke;\n'
                          '#clear APT::Update::Post-Invoke-Success;\n')
        options = [
            '-c', str(config),
            '-o', 'Dir::Etc::sourcelist=-',
            '-o', f'Dir::Etc::sourceparts={parts}',
            '-o', f'Dir::State::lists={lists}',
            '-o', f'Dir::Cache::pkgcache={work / "pkgcache.bin"}',
            '-o', f'Dir::Cache::srcpkgcache={work / "srcpkgcache.bin"}',
            '-o', 'APT::Get::AllowUnauthenticated=false',
            '-o', 'Acquire::AllowInsecureRepositories=false',
            '-o', 'Acquire::AllowDowngradeToInsecureRepositories=false',
            '-o', 'APT::Update::Error-Mode=any',
        ]
        # Private temporary files are not accessible to _apt. Signature and
        # checksum verification remain enabled; no global APT setting changes.
        if os.geteuid() == 0:
            options += ['-o', 'APT::Sandbox::User=root']
        subprocess.run(['apt-get', *options, 'update'], cwd=work,
                       stdout=sys.stderr, check=True)
        subprocess.run(['apt-get', *options, '--download-only', '--only-source',
                        'source', f'{name}={version}'], cwd=work,
                       stdout=sys.stderr, check=True)
        dsc_files = list(work.glob('*.dsc'))
        if len(dsc_files) != 1:
            raise RuntimeError('Expected exactly one authenticated source package')
        tree = work / 'source'
        print('Extracting and applying Ubuntu kernel source changes…', file=sys.stderr)
        with (work / 'extract.log').open('w+') as log:
            try:
                subprocess.run(['dpkg-source', '-x', str(dsc_files[0]), str(tree)],
                               cwd=work, stdout=log, stderr=subprocess.STDOUT, check=True)
            except subprocess.CalledProcessError:
                log.seek(0)
                print(''.join(log.readlines()[-40:]), file=sys.stderr)
                raise
        usb = tree / 'sound/usb'
        if not (usb / 'Makefile').is_file():
            raise RuntimeError('Kernel source package does not contain sound/usb')
        temporary_archive = work / 'usb.tar.bz2'
        with tarfile.open(temporary_archive, 'w:bz2') as output:
            output.add(usb, arcname='linux-source/sound/usb')
        temporary_archive.chmod(0o644)
        temporary_archive.replace(archive)
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel')
    parser.add_argument('--identify', action='store_true')
    parser.add_argument('--apt-dir', type=Path, default=Path('/etc/apt'))
    parser.add_argument('--cache', type=Path,
                        default=Path(os.environ.get('ELEVEN_SOURCE_CACHE',
                                                    '/var/cache/eleven-rack/kernel-sources')))
    args = parser.parse_args()
    try:
        name, version = kernel_source(args.kernel)
        if args.identify:
            print(name, version)
        else:
            print(fetch(name, version, args.apt_dir.resolve(), args.cache.resolve()))
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'Kernel source preparation failed: {error}', file=sys.stderr)
        print('Exact sources must be available in the configured APT mirrors. '
              'Check network access and repository availability, then retry '
              f'sudo dkms autoinstall -k {args.kernel}.', file=sys.stderr)
        sys.exit(1)

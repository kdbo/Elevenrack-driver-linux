#!/usr/bin/env python3
"""Cache the sound/usb sources of an installed Arch kernel for the DKMS build.

The kernel.org tarball and Arch patch come from the package's own recipe
(.SRCINFO) at the installed version, and must match that recipe's checksums.
Only sound/usb is kept. Results are cached per kernel release, so DKMS
rebuilds of a cached kernel need no network. Prints the sound/usb directory.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

CACHE = Path('/var/cache/eleven-rack/arch-kernel')
RECIPE = 'https://gitlab.archlinux.org/archlinux/packaging/packages/{package}/-/raw/{tag}/.SRCINFO'


def kernel_package(kernel_release):
    """The headers package owning this kernel's build tree, and its version."""
    makefile = Path('/usr/lib/modules') / kernel_release / 'build/Makefile'
    owner = subprocess.check_output(['pacman', '-Qo', str(makefile)], text=True).strip()
    match = re.search(r' is owned by (\S+)-headers (\S+)$', owner)
    if not match:
        raise RuntimeError(f'Kernel {kernel_release} has no Arch *-headers package')
    return match[1], match[2]


def parse_recipe(text):
    """Fields of the pkgbase section; repeated keys become lists."""
    fields = {}
    for line in text.splitlines():
        if line.startswith('pkgname = '):
            break
        if ' = ' in line:
            key, value = line.strip().split(' = ', 1)
            fields.setdefault(key, []).append(value)
    return fields


def sources(recipe, version):
    """(url, algorithm, digest) for the kernel tarball and every patch."""
    if [f'{recipe["pkgver"][0]}-{recipe["pkgrel"][0]}'] != [version]:
        raise RuntimeError('Arch recipe does not describe the installed kernel version')
    entries = recipe.get('source', []) + recipe.get('source_x86_64', [])
    for algorithm, key in (('sha256', 'sha256sums'), ('blake2b', 'b2sums')):
        digests = recipe.get(key, []) + recipe.get(key + '_x86_64', [])
        if len(digests) == len(entries):
            break
    else:
        raise RuntimeError('Arch recipe has no checksum for every source')
    tarballs, patches = [], []
    for entry, digest in zip(entries, digests):
        url = entry.split('::', 1)[-1]
        if re.search(r'\.tar\.(xz|gz|zst)$', url):
            tarballs.append((url, algorithm, digest))
        elif re.search(r'\.patch(\.zst|\.xz)?$', url):
            patches.append((url, algorithm, digest))
    if len(tarballs) != 1 or not tarballs[0][0].startswith('https://'):
        raise RuntimeError('Expected one HTTPS kernel tarball in the Arch recipe')
    for url, _, digest in tarballs + patches:
        if digest == 'SKIP' or not url.startswith('https://'):
            raise RuntimeError(f'Refusing unverified kernel source {url}')
    return tarballs[0], patches


def download(url, algorithm, digest, target):
    hasher = hashlib.new(algorithm)
    with urllib.request.urlopen(url, timeout=60) as response, target.open('wb') as stream:
        while chunk := response.read(1 << 20):
            hasher.update(chunk)
            stream.write(chunk)
    if hasher.hexdigest() != digest:
        raise RuntimeError(f'Checksum mismatch for {url}')


def usb_sections(patch_text):
    """Only the diff sections that change sound/usb."""
    sections = re.split(r'(?m)^(?=diff --git )', patch_text)
    return ''.join(s for s in sections if re.match(r'diff --git a/sound/usb/\S+ b/sound/usb/', s))


def extract_usb(tarball, tree):
    with tarfile.open(tarball, 'r|*') as archive:
        for member in archive:
            parts = member.name.split('/', 3)
            if len(parts) > 2 and parts[1:3] == ['sound', 'usb']:
                member.name = '/'.join(parts[1:])
                archive.extract(member, tree, filter='data')
    if not (tree / 'sound/usb/Makefile').is_file():
        raise RuntimeError('Kernel tarball contains no sound/usb sources')


def apply_patch(patch, tree):
    if patch.suffix in ('.zst', '.xz'):
        tool = 'zstd' if patch.suffix == '.zst' else 'xz'
        text = subprocess.check_output([tool, '-dcq', str(patch)], text=True)
    else:
        text = patch.read_text()
    text = usb_sections(text)
    if text:
        subprocess.run(['patch', '--batch', '--forward', '--fuzz=0', '-p1'],
                       input=text, text=True, cwd=tree, check=True, stdout=subprocess.DEVNULL)


def prepare(kernel_release, cache):
    package, version = kernel_package(kernel_release)
    target = cache / kernel_release
    stamp = target / 'source.json'
    if stamp.is_file() and json.loads(stamp.read_text()).get('version') == version:
        return target / 'sound/usb'
    tag = version.replace(':', '-')
    with urllib.request.urlopen(RECIPE.format(package=package, tag=tag), timeout=60) as response:
        recipe = parse_recipe(response.read().decode())
    tarball, patches = sources(recipe, version)
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fetch-', dir=cache) as directory:
        work = Path(directory)
        tree = work / 'tree'
        archive = work / Path(tarball[0]).name
        print(f'Downloading {package} {version} kernel sources...', file=sys.stderr, flush=True)
        download(*tarball, archive)
        extract_usb(archive, tree)
        archive.unlink()
        for url, algorithm, digest in patches:
            patch = work / Path(url).name
            download(url, algorithm, digest, patch)
            apply_patch(patch, tree)
        (tree / 'source.json').write_text(json.dumps({
            'package': package, 'version': version, 'kernel_release': kernel_release,
            'tarball': tarball[0], 'patches': [p[0] for p in patches]}, indent=2) + '\n')
        if target.exists():
            shutil.rmtree(target)
        tree.rename(target)
    return target / 'sound/usb'


def prune(cache):
    """Drop cached sources of kernels that are no longer installed."""
    if cache.is_dir():
        for entry in cache.iterdir():
            if entry.is_dir() and not entry.name.startswith('fetch-') and \
                    not (Path('/usr/lib/modules') / entry.name).is_dir():
                shutil.rmtree(entry)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel_release')
    parser.add_argument('--cache', type=Path, default=CACHE)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_.+-]+', args.kernel_release):
        parser.error('Invalid kernel release')
    try:
        prune(args.cache)
        print(prepare(args.kernel_release, args.cache))
    except (OSError, RuntimeError, subprocess.CalledProcessError, tarfile.TarError) as error:
        print(f'Cannot prepare Arch kernel sources for {args.kernel_release}: {error}', file=sys.stderr)
        raise SystemExit(1)

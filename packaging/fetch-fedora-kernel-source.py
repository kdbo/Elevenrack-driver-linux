#!/usr/bin/env python3
"""Cache the sound/usb sources of an installed Fedora or CentOS Stream kernel for DKMS.

The source RPM is the one named by the kernel-devel package of that kernel,
downloaded from Fedora's build system or the CentOS Stream mirror, and must
carry a signature that rpm trusts. Fedora deletes its signed copies of older
builds but keeps their signature headers; the signed RPM is then rebuilt from
the unsigned one and that header, as Fedora's build system does itself. Only sound/usb of its kernel tarball is kept,
with the sound/usb parts of the patches its spec applies. Results are cached
per kernel release, so DKMS rebuilds of a cached kernel need no network.
Prints the sound/usb directory.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request

CACHE = Path('/var/cache/eleven-rack/fedora-kernel')
FEDORA = 'https://kojipkgs.fedoraproject.org/packages/{name}/{version}/{release}/'
CENTOS = 'https://mirror.stream.centos.org/{major}-stream/BaseOS/source/tree/Packages/{srpm}'


def source_rpm(kernel_release):
    """The source RPM file name of the kernel-devel package for this kernel."""
    makefile = Path('/usr/src/kernels') / kernel_release / 'Makefile'
    if not makefile.is_file():
        raise RuntimeError(f'kernel-devel for {kernel_release} is not installed')
    srpm = subprocess.check_output(['rpm', '-qf', '--qf', '%{SOURCERPM}\n', str(makefile)], text=True).strip()
    if not re.fullmatch(r'[A-Za-z0-9_.+-]+-[^-/]+-[^-/]+\.src\.rpm', srpm):
        raise RuntimeError(f'Unexpected source package {srpm!r} for {kernel_release}')
    return srpm


def signing_keys(url):
    """Signing key directories listed at a koji URL; none if it is missing."""
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            return re.findall(r'href="([0-9a-f]{8})/"', response.read().decode())
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return []
        raise


def candidates(srpm):
    """(source RPM URL, signature header URL or None), most likely first."""
    name, version, release = re.fullmatch(r'(.+)-([^-]+)-([^-]+)\.src\.rpm', srpm).groups()
    if re.search(r'\.fc\d+$', release):
        base = FEDORA.format(name=name, version=version, release=release)
        found = [(f'{base}data/signed/{key}/src/{srpm}', None) for key in signing_keys(base+'data/signed/')]
        found += [(f'{base}src/{srpm}', f'{base}data/sigcache/{key}/src/{srpm}.sig')
                  for key in signing_keys(base+'data/sigcache/')]
        if not found:
            raise RuntimeError(f'Fedora has no signed copy or signature of {srpm}')
        return found
    centos = re.search(r'\.el(\d+)$', release)
    if centos:
        return [(CENTOS.format(major=centos[1], srpm=srpm), None)]
    raise RuntimeError(f'Unsupported distribution for {srpm}')


def header_size(data):
    """Length of the RPM header structure at the start of data."""
    if data[:3] != b'\x8e\xad\xe8':
        raise RuntimeError('Malformed RPM signature header')
    entries, size = struct.unpack('>II', data[8:16])
    return 16 + 16*entries + size


def read_exact(stream, size):
    data = stream.read(size)
    if len(data) != size:
        raise RuntimeError('Truncated download')
    return data


def download(url, target, signature_url=None):
    """Save the RPM; with signature_url, replace its signature header by that one."""
    with urllib.request.urlopen(url, timeout=60) as response, target.open('wb') as stream:
        if signature_url:
            with urllib.request.urlopen(signature_url, timeout=60) as signature:
                header = signature.read(1 << 20)
            # Koji may store the header with its padding to 8 bytes.
            size = header_size(header)
            if len(header) - size not in range(8) or header[size:].strip(b'\0'):
                raise RuntimeError('Malformed signature header')
            header = header[:size]
            lead = read_exact(response, 96 + 16)
            # Skip the unsigned RPM's own signature header and its padding to 8 bytes.
            old = header_size(lead[96:])
            read_exact(response, old + (8 - old % 8) % 8 - 16)
            stream.write(lead[:96] + header + b'\0' * ((8 - len(header) % 8) % 8))
        shutil.copyfileobj(response, stream, 1 << 20)


def verify(path, srpm):
    """Require a trusted signature and the expected package identity."""
    result = subprocess.run(['rpm', '--checksig', str(path)], capture_output=True, text=True)
    if result.returncode != 0 or 'signatures OK' not in result.stdout:
        raise RuntimeError(f'{srpm} has no trusted signature: {(result.stdout + result.stderr).strip()}')
    actual = subprocess.check_output(['rpm', '-qp', '--qf', '%{NAME}-%{VERSION}-%{RELEASE}.src.rpm', str(path)],
                                     text=True).strip()
    if actual != srpm:
        raise RuntimeError(f'Downloaded {actual}, expected {srpm}')


class Member:
    """Read-only view of one cpio member, for streaming it into tarfile."""

    def __init__(self, stream, size):
        self.stream, self.left = stream, size

    def read(self, size=-1):
        size = self.left if size < 0 else min(size, self.left)
        data = self.stream.read(size)
        self.left -= len(data)
        return data


def cpio_members(stream):
    """(name, reader, size) for each member of a newc cpio stream."""
    while True:
        header = stream.read(110)
        if len(header) < 110 or header[:6] not in (b'070701', b'070702'):
            raise RuntimeError('Malformed source RPM payload')
        size, name_size = int(header[54:62], 16), int(header[94:102], 16)
        name = stream.read(name_size)[:-1].decode()
        stream.read((4 - (110 + name_size) % 4) % 4)
        if name == 'TRAILER!!!':
            return
        member = Member(stream, size)
        yield name.removeprefix('./'), member, size
        while member.read(1 << 20):
            pass
        stream.read((4 - size % 4) % 4)


def extract_usb(archive, tree):
    with tarfile.open(fileobj=archive, mode='r|*') as tar:
        for member in tar:
            parts = member.name.split('/', 3)
            if len(parts) > 2 and parts[1:3] == ['sound', 'usb']:
                member.name = '/'.join(parts[1:])
                tar.extract(member, tree, filter='data')
    if not (tree / 'sound/usb/Makefile').is_file():
        raise RuntimeError('Kernel tarball contains no sound/usb sources')


def applied_patches(spec, names):
    """Patch files of the source RPM that the spec's %prep applies, in order."""
    patches = []
    for line in re.findall(r'(?m)^\s*Apply(?:Optional)?Patch\s+(\S+)', spec):
        pattern = re.escape(line)
        pattern = re.sub(r'%\\\{[^}]*\\\}', '[^/]*', pattern)
        matches = [n for n in names if re.fullmatch(pattern, n)]
        if len(matches) > 1:
            raise RuntimeError(f'Ambiguous patch {line} in the kernel spec')
        patches += matches
    return patches


def usb_sections(patch_text):
    """Only the diff sections that change sound/usb."""
    sections = re.split(r'(?m)^(?=diff --git )', patch_text)
    return ''.join(s for s in sections if re.match(r'diff --git a/sound/usb/\S+ b/sound/usb/', s))


def unpack(path, tree):
    """Extract sound/usb with the spec's patches from a verified source RPM."""
    texts, tarballs = {}, 0
    rpm2cpio = subprocess.Popen(['rpm2cpio', str(path)], stdout=subprocess.PIPE)
    try:
        for name, member, size in cpio_members(rpm2cpio.stdout):
            if re.fullmatch(r'linux-\d[^/]*\.tar\.(xz|gz|bz2)', name):
                tarballs += 1
                extract_usb(member, tree)
            elif name.endswith(('.patch', '.spec')) and size < 64 << 20:
                texts[name] = member.read().decode(errors='replace')
    finally:
        rpm2cpio.stdout.close()
        status = rpm2cpio.wait()
    if status != 0:
        raise RuntimeError('Cannot read the source RPM payload')
    specs = [text for name, text in texts.items() if name.endswith('.spec')]
    if tarballs != 1 or len(specs) != 1:
        raise RuntimeError('Expected one kernel tarball and one spec in the source RPM')
    patches = applied_patches(specs[0], [n for n in texts if n.endswith('.patch')])
    for name in patches:
        text = usb_sections(texts[name])
        if text:
            subprocess.run(['patch', '--batch', '--forward', '--fuzz=0', '-p1'],
                           input=text, text=True, cwd=tree, check=True, stdout=subprocess.DEVNULL)
    return patches


def prepare(kernel_release, cache):
    srpm = source_rpm(kernel_release)
    target = cache / kernel_release
    stamp = target / 'source.json'
    if stamp.is_file() and json.loads(stamp.read_text()).get('source_rpm') == srpm:
        return target / 'sound/usb'
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fetch-', dir=cache) as directory:
        work = Path(directory)
        path, errors = work / srpm, []
        print(f'Downloading {srpm} (about 170 MB) for the Eleven Rack driver...', file=sys.stderr, flush=True)
        for url, signature in candidates(srpm):
            try:
                download(url, path, signature)
                verify(path, srpm)
                break
            except (OSError, RuntimeError) as error:
                errors.append(f'{url}: {error}')
        else:
            raise RuntimeError('; '.join(errors))
        tree = work / 'tree'
        patches = unpack(path, tree)
        path.unlink()
        (tree / 'source.json').write_text(json.dumps({
            'source_rpm': srpm, 'url': url, 'signature': signature, 'kernel_release': kernel_release,
            'patches': patches}, indent=2) + '\n')
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
        print(f'Cannot prepare kernel sources for {args.kernel_release}: {error}', file=sys.stderr)
        raise SystemExit(1)

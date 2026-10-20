#!/usr/bin/env python3
"""Build the Eleven Rack PCM backend for a specific PipeWire version and distro."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent.parent


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def installed_version():
    for command in (('pipewire', '--version'),
                    ('pkg-config', '--modversion', 'libpipewire-0.3')):
        try:
            lines = run(*command).splitlines()
        except (OSError, subprocess.CalledProcessError):
            continue
        match = re.search(r'(\d+\.\d+\.\d+)', lines[-1]) if lines else None
        if match:
            return match[1]
    raise RuntimeError('Cannot determine installed PipeWire version; install pipewire '
                       'or its development metadata, or specify --pipewire-version')


def native_multiarch():
    """The host's multiarch triplet, e.g. x86_64-linux-gnu, or None if unknown."""
    for command in (('dpkg-architecture', '-qDEB_HOST_MULTIARCH'),
                    (*shlex.split(os.environ.get('CC', 'cc')), '-print-multiarch')):
        try:
            value = run(*command)
        except (OSError, subprocess.CalledProcessError):
            continue
        if re.fullmatch(r'[a-z0-9_]+-linux-[a-z0-9_]+', value):
            return value
    return None


def plugin_directory(root=Path('/'), multiarch=native_multiarch):
    try:
        path = run('pkg-config', '--variable=plugindir', 'libspa-0.2')
        if path and (Path(path) / 'alsa/libspa-alsa.so').is_file():
            return Path(path)
    except (OSError, subprocess.CalledProcessError):
        pass
    # Runtime packages do not always install the pkg-config metadata.
    matches = {p.resolve().parent.parent for pattern in (
        'usr/lib/spa-0.2/alsa/libspa-alsa.so',
        'usr/lib64/spa-0.2/alsa/libspa-alsa.so',
        'usr/lib/*-linux-gnu/spa-0.2/alsa/libspa-alsa.so')
        for p in root.glob(pattern)}
    if len(matches) > 1:
        # Multiarch systems can also carry foreign plugins, e.g. i386 ones
        # installed for 32-bit applications; build for the native one.
        triplet = multiarch()
        native = {m for m in matches if triplet and m.parent.name == triplet}
        if len(native) == 1:
            return native.pop()
    if len(matches) != 1:
        found = ', '.join(sorted(map(str, matches))) or 'none'
        raise RuntimeError(f'Cannot locate one system SPA directory (found: {found}); '
                           'specify --spa-plugin-dir')
    return matches.pop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pipewire-version', help='Defaults to the installed PipeWire version')
    parser.add_argument('--archive', type=Path, help='Local pristine upstream PipeWire tar.gz')
    parser.add_argument('--sha256', help='Required for versions outside packaging/pipewire-sources.json')
    parser.add_argument('--spa-plugin-dir', type=Path, help='System SPA directory on the target distro')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/latency')
    args = parser.parse_args()
    version = args.pipewire_version or installed_version()
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        parser.error('Invalid PipeWire version')
    sources = json.loads((ROOT / 'packaging/pipewire-sources.json').read_text())
    source = sources.get(version, {})
    expected = args.sha256 or source.get('sha256')
    if not expected or not re.fullmatch(r'[a-fA-F0-9]{64}', expected):
        parser.error(f'PipeWire {version} has no valid source checksum; supply --archive '
                     'and --sha256 or add this release to packaging/pipewire-sources.json')
    if not source and not args.archive:
        parser.error(f'Supply --archive for unlisted PipeWire {version}')
    spa_dir = args.spa_plugin_dir or plugin_directory()
    # These paths are embedded in C and systemd configuration; reject control characters.
    if not re.fullmatch(r'/[A-Za-z0-9_./+-]+', str(spa_dir)):
        parser.error('SPA plugin directory must be a simple absolute path')
    original = spa_dir / 'alsa/libspa-alsa.so'
    if not original.is_file() or 'eleven-rack' in str(original):
        parser.error('SPA directory must contain the original distribution ALSA plugin')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='eleven-pipewire-') as directory:
        work = Path(directory)
        archive = args.archive
        if archive is None:
            archive = work / 'pipewire.tar.gz'
            print('Downloading', source['url'], flush=True)
            urllib.request.urlretrieve(source['url'], archive)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest.lower() != expected.lower():
            raise RuntimeError('PipeWire archive SHA-256 mismatch; refusing to patch/build')
        with tarfile.open(archive) as bundle:
            # data filter rejects path traversal and unsafe links/devices.
            bundle.extractall(work, filter='data')
        tree = work / f'pipewire-{version}'
        if not (tree / 'spa/plugins/alsa/alsa-pcm.c').is_file():
            raise RuntimeError('Archive does not contain the requested PipeWire source tree')
        patch = ROOT / 'packaging' / source.get('patch', 'pipewire-eleven-latency.patch')
        subprocess.run(['patch', '--batch', '--forward', '--fuzz=0', '-p1', '-i', str(patch)],
                       cwd=tree, check=True)
        library = work / 'libspa-eleven-latency.so'
        command = shlex.split(os.environ.get('CC', 'cc')) + [
            '-shared', '-fPIC', '-Wl,-Bsymbolic', '-Wl,-z,defs', '-O2', '-Wall', '-Wextra', '-Werror',
            '-Wno-unused-parameter', '-Wno-missing-field-initializers',
            f'-DELEVEN_SYSTEM_ALSA_PLUGIN="{original}"',
            f'-I{tree / "spa/include"}', f'-I{tree / "spa/plugins/alsa"}',
            str(ROOT / 'tools/spa-eleven-alsa.c')]
        command += [str(tree / 'spa/plugins/alsa' / name) for name in (
            'alsa-pcm.c', 'alsa-pcm-source.c', 'alsa-pcm-sink.c', 'alsa-pcm-device.c')]
        command += ['-lasound', '-lm', '-ldl', '-o', str(library)]
        subprocess.run(command, check=True)
        subprocess.run(['ldd', '-r', str(library)], check=True)
        # Publish only after successful compilation and linking.
        metadata = {
            'pipewire_version': version, 'source_sha256': digest,
            'patch_sha256': hashlib.sha256(patch.read_bytes()).hexdigest(),
            'spa_plugin_dir': str(spa_dir), 'system_alsa_plugin': str(original),
            'machine': run('uname', '-m'),
            'library_sha256': hashlib.sha256(library.read_bytes()).hexdigest(),
            'correction_config_sha256': hashlib.sha256(
                (ROOT / 'config/52-eleven-rack-latency.conf').read_bytes()).hexdigest(),
            'corrections': 'Ubuntu measurement defaults; unvalidated on other distributions',
        }
        (output / 'libspa-eleven-latency.so').write_bytes(library.read_bytes())
        (output / 'backend-build.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print('Built', output / 'libspa-eleven-latency.so')


if __name__ == '__main__':
    main()

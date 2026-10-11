#!/usr/bin/env python3
"""Build the bundled backend for installed PipeWire without downloading sources."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
GENERATED = (
    'usr/lib/eleven-rack/spa/alsa/libspa-alsa.so',
    'usr/lib/systemd/user/pipewire.service.d/60-eleven-rack-latency.conf',
    'usr/lib/systemd/user/wireplumber.service.d/60-eleven-rack-latency.conf',
    'var/lib/eleven-rack/latency/backend-build.json',
)


def builder():
    spec = importlib.util.spec_from_file_location('latency_builder', ROOT / 'tools/build-latency-backend.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def install(source_root, destination):
    build = builder()
    version = build.installed_version()
    spa_dir = build.plugin_directory()
    catalog = json.loads((source_root / 'packaging/pipewire-sources.json').read_text())
    source = catalog.get(version)
    if source is None:
        raise RuntimeError(f'PipeWire {version} is not in the bundled source catalog; '
                           'install an updated Eleven Rack driver package. No Ubuntu version selection is required.')
    archive = source_root / 'archives' / f'pipewire-{version}.tar.gz'
    if hashlib.sha256(archive.read_bytes()).hexdigest() != source['sha256']:
        raise RuntimeError('Bundled PipeWire source checksum mismatch')
    state = destination / 'var/lib/eleven-rack/latency'
    metadata_path = state / 'backend-build.json'
    library = destination / GENERATED[0]
    patch = source_root / 'packaging' / source.get('patch', 'pipewire-eleven-latency.patch')
    config = source_root / 'config/52-eleven-rack-latency.conf'
    expected = {
        'pipewire_version': version,
        'source_sha256': source['sha256'],
        'patch_sha256': hashlib.sha256(patch.read_bytes()).hexdigest(),
        'correction_config_sha256': hashlib.sha256(config.read_bytes()).hexdigest(),
        'spa_plugin_dir': str(spa_dir),
        'wrapper_sha256': hashlib.sha256((source_root / 'tools/spa-eleven-alsa.c').read_bytes()).hexdigest(),
        'builder_sha256': hashlib.sha256((source_root / 'tools/build-latency-backend.py').read_bytes()).hexdigest(),
    }
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    cached = all(metadata.get(key) == value for key, value in expected.items())
    cached = cached and library.exists() and hashlib.sha256(library.read_bytes()).hexdigest() == metadata.get('library_sha256')
    state.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='build-', dir=state) as temporary:
        work = Path(temporary)
        if not cached:
            subprocess.run([sys.executable, str(source_root / 'tools/build-latency-backend.py'),
                            '--archive', str(archive), '--output', str(work)], check=True)
            subprocess.run([sys.executable, str(source_root / 'tools/check-latency-backend.py'),
                            '--build', str(work)], check=True)
            built_metadata = json.loads((work / 'backend-build.json').read_text())
            built_metadata['wrapper_sha256'] = expected['wrapper_sha256']
            built_metadata['builder_sha256'] = expected['builder_sha256']
            (work / 'backend-build.json').write_text(json.dumps(built_metadata, indent=2) + '\n')
            for source_file, target in ((work / 'libspa-eleven-latency.so', library),
                                        (work / 'backend-build.json', metadata_path)):
                target.parent.mkdir(parents=True, exist_ok=True)
                staged = target.with_suffix(target.suffix + '.new')
                shutil.copyfile(source_file, staged)
                staged.chmod(0o644)
                os.replace(staged, target)
        # Write only after the native backend has compiled and passed its checks.
        for name in GENERATED[1:3]:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('[Service]\nEnvironment=SPA_PLUGIN_DIR=/usr/lib/eleven-rack/spa:' + str(spa_dir) + '\n')
            target.chmod(0o644)
    print(f'Eleven Rack backend ready for installed PipeWire {version}')


def remove(destination):
    for name in GENERATED:
        (destination / name).unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--destination', type=Path, default=Path('/'))
    parser.add_argument('--remove', action='store_true')
    args = parser.parse_args()
    if args.remove:
        remove(args.destination)
    else:
        try:
            install(args.source_root, args.destination)
        except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
            # A previous backend must not stay active after an incompatible update.
            remove(args.destination)
            print(f'Eleven Rack backend installation failed: {error}', file=sys.stderr)
            raise SystemExit(1)

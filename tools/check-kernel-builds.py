#!/usr/bin/env python3
"""Compile the packaged driver against cached Ubuntu kernel .debs without root.

Downloads and system installation are deliberately separate from build testing.
Supply source/common-header/generic-header .debs in --cache. Logs and JSON
results go to build/compatibility; SDK extraction and compiler output stay in
--work-dir. Nothing is installed, loaded, or written to the host kernel tree.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def check(release, entry, cache, work, output):
    kernel = entry['kernel']
    base = kernel.removesuffix('-generic')
    version = entry['version']
    source = f"linux-source-{entry['series']}.0_{version}_all.deb"
    files = [source, f'linux-headers-{base}_{version}_all.deb',
             f'linux-headers-{kernel}_{version}_amd64.deb']
    missing = [name for name in files if not (cache / name).is_file()]
    if missing:
        raise RuntimeError('Missing cached packages: ' + ', '.join(missing))
    sdk = work / release / 'sdk'
    sdk.mkdir(parents=True, exist_ok=True)
    fingerprints = {}
    for name in files:
        with (cache / name).open('rb') as stream:
            fingerprints[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
    stamp = sdk / '.packages.json'
    if not stamp.exists() or json.loads(stamp.read_text()) != fingerprints:
        for name in files:
            subprocess.run(['dpkg-deb', '-x', str(cache / name), str(sdk)], check=True)
        stamp.write_text(json.dumps(fingerprints, indent=2) + '\n')
    build = work / release / 'build'
    build.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / 'packaging/prepare-driver.py', build / 'prepare-driver.py')
    headers = sdk / 'usr/src' / ('linux-headers-' + kernel)
    archive = sdk / 'usr/src' / f"linux-source-{entry['series']}.0.tar.bz2"
    env = dict(os.environ, ELEVEN_SOURCE_ARCHIVE=str(archive))
    output.mkdir(parents=True, exist_ok=True)
    log = output / f'ubuntu-{release}.log'
    print(f'Ubuntu {release}: building for {kernel}', flush=True)
    with log.open('w') as stream:
        result = subprocess.run(['bash', str(ROOT / 'packaging/build-driver.sh'),
                                 kernel, str(headers)], cwd=build, env=env,
                                stdout=stream, stderr=subprocess.STDOUT)
    metadata = dict(entry, ubuntu=release, package_sha256=fingerprints,
                    build_exit_code=result.returncode,
                    prepare_driver_sha256=hashlib.sha256(
                        (build / 'prepare-driver.py').read_bytes()).hexdigest(),
                    hardware_tested=False, full_os_install_tested=False,
                    log=str(log.relative_to(ROOT)))
    if result.returncode == 0:
        module = build / 'kernel-source/sound/usb/snd-usb-audio.ko'
        metadata['vermagic'] = subprocess.check_output(
            ['modinfo', '-F', 'vermagic', str(module)], text=True).strip()
        if not metadata['vermagic'].startswith(kernel + ' '):
            raise RuntimeError('Built module has incorrect kernel vermagic')
        metadata['module_sha256'] = hashlib.sha256(module.read_bytes()).hexdigest()
    (output / f'ubuntu-{release}.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(f"Ubuntu {release}: {'PASS' if result.returncode == 0 else 'FAIL'} — {log}", flush=True)
    return result.returncode


if __name__ == '__main__':
    matrix = json.loads((ROOT / 'packaging/ubuntu-kernels.json').read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--releases', nargs='+', choices=matrix, default=list(matrix))
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    args = parser.parse_args()
    failed = False
    for release in args.releases:
        try:
            failed |= bool(check(release, matrix[release], args.cache.resolve(),
                                 args.work_dir.resolve(), ROOT / 'build/compatibility'))
        except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
            print(f'Ubuntu {release}: {error}', file=sys.stderr, flush=True)
            failed = True
    sys.exit(1 if failed else 0)

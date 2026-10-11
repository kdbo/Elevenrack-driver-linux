#!/usr/bin/env python3
"""Download and verify the source archives bundled in the universal Ubuntu driver."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import urllib.request

ROOT = Path(__file__).resolve().parent.parent


def fetch(output):
    output.mkdir(parents=True, exist_ok=True)
    catalog = json.loads((ROOT / 'packaging/pipewire-sources.json').read_text())
    for version, source in catalog.items():
        if not re.fullmatch(r'\d+\.\d+\.\d+', version):
            raise RuntimeError('Invalid source version')
        archive = output / f'pipewire-{version}.tar.gz'
        if not archive.exists():
            temporary = archive.with_suffix('.download')
            try:
                urllib.request.urlretrieve(source['url'], temporary)
                if hashlib.sha256(temporary.read_bytes()).hexdigest() != source['sha256']:
                    raise RuntimeError(f'Source checksum mismatch for PipeWire {version}')
                temporary.replace(archive)
            finally:
                temporary.unlink(missing_ok=True)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != source['sha256']:
            raise RuntimeError(f'Source checksum mismatch for PipeWire {version}')
        print('Verified', archive)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/latency-sources')
    fetch(parser.parse_args().output)

#!/usr/bin/env python3
"""Check availability of pinned kernel build inputs without downloading them."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parent.parent
MIRRORS = ('https://archive.ubuntu.com/ubuntu', 'https://old-releases.ubuntu.com/ubuntu')


def probe(item):
    release, name = item
    attempts = []
    for mirror in MIRRORS:
        url = f'{mirror}/pool/main/l/linux/{name}'
        try:
            request = urllib.request.Request(url, method='HEAD')
            with urllib.request.urlopen(request, timeout=25) as response:
                if response.status == 200:
                    return {'ubuntu': release, 'package': name, 'available': True,
                            'url': url, 'attempts': attempts}
        except (OSError, urllib.error.URLError) as error:
            attempts.append({'url': url, 'error': str(error)})
    return {'ubuntu': release, 'package': name, 'available': False, 'attempts': attempts}


def main():
    matrix = json.loads((ROOT / 'packaging/ubuntu-kernels.json').read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--releases', nargs='+', choices=matrix, default=['24.10', '25.04', '25.10'])
    parser.add_argument('--output', type=Path, default=ROOT / 'build/kernel-package-availability.json')
    args = parser.parse_args()
    items = []
    for release in args.releases:
        entry = matrix[release]
        version, kernel = entry['version'], entry['kernel']
        names = [f"linux-source-{entry['series']}.0_{version}_all.deb",
                 f"linux-headers-{kernel.removesuffix('-generic')}_{version}_all.deb",
                 f'linux-headers-{kernel}_{version}_amd64.deb']
        items.extend((release, name) for name in names)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(probe, items))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'checked_at': datetime.now(timezone.utc).isoformat(),
                                      'scope': 'Pinned amd64 build inputs; not latest kernels or full installation',
                                      'results': results}, indent=2) + '\n')
    for result in results:
        print(f"Ubuntu {result['ubuntu']}: {'AVAILABLE' if result['available'] else 'UNAVAILABLE'} {result['package']}")
        if result['available']:
            print('  ' + result['url'])
    return 0 if all(r['available'] for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())

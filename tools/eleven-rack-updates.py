#!/usr/bin/env python3
"""Read-only release checks shared by Control and the Linux Editor."""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import shlex
import time
import urllib.request
from urllib.parse import quote

REPOSITORY = 'kdbo/Elevenrack-driver-linux'
RELEASES = 'https://github.com/' + REPOSITORY + '/releases'
API = 'https://api.github.com/repos/' + REPOSITORY + '/releases?per_page=100'
MAX_RESPONSE = 4 * 1024 * 1024


def version_key(value):
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)(?:[-~_.]?((?:alpha|beta|rc))(\d+))?', value)
    if not match:
        return None
    major, minor, patch, stage, number = match.groups()
    return (int(major), int(minor), int(patch),
            {None: 3, 'rc': 2, 'beta': 1, 'alpha': 0}[stage], int(number or 0))


def host_target():
    try:
        info = platform.freedesktop_os_release()
    except OSError:
        info = {}
    return {'distro': info.get('ID', ''), 'release': info.get('VERSION_ID', ''),
            'arch': platform.machine()}


def package_matches(name, component, target):
    prefix = 'eleven-rack-driver' if component == 'driver' else 'eleven-rack-editor-linux'
    if not re.fullmatch(r'[A-Za-z0-9_.+~%-]+', name) or not name.startswith(prefix + ('_' if target['distro'] == 'ubuntu' else '-')):
        return False
    if target['arch'] not in ('x86_64', 'amd64'):
        return False
    distro = target['distro']
    if distro == 'ubuntu':
        return name.endswith(('_all.deb', '_amd64.deb'))
    if distro == 'fedora':
        return bool(re.search(r'\.fc' + re.escape(target['release']) + r'\.x86_64\.rpm$', name))
    if distro == 'centos' and target['release'].split('.')[0] == '10':
        return name.endswith('.el10.x86_64.rpm')
    if distro == 'arch':
        return name.endswith('-x86_64.pkg.tar.zst')
    return False


def package_version(name, component, distro):
    prefix = 'eleven-rack-driver' if component == 'driver' else 'eleven-rack-editor-linux'
    separator = '_' if distro == 'ubuntu' else '-'
    value = name[len(prefix) + 1:]
    return version_key(value.split(separator, 1)[0])


def select_update(releases, installed, component, target):
    current = version_key(installed)
    result = {'status': 'current', 'installed': installed}
    if current is None:
        return dict(result, status='unknown', message='Cannot compare this development version.')
    if target['distro'] not in ('ubuntu', 'fedora', 'centos', 'arch') or target['arch'] not in ('x86_64', 'amd64'):
        return dict(result, status='unsupported', message='No update packages configured for this system.')
    candidates = []
    for release in releases:
        if not isinstance(release, dict) or release.get('draft'):
            continue
        tag = release.get('tag_name', '')
        key = version_key(tag)
        if key is None or key <= current:
            continue
        # Stable installations follow stable releases; beta installations also see betas.
        if current[3] == 3 and (release.get('prerelease') or key[3] != 3):
            continue
        assets = release.get('assets', [])
        if not isinstance(assets, list):
            continue
        packages = sorted(asset['name'] for asset in assets
                          if isinstance(asset, dict) and isinstance(asset.get('name'), str)
                          and asset.get('state', 'uploaded') == 'uploaded'
                          and package_matches(asset['name'], component, target)
                          and package_version(asset['name'], component, target['distro']) == key)
        if len(packages) != 1:
            continue  # Ambiguous sets need an explicit target manifest before proposing an install.
        command = {'ubuntu': 'sudo apt install', 'fedora': 'sudo dnf install',
                   'centos': 'sudo dnf install', 'arch': 'sudo pacman -U'}[target['distro']]
        candidates.append((key, dict(result, status='available', version=tag.lstrip('v'),
                                    url=RELEASES + '/tag/' + quote(tag, safe=''),
                                    package=packages[0], command=command + ' ' + shlex.quote('./' + packages[0]),
                                    message='Download the package and its checksums, verify them, then run the command in the download folder. Check the release’s kernel and PipeWire requirements first.'
                                    + (' Reboot after installing the driver.' if component == 'driver'
                                       else ' Close the Editor before installing, then reopen it.'))))
    return max(candidates, key=lambda item: item[0])[1] if candidates else result


def check_updates(installed, component, force=False):
    target = host_target()
    cache = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'eleven-rack' / ('updates-' + component + '.json')
    identity = {'installed': installed, 'target': target}
    if not force:
        try:
            saved = json.loads(cache.read_text())
            if saved['identity'] == identity and 0 <= time.time() - saved['time'] < 86400:
                return saved['result']
        except (OSError, ValueError, KeyError, TypeError):
            pass
    try:
        request = urllib.request.Request(API, headers={'Accept': 'application/vnd.github+json',
                                                       'User-Agent': 'Eleven-Rack-Linux-update-check'})
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = response.read(MAX_RESPONSE + 1)
        if len(payload) > MAX_RESPONSE:
            raise ValueError('Release response too large')
        releases = json.loads(payload)
        if not isinstance(releases, list):
            raise ValueError('Invalid release response')
        result = select_update(releases, installed, component, target)
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            temporary = cache.with_suffix('.%d.tmp' % os.getpid())
            temporary.write_text(json.dumps({'identity': identity, 'time': time.time(), 'result': result}))
            temporary.replace(cache)
        except OSError:
            pass
        return result
    except (OSError, ValueError, TypeError, KeyError):
        return {'status': 'offline', 'installed': installed,
                'message': 'Could not check for updates. Check your connection and try again.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    parser.add_argument('--component', choices=('driver', 'editor'), required=True)
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    print(json.dumps(check_updates(args.version, args.component, args.force)))


if __name__ == '__main__':
    main()

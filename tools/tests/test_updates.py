import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('updates', Path(__file__).resolve().parents[1] / 'eleven-rack-updates.py')
updates = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updates)


def release(tag, *packages, **flags):
    return {'tag_name': tag, 'assets': [{'name': p, 'state': 'uploaded'} for p in packages], **flags}


class UpdatesTest(unittest.TestCase):
    def select(self, releases, installed='0.1.2~beta8', component='driver', distro='ubuntu', version='24.04', arch='x86_64'):
        return updates.select_update(releases, installed, component,
                                     {'distro': distro, 'release': version, 'arch': arch})

    def test_version_formats_and_numeric_beta_order(self):
        for version in ('v0.1.2-beta8', '0.1.2~beta8', '0.1.2_beta8', '0.1.2beta8', '0.1.2.beta8'):
            self.assertEqual(updates.version_key(version), updates.version_key('0.1.2-beta8'))
        sequence = ['0.1.2-alpha1', '0.1.2-beta8', '0.1.2-beta10', '0.1.2-rc1', '0.1.2', '0.1.3-alpha1']
        self.assertEqual(sequence, sorted(sequence, key=updates.version_key))
        self.assertIsNone(updates.version_key('development'))

    def test_choose_newest_version_not_api_order(self):
        releases = [release('v0.1.2-beta9', 'eleven-rack-driver_0.1.2~beta9_all.deb'),
                    release('v0.1.2-beta10', 'eleven-rack-driver_0.1.2~beta10_all.deb')]
        result = self.select(releases)
        self.assertEqual(result['version'], '0.1.2-beta10')
        self.assertIn('sudo apt install', result['command'])
        self.assertTrue(result['url'].startswith(updates.RELEASES + '/tag/'))

    def test_published_debian_filename_format(self):
        result = self.select([release('v0.1.2-beta9', 'eleven-rack-driver_0.1.2.beta9_all.deb')])
        self.assertEqual(result['status'], 'available')

    def test_stable_users_do_not_receive_beta(self):
        self.assertEqual(self.select([release('v0.1.3-beta1', 'eleven-rack-driver_0.1.3~beta1_all.deb', prerelease=True)], installed='0.1.2')['status'], 'current')

    def test_drafts_missing_assets_and_wrong_package_version(self):
        for candidate in (release('v0.1.3', 'eleven-rack-driver_0.1.3_all.deb', draft=True),
                          release('v0.1.3'), release('v0.1.3', 'eleven-rack-driver_0.1.2_all.deb')):
            self.assertEqual(self.select([candidate])['status'], 'current')

    def test_distro_arch_and_component_filter(self):
        assets = ('eleven-rack-driver-0.1.3-1.fc44.x86_64.rpm',
                  'eleven-rack-driver-0.1.3-1.fc43.x86_64.rpm',
                  'eleven-rack-driver-0.1.3-1.el10.x86_64.rpm',
                  'eleven-rack-editor-linux-0.1.3-1.fc44.x86_64.rpm',
                  'eleven-rack-driver-0.1.3-1-x86_64.pkg.tar.zst')
        releases = [release('v0.1.3', *assets)]
        for distro, version, suffix in (('fedora', '44', '.fc44.x86_64.rpm'),
                                       ('centos', '10', '.el10.x86_64.rpm'),
                                       ('arch', '', '.pkg.tar.zst')):
            result = self.select(releases, distro=distro, version=version)
            self.assertEqual(result['status'], 'available')
            self.assertTrue(result['package'].endswith(suffix))
        self.assertTrue(self.select(releases, component='editor', distro='fedora', version='44')['package'].startswith('eleven-rack-editor-linux-'))
        self.assertEqual(self.select(releases, distro='fedora', version='45')['status'], 'current')
        self.assertEqual(self.select(releases, arch='aarch64')['status'], 'unsupported')

    def test_ambiguous_and_unsafe_assets_not_offered(self):
        candidates = [release('v0.1.3', 'eleven-rack-driver_0.1.3_all.deb', 'eleven-rack-driver_0.1.3_amd64.deb'),
                      release('v0.1.3', 'eleven-rack-driver_0.1.3_$(echo hacked)_all.deb')]
        for item in candidates:
            self.assertEqual(self.select([item])['status'], 'current')

    def test_offline_and_cache_identity(self):
        target = {'distro': 'ubuntu', 'release': '24.04', 'arch': 'x86_64'}
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'XDG_CACHE_HOME': folder}), patch.object(updates, 'host_target', return_value=target), patch.object(updates.urllib.request, 'urlopen', side_effect=OSError('offline')) as request:
            cache = Path(folder) / 'eleven-rack/updates-driver.json'
            cache.parent.mkdir()
            cache.write_text(json.dumps({'identity': {'installed': '0.1.2', 'target': target}, 'time': updates.time.time(), 'result': {'status': 'current'}}))
            self.assertEqual(updates.check_updates('0.1.2', 'driver')['status'], 'current')
            request.assert_not_called()
            self.assertEqual(updates.check_updates('0.1.2', 'driver', force=True)['status'], 'offline')
            self.assertEqual(updates.check_updates('0.1.3', 'driver')['status'], 'offline')


if __name__ == '__main__':
    unittest.main()

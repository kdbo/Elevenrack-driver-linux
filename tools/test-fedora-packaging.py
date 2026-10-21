#!/usr/bin/env python3
"""Check Fedora source guards and scriptlets without touching audio or DKMS."""
import importlib.util
import io
import os
from pathlib import Path
import struct
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fedora', ROOT/'tools/build-fedora-package-set.py')
fedora = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fedora)
spec = importlib.util.spec_from_file_location('fetch', ROOT/'packaging/fetch-fedora-kernel-source.py')
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)


def cpio(members):
    """A newc cpio archive of (name, bytes) members, as rpm2cpio prints it."""
    out = b''
    for name, data in members + [('TRAILER!!!', b'')]:
        encoded = name.encode() + b'\0'
        fields = [0, 0o100644, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(encoded), 0]
        out += b'070701' + b''.join(b'%08x' % f for f in fields) + encoded
        out += b'\0' * ((4 - len(out) % 4) % 4) + data + b'\0' * ((4 - len(data) % 4) % 4)
    return out


def kernel_tarball(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:xz') as archive:
        for name, text in files.items():
            info = tarfile.TarInfo('linux-7.2.9/'+name)
            info.size = len(text.encode())
            archive.addfile(info, io.BytesIO(text.encode()))
    return buffer.getvalue()


def fake_commands(directory, scripts):
    directory.mkdir(parents=True, exist_ok=True)
    for name, body in scripts.items():
        path = directory/name
        path.write_text('#!/bin/sh\n'+body+'\n')
        path.chmod(0o755)
    return {**os.environ, 'PATH': f'{directory}:{os.environ["PATH"]}'}


class FedoraPackaging(unittest.TestCase):
    def test_installed_kernel_requires_matching_headers_and_runtime_modules(self):
        targets = [{'kernel_devel_version': '7.2.9-101.fc43'},
                   {'kernel_devel_version': '6.19.10-300.fc44'}]
        dependencies = fedora.driver_dependencies('1.4.11-1.fc43', targets)
        for target in targets:
            version = target['kernel_devel_version']
            for package in ('kernel-devel', 'kernel-modules-core', 'kernel-modules',
                            'kernel-modules-extra'):
                self.assertIn(f'({package} = {version} if kernel-core = {version})', dependencies)
                self.assertNotIn(f'{package} = {version}', dependencies)

    def test_bundled_rtmidi_uses_host_python_abi(self):
        import sys
        dependencies = fedora.editor_dependencies()
        self.assertNotIn('python3-rtmidi', dependencies)
        self.assertIn(f'python(abi) = {sys.version_info.major}.{sys.version_info.minor}', dependencies)

    def test_editor_requires_bundled_rtmidi(self):
        with tempfile.TemporaryDirectory() as temporary:
            editor = Path(temporary)/'editor'
            for name in ('eleven-rack-editor-linux', 'resources/app.asar',
                         'resources/eleven-rack-updates.py', 'resources/bridge-linux/bridge.py'):
                fedora.write(editor, name, 'test')
            with self.assertRaisesRegex(RuntimeError, 'rtmidi/__init__.py'):
                fedora.editor_payload(Path(temporary)/'stage', editor)

    def test_config_preservation_and_kernel_pin(self):
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary)
            fedora.write(stage, 'etc/wireplumber/test.conf', 'test')
            fedora.write(stage, 'usr/bin/test', 'test')
            text = fedora.spec('eleven-rack-driver', '0.1.2~beta8', stage,
                               ['kernel-devel = 7.0.1-1.fc44'])
            self.assertIn('%config(noreplace) /etc/wireplumber/test.conf', text)
            self.assertIn('Requires: kernel-devel = 7.0.1-1.fc44', text)
            self.assertIn('/usr/bin/test', text)

    def test_editor_rejects_incomplete_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(RuntimeError, 'Missing built Editor'):
                fedora.editor_payload(Path(temporary)/'stage', Path(temporary))

    def test_additional_kernel_selects_its_own_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            script = root/'build-driver.sh'
            script.write_text((ROOT/'packaging/fedora/build-driver.sh').read_text())
            (root/'prepared-kernel').mkdir()
            (root/'prepared-kernel/kernel-release').write_text('7.2.9-201.fc44.x86_64\n')
            old = root/'prepared-kernels/6.19.10-300.fc44.x86_64'
            old.mkdir(parents=True)
            (old/'kernel-release').write_text('6.19.10-300.fc44.x86_64\n')
            (root/'build-driver-common.sh').write_text('#!/bin/bash\nprintf "%s\\n" "$1" "$2" "$3"\n')
            result = subprocess.run(['bash', str(script), '6.19.10-300.fc44.x86_64', '/test/headers'], capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout.splitlines(), ['6.19.10-300.fc44.x86_64', '/test/headers', str(old/'sound/usb')])


    def test_unbundled_kernel_fetches_its_own_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            script = root/'build-driver.sh'
            script.write_text((ROOT/'packaging/fedora/build-driver.sh').read_text())
            (root/'prepared-kernel').mkdir()
            (root/'prepared-kernel/kernel-release').write_text('7.2.11-200.fc44.x86_64\n')
            (root/'fetch-fedora-kernel-source.py').write_text('import sys\nprint("/cache/" + sys.argv[1] + "/sound/usb")\n')
            (root/'build-driver-common.sh').write_text('#!/bin/bash\nprintf "%s\\n" "$1" "$2" "$3"\n')
            result = subprocess.run(['bash', str(script), '7.2.9-201.fc44.x86_64', '/test/headers'],
                                    capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout.splitlines(),
                             ['7.2.9-201.fc44.x86_64', '/test/headers', '/cache/7.2.9-201.fc44.x86_64/sound/usb'])

    def test_failed_source_fetch_stops_the_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            script = root/'build-driver.sh'
            script.write_text((ROOT/'packaging/fedora/build-driver.sh').read_text())
            (root/'fetch-fedora-kernel-source.py').write_text('raise SystemExit(1)\n')
            (root/'build-driver-common.sh').write_text('#!/bin/bash\necho built\n')
            result = subprocess.run(['bash', str(script), '7.2.9-201.fc44.x86_64'], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('built', result.stdout)

    def test_payload_does_not_pin_dkms_to_bundled_kernels(self):
        text = (ROOT/'tools/build-fedora-package-set.py').read_text()
        self.assertNotIn("'|'.join(re.escape(k) for k in kernels)", text)
        self.assertIn("'fetch-fedora-kernel-source.py'", text)

    def run_post(self, running, kernels, dkms_entries=(), check=None):
        """Run %post against fake kernels: {release: 'devel' | 'core' | 'fails'}."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for kernel, state in kernels.items():
                (root/'modules'/kernel).mkdir(parents=True)
                if state != 'core':
                    (root/'src'/kernel).mkdir(parents=True)
                    (root/'src'/kernel/'Makefile').write_text('')
            failing = ' '.join(k for k, state in kernels.items() if state == 'fails')
            env = fake_commands(root/'bin', {
                'uname': f'echo {running}',
                'rpm': 'case "$2" in ' + ''.join(f'kernel-core-{k}) exit 0 ;; ' for k in kernels) + '*) exit 1 ;; esac',
                'dkms': f'echo "dkms $*" >> {root}/dkms.log; '
                        f'for k in {failing}; do [ "$1" = build ] && [ "$7" = "$k" ] && exit 1; done; exit 0',
                'depmod': 'exit 0', 'dracut': 'exit 0',
                'modinfo': 'echo /lib/modules/$2/extra/snd-usb-audio.ko.xz'})
            body = fedora.driver_scripts('0.1.2~beta16').split('\n%preun')[0].split('\n', 1)[1]
            (root/'dkms').mkdir()
            for old in dkms_entries:
                (root/'dkms'/old).mkdir()
            # DKMS links each kernel to the version built for it; this one dangles afterwards.
            (root/'dkms/kernel-7.2.9-201.fc44.x86_64-x86_64').symlink_to(root/'dkms/0.1.2~beta8')
            (root/'usr-src/eleven-rack-0.1.2~beta15').mkdir(parents=True)
            (root/'usr-src/eleven-rack-0.1.2~beta15/dkms.conf').write_text('')
            body = body.replace('/var/lib/dkms/eleven-rack', str(root/'dkms'))
            body = body.replace('/usr/src/eleven-rack-', str(root/'usr-src/eleven-rack-'))
            body = body.replace('/usr/src/kernels', str(root/'src'))
            body = body.replace('/lib/modules 2>', str(root/'modules')+' 2>')
            result = subprocess.run(['sh', '-c', body], capture_output=True, text=True, env=env)
            if check:
                check(root)
            return result

    def test_post_builds_every_installed_kernel_with_headers(self):
        result = self.run_post('7.2.9-201.fc44.x86_64', {'7.2.9-201.fc44.x86_64': 'devel',
                                                         '7.2.11-200.fc44.x86_64': 'devel',
                                                         '6.19.10-300.fc44.x86_64': 'core'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('  7.2.9-201.fc44.x86_64: ready', result.stdout)
        self.assertIn('  7.2.11-200.fc44.x86_64: ready', result.stdout)
        self.assertIn('  6.19.10-300.fc44.x86_64: NOT built, kernel-devel is missing '
                      '(sudo dnf install kernel-devel-6.19.10-300.fc44.x86_64)', result.stdout)
        self.assertIn('Reboot to activate', result.stdout)
        self.assertNotIn('WARNING', result.stderr)

    def test_post_removes_dkms_entries_of_older_versions(self):
        def check(root):
            self.assertEqual(sorted(p.name for p in (root/'dkms').iterdir()), ['0.1.2~beta16'])
            log = (root/'dkms.log').read_text()
            self.assertIn('dkms remove -m eleven-rack -v 0.1.2~beta15 --all', log)
            self.assertNotIn('-v 0.1.2~beta8 --all', log)
        result = self.run_post('7.2.9-201.fc44.x86_64', {'7.2.9-201.fc44.x86_64': 'devel'},
                               ['0.1.2~beta8', '0.1.2~beta15', '0.1.2~beta16'], check)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('removing the DKMS entry of version 0.1.2~beta8', result.stdout)
        self.assertIn('removing the DKMS entry of version 0.1.2~beta15', result.stdout)
        self.assertNotIn('version 0.1.2~beta16', result.stdout)

    def test_post_warns_when_the_running_kernel_has_no_driver(self):
        result = self.run_post('7.2.9-201.fc44.x86_64', {'7.2.9-201.fc44.x86_64': 'fails',
                                                         '7.2.11-200.fc44.x86_64': 'devel'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('  7.2.9-201.fc44.x86_64: NOT built, the build failed', result.stdout)
        self.assertIn('  7.2.11-200.fc44.x86_64: ready', result.stdout)
        self.assertIn('WARNING: the Eleven Rack driver is not built for the running kernel 7.2.9-201.fc44.x86_64',
                      result.stderr)
        self.assertNotIn('Reboot to activate', result.stdout)

    def test_post_warns_without_running_kernel_headers(self):
        result = self.run_post('7.2.9-201.fc44.x86_64', {'7.2.9-201.fc44.x86_64': 'core'})
        self.assertIn('kernel-devel is missing', result.stdout)
        self.assertIn('WARNING', result.stderr)

    def test_scriptlet_sections_are_valid_shell(self):
        text = fedora.driver_scripts('0.1.2~beta16')
        for action in ('build', 'install'):
            self.assertIn(f'dkms {action} -m eleven-rack -v 0.1.2~beta16 -k "$kernel" '
                          '--kernelsourcedir "/usr/src/kernels/$kernel"', text)
        for section in text.split('\n%'):
            subprocess.run(['sh', '-n'], input=section.split('\n', 1)[1], text=True, check=True)


class FedoraKernelSource(unittest.TestCase):
    SPEC = """%prep
ApplyOptionalPatch()
{
  ApplyPatch $patch ${1+"$@"}
}
ApplyOptionalPatch patch-%{patchversion}-redhat.patch
ApplyOptionalPatch linux-kernel-test.patch
"""

    def test_spec_patches_resolve_macros_in_order(self):
        names = ['linux-kernel-test.patch', 'patch-7.2-redhat.patch', 'unused.patch']
        self.assertEqual(fetch.applied_patches(self.SPEC, names), ['patch-7.2-redhat.patch', 'linux-kernel-test.patch'])

    def test_only_sound_usb_sections_are_applied(self):
        patch = ('diff --git a/sound/soc/x.c b/sound/soc/x.c\n--- a/sound/soc/x.c\n'
                 'diff --git a/sound/usb/card.c b/sound/usb/card.c\n--- a/sound/usb/card.c\n')
        self.assertEqual(fetch.usb_sections(patch), 'diff --git a/sound/usb/card.c b/sound/usb/card.c\n--- a/sound/usb/card.c\n')

    def test_unpack_extracts_and_patches_sound_usb(self):
        patch = """diff --git a/sound/usb/card.c b/sound/usb/card.c
--- a/sound/usb/card.c
+++ b/sound/usb/card.c
@@ -1 +1 @@
-upstream
+fedora
"""
        tarball = kernel_tarball({'Makefile': 'top', 'sound/usb/Makefile': 'obj', 'sound/usb/card.c': 'upstream\n',
                                  'sound/core/pcm.c': 'other'})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'payload.cpio').write_bytes(cpio([('kernel.spec', self.SPEC.encode()),
                                                    ('linux-7.2.9.tar.xz', tarball),
                                                    ('linux-kernel-test.patch', b''),
                                                    ('patch-7.2-redhat.patch', patch.encode())]))
            env = fake_commands(root/'bin', {'rpm2cpio': f'cat {root}/payload.cpio'})
            old = os.environ['PATH']
            os.environ['PATH'] = env['PATH']
            try:
                patches = fetch.unpack(root/'kernel.src.rpm', root/'tree')
            finally:
                os.environ['PATH'] = old
            self.assertEqual(patches, ['patch-7.2-redhat.patch', 'linux-kernel-test.patch'])
            self.assertEqual((root/'tree/sound/usb/card.c').read_text(), 'fedora\n')
            self.assertFalse((root/'tree/sound/core').exists())
            self.assertFalse((root/'tree/Makefile').exists())

    def test_unsigned_source_rpm_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env = fake_commands(root/'bin', {'rpm': 'echo "kernel.src.rpm: digests OK"; exit 0'})
            old = os.environ['PATH']
            os.environ['PATH'] = env['PATH']
            try:
                with self.assertRaisesRegex(RuntimeError, 'no trusted signature'):
                    fetch.verify(root/'kernel.src.rpm', 'kernel-7.2.9-201.fc44.src.rpm')
            finally:
                os.environ['PATH'] = old

    def test_signature_header_replaces_the_unsigned_one(self):
        def header(entries, store):
            return b'\x8e\xad\xe8\x01\0\0\0\0' + struct.pack('>II', entries, len(store)) + b'E' * 16 * entries + store
        lead = b'\xed\xab\xee\xdb' + b'L' * 92
        unsigned = header(1, b'old')            # 35 bytes, padded to 40
        signed = header(2, b'signature!')       # 58 bytes, cached padded to 64
        rest = b'main header and payload'
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'unsigned.rpm').write_bytes(lead + unsigned + b'\0' * 5 + rest)
            (root/'header.sig').write_bytes(signed + b'\0' * 6)
            fetch.download((root/'unsigned.rpm').as_uri(), root/'signed.rpm', (root/'header.sig').as_uri())
            self.assertEqual((root/'signed.rpm').read_bytes(), lead + signed + b'\0' * 6 + rest)
            (root/'bad.sig').write_bytes(signed + b'junk')
            with self.assertRaisesRegex(RuntimeError, 'Malformed'):
                fetch.download((root/'unsigned.rpm').as_uri(), root/'bad.rpm', (root/'bad.sig').as_uri())

    def test_download_locations(self):
        self.assertEqual(fetch.candidates('kernel-6.12.0-277.el10.src.rpm'),
                         [('https://mirror.stream.centos.org/10-stream/BaseOS/source/tree/Packages/'
                           'kernel-6.12.0-277.el10.src.rpm', None)])
        with self.assertRaisesRegex(RuntimeError, 'Unsupported'):
            fetch.candidates('kernel-7.2.9-1.mga10.src.rpm')


if __name__ == '__main__':
    unittest.main()

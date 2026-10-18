#!/usr/bin/env python3
"""Check Arch kernel-source fetching for DKMS without network, root or an Arch host."""
import hashlib
import importlib.util
import io
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('fetch', ROOT / 'packaging/fetch-arch-kernel-source.py')
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)

TARBALL = 'https://cdn.kernel.org/pub/linux/kernel/v7.x/linux-7.2.11.tar.xz'
PATCH = 'https://github.com/archlinux/linux/releases/download/v7.2.11-arch1/linux-v7.2.11-arch1.patch.zst'
ARCH_PATCH = '''From 1 Mon Sep 17 00:00:00 2001
Subject: [PATCH] Arch changes

diff --git a/sound/usb/card.c b/sound/usb/card.c
--- a/sound/usb/card.c
+++ b/sound/usb/card.c
@@ -1 +1 @@
-int card;
+int card_patched;
diff --git a/init/Kconfig b/init/Kconfig
--- a/init/Kconfig
+++ b/init/Kconfig
@@ -1 +1 @@
-config A
+config B
'''


def tar_xz(files):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode='w:xz') as archive:
        for name, text in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(text)
            archive.addfile(info, io.BytesIO(text))
    return data.getvalue()


def recipe(tarball_sum, patch_sum, version=('7.2.11.arch1', '1')):
    return f'''pkgbase = linux
\tpkgver = {version[0]}
\tpkgrel = {version[1]}
\tsource = {TARBALL}
\tsource = https://cdn.kernel.org/pub/linux/kernel/v7.x/linux-7.2.11.tar.sign
\tsource = {PATCH}
\tsource = {PATCH}.sig
\tsource_x86_64 = config.x86_64
\tsha256sums = {tarball_sum}
\tsha256sums = SKIP
\tsha256sums = {patch_sum}
\tsha256sums = SKIP
\tsha256sums_x86_64 = {'0' * 64}

pkgname = linux
\tpkgdesc = The Linux kernel and modules
'''


class FetchArchKernelSource(unittest.TestCase):
    def setUp(self):
        self.tarball = tar_xz({'linux-7.2.11/sound/usb/Makefile': b'obj-m += x.o\n',
                               'linux-7.2.11/sound/usb/card.c': b'int card;\n',
                               'linux-7.2.11/init/Kconfig': b'config A\n'})
        self.patch = subprocess.run(['zstd', '-q', '-c'], input=ARCH_PATCH.encode(),
                                    capture_output=True, check=True).stdout
        self.recipe = recipe(hashlib.sha256(self.tarball).hexdigest(), hashlib.sha256(self.patch).hexdigest())
        self.requests = []

    def urlopen(self, url, timeout=None):
        self.requests.append(url)
        body = {TARBALL: self.tarball, PATCH: self.patch}.get(url)
        if url.endswith('/7.2.11.arch1-1/.SRCINFO'):
            body = self.recipe.encode()
        if body is None:
            raise AssertionError('Unexpected download ' + url)
        return io.BytesIO(body)

    def prepare(self, cache):
        owner = '/usr/lib/modules/7.2.11-arch1-1/build/Makefile is owned by linux-headers 7.2.11.arch1-1\n'
        real = subprocess.check_output
        def check_output(args, **kwargs):
            return owner if args[0] == 'pacman' else real(args, **kwargs)
        with patch.object(fetch.urllib.request, 'urlopen', side_effect=self.urlopen), \
             patch.object(fetch.subprocess, 'check_output', side_effect=check_output):
            return fetch.prepare('7.2.11-arch1-1', cache)

    def test_only_sound_usb_is_kept_with_the_arch_patch_applied_and_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            usb = self.prepare(Path(directory))
            self.assertEqual('int card_patched;\n', (usb / 'card.c').read_text())
            self.assertTrue((usb / 'Makefile').is_file())
            self.assertFalse((usb.parent.parent / 'init').exists())
            # A rebuild of the same kernel needs no network.
            self.requests.clear()
            self.assertEqual(usb, self.prepare(Path(directory)))
            self.assertEqual([], self.requests)

    def test_checksum_mismatch_is_refused(self):
        self.tarball += b'tampered'
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, 'Checksum'):
                self.prepare(Path(directory))
            self.assertEqual([], list(Path(directory).iterdir()), 'no partial cache after a refusal')

    def test_unverified_or_mismatched_recipes_are_refused(self):
        parsed = fetch.parse_recipe(recipe('SKIP', 'a' * 64))
        with self.assertRaisesRegex(RuntimeError, 'unverified'):
            fetch.sources(parsed, '7.2.11.arch1-1')
        parsed = fetch.parse_recipe(recipe('a' * 64, 'b' * 64))
        with self.assertRaisesRegex(RuntimeError, 'installed kernel version'):
            fetch.sources(parsed, '7.2.12.arch1-1')
        tarball, patches = fetch.sources(parsed, '7.2.11.arch1-1')
        self.assertEqual((TARBALL, 'sha256', 'a' * 64), tarball)
        self.assertEqual([(PATCH, 'sha256', 'b' * 64)], patches)

    def test_only_sound_usb_sections_of_a_patch_are_applied(self):
        self.assertEqual(['sound/usb/card.c'],
                         [line.split()[2][2:] for line in fetch.usb_sections(ARCH_PATCH).splitlines()
                          if line.startswith('diff --git')])
        self.assertEqual('', fetch.usb_sections('diff --git a/sound/usbx/a b/sound/usbx/a\n'))


if __name__ == '__main__':
    unittest.main()

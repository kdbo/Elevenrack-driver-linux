#!/usr/bin/env python3
"""Check SPA plugin directory detection against fake multiarch file trees."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build', ROOT/'tools/build-latency-backend.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class PluginDirectory(unittest.TestCase):
    def detect(self, plugins, triplet='x86_64-linux-gnu'):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for directory in plugins:
                plugin = root/directory/'alsa/libspa-alsa.so'
                plugin.parent.mkdir(parents=True)
                plugin.write_bytes(b'')
            # No pkg-config metadata, as on runtime-only installations.
            with patch.object(build, 'run', side_effect=OSError):
                found = build.plugin_directory(root, multiarch=lambda: triplet)
            return str(found.relative_to(root.resolve()))

    def test_single_multiarch_plugin(self):
        self.assertEqual(self.detect(['usr/lib/x86_64-linux-gnu/spa-0.2']), 'usr/lib/x86_64-linux-gnu/spa-0.2')

    def test_native_plugin_wins_over_foreign_i386_plugin(self):
        # Ubuntu Studio with 32-bit PipeWire modules for Wine or Steam.
        plugins = ['usr/lib/x86_64-linux-gnu/spa-0.2', 'usr/lib/i386-linux-gnu/spa-0.2']
        self.assertEqual(self.detect(plugins), 'usr/lib/x86_64-linux-gnu/spa-0.2')

    def test_non_multiarch_layouts(self):
        self.assertEqual(self.detect(['usr/lib64/spa-0.2']), 'usr/lib64/spa-0.2')
        self.assertEqual(self.detect(['usr/lib/spa-0.2']), 'usr/lib/spa-0.2')

    def test_ambiguous_or_missing_plugin_names_the_candidates(self):
        plugins = ['usr/lib/x86_64-linux-gnu/spa-0.2', 'usr/lib/i386-linux-gnu/spa-0.2']
        with self.assertRaisesRegex(RuntimeError, 'i386-linux-gnu.*x86_64-linux-gnu|found: .*i386'):
            self.detect(plugins, triplet=None)
        with self.assertRaisesRegex(RuntimeError, 'found: none'):
            self.detect([])


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
"""Check task admission/results without touching audio or the real queue."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('nightly', Path(__file__).with_name('run-nightly-regression.py'))
nightly = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nightly)


class NightlyRunner(unittest.TestCase):
    def run_queue(self, root, complete, queue=((48000,128,30,'white'),)):
        commands = []
        def child(argv, **kwargs):
            commands.append(argv)
            if complete:
                matrix = Path(argv[argv.index('--output')+1])/'cycle-1-white'
                matrix.mkdir(parents=True)
                (matrix/'matrix.json').write_text(json.dumps({
                    'restored': True, 'results': [{'valid': False, 'platform': {'classification': 'smi_correlated'},
                                                   'transport': {'classification': 'xhci'}}],
                    'driver_srcversion': 'test-driver-identity'}))
            return SimpleNamespace(returncode=0 if complete else 1, poll=lambda: 0 if complete else 1)
        with patch.object(nightly, 'ROOT', root), \
             patch.object(nightly.sys, 'argv', ['nightly', '--start-now']), \
             patch.object(nightly, 'tasks', return_value=list(queue)), \
             patch.object(nightly.fcntl, 'flock'), \
             patch.object(nightly.signal, 'signal'), \
             patch.object(nightly.shutil, 'disk_usage', return_value=SimpleNamespace(free=10*1024**3)), \
             patch.object(nightly.subprocess, 'run', return_value=SimpleNamespace(returncode=1)), \
             patch.object(nightly.subprocess, 'Popen', side_effect=child):
            nightly.main()
        return commands, json.loads((root/'build/latency/nightly-regression/queue.json').read_text())

    def test_white_noise_uses_analog_analysis_and_keeps_driver_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            commands, state = self.run_queue(Path(tmp), True)
            self.assertIn('--analog-white-noise', commands[0])
            self.assertEqual(state['next_task'], 1)
            self.assertEqual(state['results'][0]['driver_srcversion'], 'test-driver-identity')
            self.assertTrue(state['results'][0]['restored'])
            self.assertEqual(state['results'][0]['platform'], 'smi_correlated')
            self.assertIn('--transport-trace', commands[0])
            self.assertIn('--usb-flight', commands[0])
            self.assertEqual(state['results'][0]['transport'], 'xhci')

    def test_platform_calibration_runs_once_per_night(self):
        with tempfile.TemporaryDirectory() as tmp:
            commands, state = self.run_queue(Path(tmp), True, [(48000,128,1,'sine'), (48000,128,1,'pink')])
            self.assertEqual(state['next_task'], 2)
            self.assertIn('--platform-calibration', commands[0])
            self.assertNotIn('--platform-calibration', commands[1])

    def test_no_matrix_leaves_task_pending_and_preserves_failed_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, state = self.run_queue(Path(tmp), False)
            self.assertEqual(state['next_task'], 0)
            self.assertFalse(state['results'][0]['complete'])
            self.assertIsNone(state['results'][0]['driver_srcversion'])
            self.assertIsNone(state['results'][0]['platform'])


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
"""Synthetic SMI attribution checks; no audio device, root or cap_perfmon required."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('platform_noise', ROOT/'tools/platform_noise.py')
platform = importlib.util.module_from_spec(spec)
spec.loader.exec_module(platform)
RATE, QUANTUM, T0 = 48000, 128, 1_700_000_000_000_000_000
PERIOD = QUANTUM*1_000_000_000//RATE


class Attribution(unittest.TestCase):
    def recording(self, directory, stall_at=None, stall_ns=0, smi_at=None, seconds=3):
        """Callback stamps with an optional stall; SMI samples every 10 ms."""
        raw = Path(directory)/'quantum-128-run-1.raw'
        lines, t = ['frame,frames,realtime_ns,monotonic_raw_ns'], T0
        for i in range(seconds*RATE//QUANTUM):
            if stall_at is not None and i == stall_at*RATE//QUANTUM:
                t += stall_ns
            lines.append(f'{i*QUANTUM},{QUANTUM},{t},{t}')
            t += PERIOD
        Path(str(raw)+'.timestamps.csv').write_text('\n'.join(lines)+'\n')
        smi, count = ['realtime_ns,monotonic_ns,smi_count,late_ns'], 7
        for ms in range(0, seconds*1000+10, 10):
            when = T0 + ms*1_000_000
            late = 0
            if smi_at is not None and ms == int(smi_at*1000)+10:
                count += 1
                late = stall_ns
            smi.append(f'{when},{when},{count},{late}')
        (Path(directory)/'smi.csv').write_text('\n'.join(smi)+'\n')
        return raw

    def classify(self, faults=(), **recording):
        with tempfile.TemporaryDirectory() as directory:
            raw = self.recording(directory, **recording)
            return platform.attribute(raw, RATE, QUANTUM, list(faults), 'available',
                                      platform.smi_events(Path(directory)/'smi.csv'))

    def test_clean_run(self):
        self.assertEqual(self.classify()['classification'], 'clean')

    def test_stall_during_smi(self):
        result = self.classify(stall_at=1.5, stall_ns=22_000_000, smi_at=1.5)
        self.assertEqual(result['classification'], 'smi_correlated')
        self.assertEqual(result['smi_count_during_recording'], 1)
        self.assertEqual(len(result['callback_stalls']), 1)
        self.assertAlmostEqual(result['max_callback_stall_ns'], 22_000_000, delta=PERIOD)

    def test_stall_without_smi(self):
        result = self.classify(stall_at=1.5, stall_ns=22_000_000)
        self.assertEqual(result['classification'], 'not_smi')

    def test_smi_far_from_stall_is_not_matched(self):
        result = self.classify(stall_at=1.0, stall_ns=22_000_000, smi_at=2.5)
        self.assertEqual(result['classification'], 'not_smi')

    def test_fault_window_reaches_back_one_round_trip(self):
        # Fault seen 60 ms after the SMI: within the 100 ms window plus round-trip lead.
        result = self.classify(faults=[{'seconds': 1.56}], smi_at=1.5)
        self.assertEqual(result['classification'], 'smi_correlated')
        self.assertEqual(self.classify(faults=[{'seconds': 2.5}], smi_at=1.5)['classification'], 'not_smi')

    def test_mixed_evidence(self):
        result = self.classify(faults=[{'seconds': 2.5}], stall_at=1.5, stall_ns=22_000_000, smi_at=1.5)
        self.assertEqual(result['classification'], 'partly_smi')

    def test_small_jitter_is_not_a_stall(self):
        self.assertEqual(self.classify(stall_at=1.0, stall_ns=3_000_000)['callback_stalls'], [])

    def test_unavailable_counter_does_not_guess(self):
        result = platform.attribute(None, RATE, QUANTUM, [{'seconds': 1}], 'helper not installed', [])
        self.assertEqual(result['classification'], 'unavailable')

    def test_calibration_parsing(self):
        text = ('realtime_ns,gap_ns,smi_delta,context_switches\n'
                '1,24000000,1,0\n2,3000000,0,1\n3,400000,0,0\n'
                '# duration_ns=30000000000 max_gap_ns=24000000 smi_total=4\n')
        result = platform.parse_calibration(text, 100)
        self.assertEqual((result['smi_total'], result['stolen_gaps']), (4, 2))
        self.assertEqual((result['max_stolen_gap_ns'], result['max_smi_gap_ns']), (24000000, 24000000))
        gaps_only = platform.parse_calibration(text.replace(',1,0\n', ',,0\n', 1).rsplit('#', 1)[0]
                                               + '# duration_ns=1 max_gap_ns=1 smi_total=\n', 100, 'denied')
        self.assertIsNone(gaps_only['smi_total'])


class Helper(unittest.TestCase):
    def test_helper_builds_and_spins(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory)/'smi-counter'
            subprocess.run(['cc', '-O2', '-Wall', '-Wextra', '-Werror', str(ROOT/'tools/smi-counter.c'),
                            '-o', str(binary)], check=True)
            result = platform.calibrate(1, 1000, helper=binary)
            self.assertGreater(result['duration_ns'], 900_000_000)
            json.dumps(result)
            monitor = platform.SmiMonitor(Path(directory)/'smi.csv', helper=binary)
            with monitor:
                pass
            self.assertTrue(monitor.status == 'available' or monitor.status.startswith('unavailable'))


if __name__ == '__main__':
    unittest.main()

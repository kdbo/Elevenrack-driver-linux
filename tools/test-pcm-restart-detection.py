#!/usr/bin/env python3
"""Check startup handling without opening audio devices."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    'matrix', Path(__file__).with_name('test-full-latency-matrix.py'))
matrix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(matrix)


def snapshot(playback, capture):
    return {
        'p_status': f'trigger_time: {playback}\n' if playback is not None else 'closed\n',
        'c_status': f'trigger_time: {capture}\n' if capture is not None else 'closed\n',
    }


class RestartDetection(unittest.TestCase):
    def test_initial_start_is_not_restart(self):
        self.assertFalse(matrix.pcm_restarted([
            snapshot(None, None), snapshot('0.000000000', '0'),
            snapshot('123.000000001', '122.999999999'),
            snapshot('123.000000001', '122.999999999')]))

    def test_restart_in_either_direction(self):
        for direction in ('p', 'c'):
            with self.subTest(direction=direction):
                changed = snapshot('123.000000001', '123.000000001')
                changed[direction+'_status'] = 'trigger_time: 123.000000002\n'
                self.assertTrue(matrix.pcm_restarted([
                    snapshot('0.000000000', '0.000000000'),
                    snapshot('123.000000001', '123.000000001'), changed]))

    def test_closed_or_unset_only_is_not_restart(self):
        self.assertFalse(matrix.pcm_restarted([
            snapshot(None, None), snapshot('0.000000000', '0.000000000')]))

    def test_unset_timestamp_does_not_hide_real_restart(self):
        self.assertTrue(matrix.pcm_restarted([
            snapshot('123.000000001', '123.000000001'),
            snapshot('0.000000000', None),
            snapshot('124.000000001', '123.000000001')]))


if __name__ == '__main__':
    unittest.main()

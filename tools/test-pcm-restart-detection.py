#!/usr/bin/env python3
"""Check startup handling without opening audio devices."""
import importlib.util
from pathlib import Path
import unittest
import tempfile

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
    def test_only_recording_changes_count(self):
        def timed(t, trigger):
            return dict(snapshot(trigger, trigger), realtime_ns=t)
        warmup = [timed(1, '10.0'), timed(2, '11.0')]
        self.assertFalse(matrix.pcm_restarted(
            warmup + [timed(3, '11.0'), timed(5, '12.0')], (3, 5)))
        # Preserve the pre-recording baseline to catch an immediate restart.
        self.assertTrue(matrix.pcm_restarted(
            warmup + [timed(3, '12.0')], (3, 5)))
        self.assertTrue(matrix.pcm_restarted(
            warmup + [timed(3, '11.0'), timed(4, '12.0')], (3, 5)))

    def test_bounds_follow_actual_callbacks_and_partial_final_block(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory)/'recording.raw'
            raw.write_bytes(bytes(6*4))
            Path(str(raw)+'.timestamps.csv').write_text(
                'frame,frames,realtime_ns,monotonic_raw_ns\n'
                '0,4,1000000000,1\n4,4,2000000000,2\n')
            self.assertEqual(matrix.recording_bounds(raw, 4),
                             (1000000000, 2500000000))
            Path(str(raw)+'.timestamps.csv').write_text('frame,frames,realtime_ns\n')
            with self.assertRaisesRegex(ValueError, 'Missing recording start'):
                matrix.recording_bounds(raw, 4)

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

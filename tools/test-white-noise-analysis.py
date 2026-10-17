#!/usr/bin/env python3
"""Offline tests: analog filtering must not conceal real discontinuities."""
import array
import importlib.util
import json
from pathlib import Path
import random
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('white', ROOT/'tools/analyze-white-noise-path.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class WhiteNoiseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT/'build/latency').mkdir(parents=True, exist_ok=True)
        for source, output in [('latency-correlation.c', 'liblatency-correlation.so'),
                               ('loopback-filter.c', 'libloopback-filter.so')]:
            subprocess.run(['cc', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror',
                            str(ROOT/'tools'/source), '-o', str(ROOT/'build/latency'/output), '-lm'], check=True)

    def sample(self, fault=None):
        rate, lag = 48000, 500
        rng = random.Random(42)
        x = array.array('f', (rng.uniform(-.03, .03) for _ in range(rate*4)))
        filtered = array.array('f', (.5*x[i]+.5*x[i-1] for i in range(len(x))))
        y = array.array('f', [0]*lag)+filtered[:-lag]
        if fault == 'step':
            y[rate*3:] = filtered[rate*3-lag-69:len(x)-lag-69]
        elif fault == 'dropout':
            y[rate*3:rate*3+4800] = array.array('f', [0]*4800)
        elif fault == 'brief_dropout':
            start = round(2.05*rate)
            y[start:start+16] = array.array('f', [0]*16)
        elif fault == 'training':
            for i in range(rate, rate*2):
                y[i] = rng.uniform(-.03, .03)
        elif fault == 'clipping':
            y[rate*3:rate*3+100] = array.array('f', [1.1]*100)
        with tempfile.TemporaryDirectory(prefix='white-path-') as directory:
            raw = Path(directory)/'test.raw'
            raw.write_bytes(y.tobytes())
            Path(str(raw)+'.reference.raw').write_bytes(x.tobytes())
            raw.with_suffix('.log').write_text(f'settled rate={rate} quantum=128\nxruns={1 if fault=="xrun" else 0}\n')
            if fault == 'pcm':
                anchor = 1_000_000_000_000
                Path(str(raw)+'.timestamps.csv').write_text(
                    f'frame,frames,realtime_ns\n0,480,{anchor}\n'
                    f'{len(x)-480},480,{anchor+(len(x)-480)*1_000_000_000//rate}\n')
                raw.with_suffix('.status.json').write_text(json.dumps([
                    {'realtime_ns': anchor+rate*1_000_000_000//rate,
                     'p_status': 'trigger_time: 1.0\n', 'c_status': 'trigger_time: 1.0\n'},
                    {'realtime_ns': anchor+3_000_000_000,
                     'p_status': 'trigger_time: 3.0\n', 'c_status': 'trigger_time: 1.0\n'}]))
            return module.analyze(raw)

    def test_fixed_analog_filter_passes_without_lowering_raw_threshold(self):
        r = self.sample()
        self.assertFalse(r['raw_screening_passed'])
        self.assertTrue(r['analog_model_validated'])
        self.assertTrue(r['passed'])
        self.assertFalse(r['faults'])

    def test_69_sample_step_remains_a_fault(self):
        r = self.sample('step')
        self.assertFalse(r['passed'])
        self.assertTrue(any(abs(x['frames']) == 69 for x in r['delay_steps']))

    def test_dropout_remains_a_fault(self):
        self.assertFalse(self.sample('dropout')['passed'])

    def test_brief_dropout_between_sparse_windows_is_detected(self):
        r = self.sample('brief_dropout')
        self.assertTrue(r['analog_model_validated'])
        self.assertFalse(r['passed'])
        self.assertTrue(r['dense_faults'])

    def test_clipping_remains_a_fault(self):
        self.assertFalse(self.sample('clipping')['passed'])

    def test_pcm_restart_fails_even_when_waveform_is_clean(self):
        r = self.sample('pcm')
        self.assertTrue(r['analog_model_validated'])
        self.assertTrue(r['pcm_restart_during_recording'])
        self.assertFalse(r['passed'])

    def test_xrun_remains_a_fault(self):
        self.assertFalse(self.sample('xrun')['passed'])

    def test_bad_training_cannot_explain_unrelated_held_out_samples(self):
        r = self.sample('training')
        self.assertFalse(r['analog_model_validated'])
        self.assertFalse(r['passed'])


if __name__ == '__main__':
    unittest.main()

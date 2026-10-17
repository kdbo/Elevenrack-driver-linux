#!/usr/bin/env python3
"""Synthetic continuity checks; no audio device or loopback cable required."""
import array
import importlib.util
from pathlib import Path
import random
import math
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('regression',ROOT/'tools/analyze-loopback-regression.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class AnalysisTests(unittest.TestCase):
    def run_signal(self, fault=None, kind="white", lag=500, jump=100, drift=False):
        rate=48000
        rng=random.Random(123)
        reference=array.array('f',(rng.uniform(-.03,.03) for _ in range(rate*3)))
        if kind=='multitone':
            reference=array.array('f',(.03*sum(math.sin(2*math.pi*f*i/rate) for f in (431,997,1871,2973))/4 for i in range(rate*3)))
        if drift:
            # A slow component the AC-coupled analog input removes from the capture.
            slow=[.05*math.sin(2*math.pi*1.5*i/rate) for i in range(len(reference))]
            captured=array.array('f',[0]*lag)+array.array('f',reference[:-lag])
            reference=array.array('f',(v+d for v,d in zip(reference,slow)))
        else:
            captured=array.array('f',[0]*lag)+reference[:-lag]
        if fault=='silence': captured[rate*2:rate*2+rate//5]=array.array('f',[0]*(rate//5))
        if fault=='jump': captured[rate*2:]=array.array('f',reference[rate*2-lag-jump:len(reference)-lag-jump])
        with tempfile.TemporaryDirectory(prefix=kind+'-regression-') as directory:
            raw=Path(directory)/'test.raw'
            raw.write_bytes(captured.tobytes());Path(str(raw)+'.reference.raw').write_bytes(reference.tobytes())
            raw.with_suffix('.log').write_text(f'settled rate={rate} quantum=128\nxruns={1 if fault=="xrun" else 0}\n')
            return module.analyze(raw)
    def test_delayed_clean_noise(self):
        result=self.run_signal();self.assertTrue(result['passed']);self.assertEqual(result['windows'][0]['lag_frames'],500)
    def test_multitone_absolute_delay(self):
        for lag in (500,5000):
            result=self.run_signal(kind='multitone',lag=lag)
            self.assertTrue(result['passed'])
            self.assertEqual(result['windows'][0]['lag_frames'],lag)
    def test_multitone_delay_jump(self):
        self.assertFalse(self.run_signal('jump',kind='multitone')['passed'])
    def test_silence_fails(self): self.assertFalse(self.run_signal('silence')['passed'])
    def test_xrun_fails(self): self.assertFalse(self.run_signal('xrun')['passed'])
    def test_delay_jump_fails(self): self.assertFalse(self.run_signal('jump')['passed'])
    def test_pink_low_frequency_drift_removed_by_analog_input_passes(self):
        self.assertTrue(self.run_signal(kind='pink', drift=True)['passed'])
    def test_small_noise_delay_step_fails(self):
        result=self.run_signal('jump', kind='pink', jump=34)
        self.assertFalse(result['passed'])
        self.assertIn('delay_jump', {i for f in result['faults'] for i in f['issues']})
if __name__=='__main__': unittest.main()

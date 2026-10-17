#!/usr/bin/env python3
"""Check click-test project generation and offset measurement without REAPER or audio."""
import array
import importlib.util
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('click', ROOT/'tools/reaper-click-test.py')
click = importlib.util.module_from_spec(spec)
spec.loader.exec_module(click)


def write_recording(path, rate, seconds, offset, step_after=None, step=0):
    """24-bit mono recording: every click delayed by offset (and step from a given click)."""
    samples = [0.0]*(rate*seconds)
    burst = click.click_burst(rate)
    for index, start in enumerate(click.click_positions(rate, seconds)):
        delay = offset + (step if step_after is not None and index >= step_after else 0)
        for i, value in enumerate(burst):
            samples[start+delay+i] = value*.8
    data = b''.join(int(v*8388607).to_bytes(3, 'little', signed=True) for v in samples)
    header = struct.pack('<4sI4s4sIHHIIHH4sI', b'RIFF', 36+len(data), b'WAVE', b'fmt ', 16, 1, 1, rate,
                         rate*3, 3, 24, b'data', len(data))
    path.write_bytes(header+data)


class ClickTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        library = ROOT/'build/latency/liblatency-correlation.so'
        library.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['cc', '-shared', '-fPIC', '-O2', str(ROOT/'tools/latency-correlation.c'),
                        '-o', str(library), '-lm'], check=True)

    def saved_project(self, directory, rate, seconds, **recording):
        directory = Path(directory)
        (directory/'Media').mkdir()
        click.write_click(directory/'click.wav', rate, seconds)
        project = directory/'click-test.RPP'
        click.write_project(project, rate, seconds)
        write_recording(directory/'Media/take.wav', rate, seconds, **recording)
        # What REAPER saves: the recorded item on track 2.
        text = project.read_text().rstrip()
        assert text.endswith('>\n>') or text.endswith('  >\n>')
        item = '''    <ITEM
      POSITION 0
      LENGTH %d
      SOFFS 0
      <SOURCE WAVE
        FILE "Media/take.wav"
      >
    >
''' % seconds
        head, tail = text.rsplit('\n  >\n>', 1)
        project.write_text(head + '\n' + item + '  >\n>\n')
        return project

    def test_constant_offset_is_measured_to_the_sample(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = click.measure(self.saved_project(tmp, 48000, 10, offset=12), 10)
            self.assertEqual((result['clicks'], result['expected_clicks']), (19, 19))
            self.assertAlmostEqual(result['median_offset_samples'], 12, delta=.2)
            self.assertEqual(result['steps'], [])
            self.assertEqual(result['polarity'], 'normal')

    def test_one_packet_step_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = click.measure(self.saved_project(tmp, 44100, 10, offset=1, step_after=7, step=-6), 10)
            self.assertEqual(len(result['steps']), 1)
            self.assertEqual(result['steps'][0]['click'], 7)
            self.assertAlmostEqual(result['steps'][0]['to_samples']-result['steps'][0]['from_samples'], -6, delta=.3)

    def test_project_records_line_in_l_without_monitoring_or_master_send(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)/'p.RPP'
            click.write_project(project, 96000, 30)
            text = project.read_text()
            self.assertIn('SAMPLERATE 96000 1 0', text)
            self.assertIn('REC 1 6 0 0 0 0 0 0', text)
            recording_track = text.split('NAME "Recording - Line In L"')[1]
            self.assertIn('MAINSEND 0 0', recording_track)

    def test_script_waits_for_audio_and_keeps_recordings(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp)/'record-click.lua'
            click.write_script(script, 30)
            text = script.read_text()
            self.assertIn('reaper.Audio_IsRunning()', text)
            self.assertIn('reaper.Main_OnCommand(40667, 0)', text)
            self.assertIn('position >= 30.5', text)


if __name__ == '__main__':
    unittest.main()

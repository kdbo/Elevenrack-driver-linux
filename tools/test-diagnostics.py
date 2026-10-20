#!/usr/bin/env python3
"""Check the Monitor window's diagnostics against fake /proc and /sys trees."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('diagnostics', ROOT/'tools/eleven_rack_diagnostics.py')
diagnostics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostics)

TOP = '''S   ID  QUANT   RATE    WAIT    BUSY   W/Q   B/Q  ERR FORMAT           NAME
S   62      0      0    ---     ---   ---   ---     0                  alsa_input.usb-Digidesign_Eleven_Rack-01.capture.0.0
S   ID  QUANT   RATE    WAIT    BUSY   W/Q   B/Q  ERR FORMAT           NAME
R   62    256  44100  42.1us   1.2us  0.01  0.00    3    S32LE 8 44100 alsa_input.usb-Digidesign_Eleven_Rack-01.capture.0.0
R   61      0      0   7.2us   8.5us  0.00  0.00    0    S32LE 6 44100  + alsa_output.usb-Digidesign_Eleven_Rack-01.playback.0.0
'''


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class Diagnostics(unittest.TestCase):
    def tree(self, root, net_cpu='0', link='up', ksoftirqd_policy=os.SCHED_OTHER):
        proc, sys = root/'proc', root/'sys'
        write(proc/'interrupts', ' 123:  1  2  xhci_hcd\n 133:  5  0  iwlwifi\n')
        write(proc/'irq/123/effective_affinity_list', '2\n')
        write(proc/'irq/133/effective_affinity_list', net_cpu + '\n')
        write(proc/'cmdline', 'BOOT_IMAGE=/vmlinuz ro quiet\n')
        write(proc/'31/comm', 'ksoftirqd/2\n')
        xhci = sys/'devices/pci0000:00/0000:00:14.0'
        for irq in ('123', '124'):   # 124 is allocated but never requested
            write(xhci/'msi_irqs'/irq, '')
        (xhci/'usb1/1-9').mkdir(parents=True)
        (sys/'bus/usb/devices').mkdir(parents=True)
        (sys/'bus/usb/devices/1-9').symlink_to(xhci/'usb1/1-9')
        wifi = sys/'devices/pci0000:00/0000:02:00.0'
        write(wifi/'msi_irqs/133', '')
        write(sys/'class/net/wlp2s0/operstate', link + '\n')
        (sys/'class/net/wlp2s0/device').symlink_to(wifi)
        policy = {31: ksoftirqd_policy}
        return proc, sys, patch.multiple(
            diagnostics.os, sched_getscheduler=lambda pid: policy[pid],
            sched_getparam=lambda pid: type('P', (), {'sched_priority': 51 if policy[pid] else 0})())

    def check(self, **tree):
        with tempfile.TemporaryDirectory() as tmp:
            proc, sys, scheduler = self.tree(Path(tmp), **tree)
            with scheduler:
                return diagnostics.system_check('1-9', proc, sys)

    def levels(self, result):
        return [level for level, _ in result['findings']]

    def test_shared_cpu_and_normal_ksoftirqd_warn(self):
        result = self.check(net_cpu='2')
        self.assertEqual((result['controller'], result['irqs'], result['cpus']), ('0000:00:14.0', [123], [2]))
        self.assertEqual(result['shared_with_network'], {'wlp2s0': {'cpus': [2], 'up': True}})
        self.assertEqual(self.levels(result), ['warn', 'warn'])

    def test_separated_and_realtime_is_ok(self):
        result = self.check(ksoftirqd_policy=os.SCHED_FIFO)
        self.assertEqual(result['ksoftirqd'][2]['policy'], 'FIFO')
        self.assertEqual(self.levels(result), ['ok'])

    def test_shared_cpu_without_link_is_only_info(self):
        result = self.check(net_cpu='2', link='down', ksoftirqd_policy=os.SCHED_FIFO)
        self.assertEqual(self.levels(result), ['info', 'ok'])

    def test_pw_top_keeps_last_iteration(self):
        rows = diagnostics.parse_top(TOP)
        self.assertEqual(rows[62]['quantum'], '256')
        self.assertEqual(rows[62]['errors'], 3)
        self.assertEqual(rows[61]['quantum'], '0')

    def test_driver_stats_and_missing_counters(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = Path(tmp)
            self.assertIsNone(diagnostics.driver_stats(1, proc))
            write(proc/'asound/card1/eleven_stats',
                  'playback_gaps 2\ngap_total_us 1500\nlast_gap_us 1000\nlast_gap_boottime_ns 1000\n'
                  'playback_xruns 1\ncapture_xruns 0\nplayback_starts 4\ncapture_starts 4\n'
                  'capture_packet_errors 3\ncapture_empty_urbs 0\n')
            stats = diagnostics.driver_stats(1, proc)
            self.assertEqual((stats['playback_gaps'], stats['gap_total_us'], stats['playback_xruns'],
                              stats['playback_starts'], stats['capture_packet_errors']), (2, 1500, 1, 4, 3))
            self.assertIn('last_gap_seconds_ago', stats)

    def data(self, when, gaps=0, xruns=0):
        return {'time': when, 'device': 'Eleven Rack 1 · USB 1-9', 'location': '1-9',
                'driver': {'playback_gaps': gaps, 'last_gap_seconds_ago': when},
                'alsa': {'playback': {'state': 'RUNNING', 'rate': '44100'}},
                'pipewire': {'capture': {'id': 62, 'errors': xruns, 'quantum': '256', 'rate': '44100'}},
                'system': {'irqs': [123], 'cpus': [2], 'findings': [('ok', 'fine')]}}

    def records(self, updates, kernel=lambda *_: []):
        with tempfile.TemporaryDirectory() as tmp:
            recorder = diagnostics.Recorder(Path(tmp)/'log.jsonl', kernel=kernel)
            for data in updates:
                recorder.update(data)
            recorder.close()
            recorder.close()   # closing twice is harmless
            return [__import__('json').loads(line) for line in recorder.path.read_text().splitlines()], recorder

    def test_recorder_logs_changes_not_repeats(self):
        # Seconds-ago changes every reading and must not count as a change.
        lines, recorder = self.records([self.data(100), self.data(102), self.data(104, gaps=1), self.data(106, gaps=1)])
        self.assertEqual([r['type'] for r in lines], ['start', 'event', 'stop'])
        self.assertEqual(lines[1]['changes'], {'driver.playback_gaps': [0, 1]})
        self.assertEqual(recorder.events, 1)
        self.assertIn('kernel', lines[0]['environment'])

    def test_recorder_snapshots_and_kernel_messages(self):
        kernel = lambda location, since, until: [{'time': until, 'message': 'Eleven Rack: playback ran dry'}]
        lines, _ = self.records([self.data(100), self.data(130), self.data(161, xruns=2)], kernel=kernel)
        types = [r['type'] for r in lines]
        self.assertEqual(types.count('kernel'), 3)
        self.assertEqual(types.count('snapshot'), 1)
        self.assertIn({'pipewire.capture.errors': [0, 2]}, [r.get('changes') for r in lines])

    def test_kernel_messages_with_empty_window_are_not_an_error(self):
        def fail(*_args, **_kwargs):
            raise AssertionError('journalctl must not run for an empty window')
        self.assertEqual(diagnostics.kernel_messages('1-9', 100.0, 99.5, run=fail), [])

    def test_recorder_notes_unreadable_kernel_log_once(self):
        lines, _ = self.records([self.data(100), self.data(102)], kernel=lambda *_: None)
        self.assertEqual([r['type'] for r in lines].count('note'), 1)

    def test_cpu_list(self):
        self.assertEqual(diagnostics.cpu_list('0-2,5\n'), {0, 1, 2, 5})


if __name__ == '__main__':
    unittest.main()

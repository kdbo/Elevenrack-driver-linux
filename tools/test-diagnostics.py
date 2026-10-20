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

    def stat(self, rt_priority, policy):
        # Fields after the command name: state (3) ... rt_priority (40), policy (41).
        rest = ['S'] + ['0'] * 36 + [str(rt_priority), str(policy)] + ['0'] * 3
        return '123 (data-loop.0) ' + ' '.join(rest) + '\n'

    def realtime_tree(self, root, policy, priority, nice_limit, irq_priority=50):
        proc = root/'proc'
        for pid, user, comm in ((10, 117, 'pipewire'), (20, os.getuid(), 'pipewire')):
            write(proc/str(pid)/'comm', comm + '\n')
            write(proc/str(pid)/'status', f'Name:\t{comm}\nUid:\t{user}\t{user}\t{user}\t{user}\n')
            write(proc/str(pid)/'limits', f'Max nice priority         {nice_limit}   {nice_limit}\n'
                                          'Max realtime priority     95   95\n')
            write(proc/str(pid)/'task'/str(pid + 1)/'comm', 'data-loop.0\n')
            # The login screen's PipeWire (uid 117) runs at RR 20 and must be ignored.
            write(proc/str(pid)/'task'/str(pid + 1)/'stat',
                  self.stat(20, 2) if pid == 10 else self.stat(priority, policy))
        write(proc/'41'/'comm', 'irq/124-xhci_hcd\n')
        write(proc/'41'/'stat', self.stat(85, 1))
        write(proc/'42'/'comm', 'irq/9-acpi\n')
        write(proc/'42'/'stat', self.stat(irq_priority, 1))
        write(proc/'43'/'comm', 'irq/37-i2c\n')
        write(proc/'43'/'stat', self.stat(irq_priority, 1))
        return proc

    def test_pipewire_realtime_ignores_other_users(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = self.realtime_tree(Path(tmp), 1, 88, 39)
            realtime = diagnostics.pipewire_realtime(proc)
            self.assertEqual((realtime['pid'], realtime['policy'], realtime['priority']), (20, 'FIFO', 88))
            self.assertEqual((realtime['rtprio_limit'], realtime['nice_limit']), (95, 39))
            self.assertEqual(diagnostics.irq_thread_priorities(proc)['irq/124-xhci_hcd'], 85)

    def test_rtkit_fallback_below_irq_threads_warns_with_threadirqs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc, sys, scheduler = self.tree(root, ksoftirqd_policy=os.SCHED_FIFO)
            self.realtime_tree(root, 2, 20, 0)
            write(proc/'cmdline', 'ro quiet threadirqs\n')
            with scheduler:
                result = diagnostics.system_check('1-9', proc, sys)
            warnings = [text for level, text in result['findings'] if level == 'warn']
            self.assertEqual(len(warnings), 1)
            self.assertIn('RR 20', warnings[0])
            self.assertIn('nice -19', warnings[0])
            write(proc/'20'/'task'/'21'/'stat', self.stat(88, 1))
            with scheduler:
                self.assertEqual(self.levels(diagnostics.system_check('1-9', proc, sys)), ['ok'])

    def test_desktop_streams_and_node_names(self):
        objects = [{'id': 179, 'type': 'PipeWire:Interface:Node', 'info': {'props': {
                        'media.class': 'Stream/Output/Audio', 'application.name': 'Firefox',
                        'node.latency': '2752/48000'}}},
                   {'id': 180, 'type': 'PipeWire:Interface:Node', 'info': {'props': {
                        'media.class': 'Stream/Output/Audio', 'client.api': 'jack', 'node.name': 'REAPER'}}}]
        self.assertEqual(diagnostics.desktop_streams(objects),
                         [{'id': 179, 'name': 'Firefox', 'latency_ms': 57.3}])
        self.assertEqual(diagnostics.parse_top(TOP)[61]['name'], 'alsa_output.usb-Digidesign_Eleven_Rack-01.playback.0.0')

    def test_cpu_list(self):
        self.assertEqual(diagnostics.cpu_list('0-2,5\n'), {0, 1, 2, 5})


if __name__ == '__main__':
    unittest.main()

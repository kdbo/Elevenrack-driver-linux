#!/usr/bin/env python3
"""Synthetic xHCI/PipeWire attribution checks; no audio device, root or tracefs required."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('transport_trace', ROOT/'tools/transport_trace.py')
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)
RATE, QUANTUM, T0 = 44100, 256, 1_700_000_000_000_000_000
PERIOD = QUANTUM*1_000_000_000//RATE
OFFSET = T0 - 5_000_000_000   # realtime minus monotonic: trace clock reads 5.0 s at T0


def trace_line(seconds, status='Ring Underrun', dci=6):
    mono = 5_000_000_000 + int(seconds*1_000_000_000)
    return (f"{OFFSET}           <idle>-0       [002] d.h1. {mono//1_000_000_000}.{mono%1_000_000_000//1000:06d}: "
            f"xhci_handle_event: Event: @00000000ffff0000 TRB 0000000012340000 status '{status}' "
            f"len 0 slot 2 ep {dci} type 'Transfer Event' flags e:C")


class Attribution(unittest.TestCase):
    def recording(self, directory, seconds=3):
        raw = Path(directory)/'quantum-256-run-1.raw'
        lines = ['frame,frames,realtime_ns,monotonic_raw_ns']
        for i in range(seconds*RATE//QUANTUM):
            lines.append(f'{i*QUANTUM},{QUANTUM},{T0+i*PERIOD},{T0+i*PERIOD}')
        Path(str(raw)+'.timestamps.csv').write_text('\n'.join(lines)+'\n')
        return raw

    def classify(self, faults=(), underruns=(), resyncs=(), xhci='available', pipewire='available'):
        with tempfile.TemporaryDirectory() as directory:
            raw = self.recording(directory)
            log = Path(directory)/'xhci.log'
            log.write_text('# header\n' + ''.join(trace_line(s)+'\n' for s in underruns))
            events = [{'start_ns': T0+int(s*1e9), 'end_ns': T0+int(s*1e9), 'message': 'resync'} for s in resyncs]
            return transport.attribute(raw, RATE, QUANTUM, [{'seconds': s} for s in faults],
                                       xhci, transport.xhci_events(log), pipewire, events)

    def test_trace_line_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory)/'xhci.log'
            log.write_text(trace_line(1.5)+'\n'+trace_line(2.0, 'Missed Service Error', 3)+'\n')
            first, second = transport.xhci_events(log)
            self.assertEqual(first['start_ns'], T0+1_500_000_000)
            self.assertEqual((first['status'], first['slot'], first['endpoint']), ('Ring Underrun', 2, '0x03'))
            self.assertEqual(second['endpoint'], '0x81')

    def test_clean_run(self):
        self.assertEqual(self.classify(underruns=[1.0])['classification'], 'clean')

    def test_underrun_before_step(self):
        # The gap plays out, then appears in the capture one round trip later.
        result = self.classify(faults=[1.56], underruns=[1.5])
        self.assertEqual(result['classification'], 'xhci')
        self.assertEqual(result['fault_windows'][0]['xhci'], ['Ring Underrun slot 2 ep 0x03'])
        self.assertEqual(result['xhci_event_count'], 1)

    def test_resync_and_both(self):
        self.assertEqual(self.classify(faults=[1.56], resyncs=[1.52])['classification'], 'pipewire_resync')
        self.assertEqual(self.classify(faults=[1.56], underruns=[1.5], resyncs=[1.5])['classification'],
                         'xhci+pipewire_resync')

    def test_far_events_leave_step_unexplained(self):
        self.assertEqual(self.classify(faults=[2.5], underruns=[1.0], resyncs=[1.0])['classification'],
                         'unexplained')
        self.assertEqual(self.classify(faults=[2.5, 1.56], underruns=[1.5])['classification'], 'mixed')

    def test_missing_source_does_not_claim_unexplained(self):
        result = self.classify(faults=[2.5], xhci='helper not installed')
        self.assertEqual(result['classification'], 'unknown')
        result = self.classify(faults=[1], xhci='helper not installed', pipewire='unavailable: no journal')
        self.assertEqual(result['classification'], 'unavailable')


spec = importlib.util.spec_from_file_location('usb_flight', ROOT/'tools/analyze-usb-flight.py')
usb_flight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(usb_flight)


def flight_line(us, cpu, event, detail, task='<idle>-0'):
    return f'{task:>20} [{cpu:03d}] d.h1. {us//1_000_000}.{us%1_000_000:06d}: {event}: {detail}'


class FlightRecorder(unittest.TestCase):
    def dump(self, stall_us=0, empty_at=None):
        """1 ms capture URBs on CPU 2, each releasing a playback URB 30 us later.

        A stall before the 18th capture delays its handling; the underrun follows.
        """
        lines, t = ['# flight recorder armed; trigger: Ring Underrun on DCI 6',
                    f'# DUMP 0 offset_ns {OFFSET}'], 100_000_000
        for i in range(20):
            if i == 17 and stall_us:
                lines.append(flight_line(t-50, 2, 'sched_switch', 'prev_comm=swapper/2 ==> next_comm=busy', 'busy-42'))
                t += stall_us
            actual = 0 if i == empty_at else 3328
            lines.append(flight_line(t, 2, 'irq_handler_entry', 'irq=127 name=xhci_hcd'))
            lines.append(flight_line(t+5, 2, 'xhci_urb_giveback',
                                     f'1-9 ep3in-isoc: urb 0000000000000001 pipe 1 slot 7 length {actual}/3328 '
                                     'sgs 0/0 stream 0 flags 00000204'))
            lines.append(flight_line(t+30, 2, 'xhci_urb_enqueue',
                                     '1-9 ep3out-isoc: urb 0000000000000002 pipe 2 slot 7 length 0/1872 '
                                     'sgs 0/0 stream 0 flags 00000204'))
            t += 1000
        lines.append(flight_line(t-500, 0, 'xhci_handle_event',
                                 "Event: @0000 TRB 0000000000000000 status 'Ring Underrun' len 0 slot 7 "
                                 "ep 6 type 'Transfer Event' flags e:C"))
        lines.append('# END')
        return '\n'.join(lines)+'\n'

    def analyze(self, **dump):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory)/'xhci-flight.log'
            log.write_text(self.dump(**dump))
            results = usb_flight.analyze(log)
        self.assertEqual(len(results), 1)
        return results[0]

    def test_capture_stall_before_underrun(self):
        result = self.analyze(stall_us=2500)
        self.assertEqual(result['slot'], 7)
        self.assertEqual(result['capture_interval']['max_us'], 3500.0)
        self.assertEqual(result['capture_interval']['median_us'], 1000.0)
        self.assertEqual(result['capture_to_playback_submit']['max_us'], 25.0)
        self.assertEqual(result['empty_capture_urbs'], 0)
        self.assertIn('sched_switch', {e['event'] for e in result['timeline']})

    def test_empty_capture_urbs_are_counted(self):
        self.assertEqual(self.analyze(empty_at=15)['empty_capture_urbs'], 1)

    def test_dump_without_playback_underrun(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory)/'xhci-flight.log'
            log.write_text(self.dump().replace("ep 6 type", "ep 3 type"))
            self.assertIn('error', usb_flight.analyze(log)[0])


class Helper(unittest.TestCase):
    def test_helper_builds_and_fails_cleanly_without_privilege(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory)/'xhci-trace'
            subprocess.run(['cc', '-O2', '-Wall', '-Wextra', '-Werror', str(ROOT/'tools/xhci-trace.c'),
                            '-o', str(binary)], check=True)
            self.assertEqual(subprocess.run([str(binary)], capture_output=True).returncode, 2)
            monitor = transport.XhciMonitor(Path(directory)/'xhci.log', helper=binary)
            with monitor:
                pass
            self.assertTrue(monitor.status == 'available' or monitor.status.startswith('unavailable'))
            json.dumps(monitor.status)


if __name__ == '__main__':
    unittest.main()

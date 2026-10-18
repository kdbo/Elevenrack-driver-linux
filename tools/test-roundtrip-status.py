#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import types
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('settings',Path(__file__).with_name('eleven-rack-settings.py'))
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)

def nodes(quantum=0):
    return [{'type':'PipeWire:Interface:Node','info':{'state':'running','props':{'api.alsa.card.id':'Rack','node.name':prefix+'Rack'},'params':{'Latency':[dict(direction=direction,minQuantum=quantum,maxQuantum=quantum,minRate=240,maxRate=240,minNs=0,maxNs=0)]}}} for prefix,direction in [('alsa_input.','Output'),('alsa_output.','Input')]]

class RoundtripStatus(unittest.TestCase):
    def setUp(self):
        # Never depend on a Rack being attached to the machine running the tests.
        device=patch.object(s,'selected_device',return_value={'card':1,'card_id':'Rack'})
        device.start(); self.addCleanup(device.stop)

    def test_automatic_uses_backend_frames_without_assuming_default_quantum(self):
        import json
        with patch.object(s,'card',return_value=1), patch.object(Path,'read_text',return_value='rate: 48000\n'), patch.object(s.subprocess,'run',return_value=types.SimpleNamespace(returncode=0,stdout=json.dumps(nodes()))):
            self.assertEqual(s.roundtrip_status({'clock.force-quantum':'0','clock.quantum':'1024'}),'Roundtrip latency · 10.00 ms')

    def test_forced_quantum_is_still_used_when_required(self):
        self.assertEqual(s.reported_roundtrip(nodes(1),48000,512),[1000*1504/48000]*2)

    def test_unknown_quantum_never_produces_guessed_latency(self):
        with self.assertRaisesRegex(ValueError,'active graph quantum'):
            s.reported_roundtrip(nodes(1),48000,None)

    def test_live_quantum_reads_the_last_pw_top_iteration_and_follows_the_driver(self):
        top=('S   ID  QUANT   RATE    WAIT    BUSY   W/Q   B/Q  ERR FORMAT           NAME \n'
             'C   59      0      0    ---     ---   ---   ---     0                  alsa_input.Rack\n'
             'S   ID  QUANT   RATE    WAIT    BUSY   W/Q   B/Q  ERR FORMAT           NAME \n'
             'R   59    256  48000  90.0us   2.3us  0.03  0.00    1    S32LE 8 48000 alsa_input.Rack\n'
             'R   58      0      0  13.6us  33.4us  0.01  0.01    1    S32LE 6 48000  + alsa_output.Rack\n')
        self.assertEqual(s.live_quantum(top,'alsa_input.Rack'),256)
        self.assertEqual(s.live_quantum(top,'alsa_output.Rack'),256)
        self.assertIsNone(s.live_quantum(top.split('S   ID')[1],'alsa_input.Rack'))
        self.assertIsNone(s.live_quantum(top,'alsa_input.Other'))

    def test_automatic_buffer_uses_the_live_quantum(self):
        import json
        top=('S   ID  QUANT   RATE    WAIT    BUSY   W/Q   B/Q  ERR FORMAT           NAME \n'
             'R   59    512  48000  90.0us   2.3us  0.03  0.00    0    S32LE 8 48000 alsa_input.Rack\n')
        def run(args,**kwargs):
            out=json.dumps(nodes(1)) if args[0]=='pw-dump' else top
            return types.SimpleNamespace(returncode=0,stdout=out)
        with patch.object(s,'card',return_value=1), \
             patch.object(Path,'read_text',return_value='rate: 48000\n'), patch.object(s.subprocess,'run',side_effect=run):
            self.assertEqual(s.roundtrip_status({'clock.force-quantum':'0'}),'Roundtrip latency · %.2f ms' % (1000*(2*512+480)/48000))
            # The live quantum is reported for the status bar, not folded into "automatic".
            self.assertEqual(s.roundtrip_report({'clock.force-quantum':'0'})[1],512)
            self.assertIsNone(s.roundtrip_report({'clock.force-quantum':'128'})[1])

    def test_idle_stays_unavailable(self):
        with patch.object(s,'card',return_value=1), patch.object(Path,'read_text',return_value='closed\n'):
            self.assertEqual(s.roundtrip_status({'clock.force-quantum':'0'}),'Roundtrip latency unavailable')

if __name__=='__main__': unittest.main()

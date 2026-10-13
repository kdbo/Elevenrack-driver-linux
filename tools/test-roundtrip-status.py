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
    def test_automatic_uses_backend_frames_without_assuming_default_quantum(self):
        import json
        with patch.object(s,'card',return_value=1), patch.object(Path,'read_text',return_value='rate: 48000\n'), patch.object(s.subprocess,'run',return_value=types.SimpleNamespace(returncode=0,stdout=json.dumps(nodes()))):
            self.assertEqual(s.roundtrip_status({'clock.force-quantum':'0','clock.quantum':'1024'}),'Roundtrip latency · 10.00 ms')

    def test_forced_quantum_is_still_used_when_required(self):
        self.assertEqual(s.reported_roundtrip(nodes(1),48000,512),[1000*1504/48000]*2)

    def test_unknown_quantum_never_produces_guessed_latency(self):
        with self.assertRaisesRegex(ValueError,'active graph quantum'):
            s.reported_roundtrip(nodes(1),48000,None)

    def test_idle_stays_unavailable(self):
        with patch.object(s,'card',return_value=1), patch.object(Path,'read_text',return_value='closed\n'):
            self.assertEqual(s.roundtrip_status({'clock.force-quantum':'0'}),'Roundtrip latency unavailable')

if __name__=='__main__': unittest.main()

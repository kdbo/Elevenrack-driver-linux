import asyncio
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('bridge', Path(__file__).parents[1] / 'bridge.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Midi:
    def __init__(self, ports):
        self.ports = ports
        self.opened = None
        self.sent = []
    def get_ports(self): return self.ports
    def close_port(self): self.opened = None
    def cancel_callback(self): pass
    def ignore_types(self, **kwargs): self.filters = kwargs
    def open_port(self, index): self.opened = index
    def set_callback(self, callback): self.callback = callback
    def send_message(self, message): self.sent.append(message)


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.input = Midi(['Eleven Rack Rig input', 'External input'])
        self.output = Midi(['Eleven Rack Rig output', 'External output'])
        self.bridge = module.Bridge(self.input, self.output, asyncio.get_running_loop())
        self.owner = object()

    async def test_combined_indexes_map_to_local_ports(self):
        result = self.bridge.connect(self.owner, 0, 2)
        self.assertEqual(0, self.output.opened)
        self.assertEqual('connected', result['type'])
        self.assertFalse(self.input.filters['sysex'])
        self.assertNotIn('_local', self.bridge.ports()['devices'][0])

    async def test_wrong_direction_and_stale_indexes_rejected(self):
        with self.assertRaises(ValueError): self.bridge.connect(self.owner, 2, 0)
        self.input.ports = ['Replacement']
        with self.assertRaises(ValueError): self.bridge.connect(self.owner, 0, 2)

    async def test_other_client_cannot_send_or_disconnect(self):
        self.bridge.connect(self.owner, 0, 2)
        for command in ('send', 'disconnect'):
            with self.assertRaises(ValueError):
                await self.bridge.command(object(), {'cmd': command, 'hex': 'C0 01'})
        self.assertIs(self.owner, self.bridge.owner)

    async def test_valid_send_and_disconnect(self):
        self.bridge.connect(self.owner, 0, 2)
        await self.bridge.command(self.owner, {'cmd': 'send', 'hex': 'F0 7E 7F 06 01 F7'})
        self.assertEqual([[240,126,127,6,1,247]], self.output.sent)
        await self.bridge.command(self.owner, {'cmd': 'disconnect'})
        self.assertIsNone(self.input.opened)
        self.assertIsNone(self.output.opened)

    async def test_malformed_commands(self):
        for value in ([], None, {'cmd': 'bogus'}):
            with self.assertRaises(ValueError): await self.bridge.command(self.owner, value)

    async def test_shared_rig_input_preserves_editor_owner(self):
        self.bridge.connect(self.owner, 0, 2)
        task = asyncio.create_task(self.bridge.command(object(), {'cmd': 'rig_input', 'value': 2}))
        await asyncio.sleep(0)
        self.assertEqual([240, 19, 11, 15, 0, 61, 2, 247], self.output.sent[-2])
        self.assertEqual([240, 19, 11, 15, 1, 61, 247], self.output.sent[-1])
        self.bridge.rig_reply.set_result(2)
        self.assertEqual(2, (await task)['value'])
        self.assertIs(self.owner, self.bridge.owner)
        self.assertEqual(0, self.input.opened)

    async def test_shared_rig_input_checks_readback_and_availability(self):
        self.assertFalse((await self.bridge.command(object(), {'cmd': 'rig_input'}))['available'])
        self.bridge.connect(self.owner, 0, 2)
        for value in (-1, 9, True):
            with self.assertRaises(ValueError):
                await self.bridge.command(object(), {'cmd': 'rig_input', 'value': value})
        task = asyncio.create_task(self.bridge.command(object(), {'cmd': 'rig_input', 'value': 1}))
        await asyncio.sleep(0)
        self.bridge.rig_reply.set_result(0)
        with self.assertRaises(ValueError): await task
        self.assertIsNone(self.bridge.rig_reply)

    def test_hex_validation(self):
        for text in ('', 'F0 01', 'F0 FF F7', 'C0 01 02', 'B0 01', 'AA ZZ', '01 02 03'):
            with self.assertRaises(ValueError): module.parse_hex(text)
        self.assertEqual([0xB0,69,127], module.parse_hex('B0 45 7F'))


if __name__ == '__main__':
    unittest.main()

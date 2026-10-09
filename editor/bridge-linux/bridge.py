#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Koen de Boevé
"""Linux ALSA MIDI transport for Eleven Edit's existing WebSocket protocol."""
import argparse
import asyncio
import json
import signal
import sys


def parse_hex(text):
    if not isinstance(text, str):
        raise ValueError('send requires a hex string')
    data = list(bytes.fromhex(text))
    if not data or len(data) > 65536:
        raise ValueError('Empty or oversized MIDI message')
    if data[0] == 0xF0:
        if data[-1] != 0xF7 or any(b > 127 for b in data[1:-1]):
            raise ValueError('Invalid SysEx message')
    else:
        length = 2 if 0xC0 <= data[0] <= 0xDF else 3
        if not 0x80 <= data[0] <= 0xEF or len(data) != length or any(b > 127 for b in data[1:]):
            raise ValueError('Expected a complete MIDI channel message or SysEx')
    return data


class Bridge:
    def __init__(self, midi_in, midi_out, loop):
        self.input, self.output, self.loop = midi_in, midi_out, loop
        self.devices = []
        self.clients = set()
        self.owner = None
        self.connected = None
        self.rig_lock = asyncio.Lock()
        self.rig_reply = None
        self.refresh()

    def refresh(self):
        self.devices = []
        for kind, midi in (('in', self.input), ('out', self.output)):
            for local_index, name in enumerate(midi.get_ports()):
                self.devices.append({'index': len(self.devices), 'kind': kind,
                                     'name': name, 'desc': 'ALSA MIDI', '_local': local_index})
        return self.ports()

    def ports(self):
        return {'type': 'ports', 'devices': [
            {k: v for k, v in d.items() if k != '_local'} for d in self.devices]}

    async def emit(self, event):
        if self.owner is not None:
            try:
                await self.owner.send(json.dumps(event))
            except Exception:
                self.disconnect()

    def receive(self, event, _data=None):
        message, _delta = event
        if message:
            self.loop.call_soon_threadsafe(self.deliver, list(message))

    def deliver(self, message):
        if (len(message) == 8 and message[:4] == [0xF0, 0x13, 0x0B, 0x0F]
                and message[4] in (0x02, 0x12) and message[5] == 0x3D
                and message[7] == 0xF7 and 0 <= message[6] < 9):
            if self.rig_reply is not None and not self.rig_reply.done():
                self.rig_reply.set_result(message[6])
        asyncio.create_task(self.emit({'type': 'midi_in', 'bytes': message,
                                      'hex': ' '.join(f'{b:02X}' for b in message)}))

    def disconnect(self):
        self.input.cancel_callback()
        self.input.close_port()
        self.output.close_port()
        self.connected = None
        self.owner = None

    def connect(self, client, input_index, output_index):
        if self.owner is not None and self.owner is not client:
            raise ValueError('MIDI ports are owned by another editor session')
        for index, kind in ((input_index, 'in'), (output_index, 'out')):
            if type(index) is not int or not 0 <= index < len(self.devices) or self.devices[index]['kind'] != kind:
                raise ValueError(f'Invalid {kind} port index')
        selected = [self.devices[input_index], self.devices[output_index]]
        # Reject stale indexes rather than silently opening a different device.
        for device, midi in zip(selected, (self.input, self.output)):
            current = midi.get_ports()
            if device['_local'] >= len(current) or current[device['_local']] != device['name']:
                self.refresh()
                raise ValueError('MIDI ports changed; refresh the port list')
        self.disconnect()
        try:
            self.input.ignore_types(sysex=False, timing=True, active_sense=True)
            self.input.open_port(selected[0]['_local'])
            self.output.open_port(selected[1]['_local'])
            self.owner = client
            self.connected = selected
            self.input.set_callback(self.receive)
        except Exception:
            self.disconnect()
            raise
        return {'type': 'connected', 'inPort': input_index, 'outPort': output_index}

    async def command(self, client, message):
        if not isinstance(message, dict):
            raise ValueError('Expected a JSON object')
        command = message.get('cmd')
        if command == 'rig_input':
            value = message.get('value')
            if value is not None and (type(value) is not int or not 0 <= value < 9):
                raise ValueError('Invalid Rig Input value')
            async with self.rig_lock:
                if self.owner is None or not self.connected or any(
                        'eleven rack' not in device['name'].lower() for device in self.connected):
                    return {'type': 'rig_input', 'available': False}
                self.rig_reply = self.loop.create_future()
                try:
                    if value is not None:
                        self.output.send_message([0xF0, 0x13, 0x0B, 0x0F, 0, 0x3D, value, 0xF7])
                    self.output.send_message([0xF0, 0x13, 0x0B, 0x0F, 1, 0x3D, 0xF7])
                    try:
                        actual = await asyncio.wait_for(self.rig_reply, timeout=2)
                    except asyncio.TimeoutError:
                        raise ValueError('No recognized Rig Input reply from the Rack')
                    if value is not None and actual != value:
                        raise ValueError('Rig Input change was not confirmed by the Rack')
                    return {'type': 'rig_input', 'available': True, 'value': actual}
                finally:
                    self.rig_reply = None
        if command == 'list_ports':
            return self.refresh()
        if command == 'connect':
            return self.connect(client, message.get('inPort'), message.get('outPort'))
        if command in ('disconnect', 'send'):
            if self.owner is not client:
                raise ValueError('This editor session does not own the MIDI ports')
            if command == 'disconnect':
                self.disconnect()
                return {'type': 'disconnected'}
            self.output.send_message(parse_hex(message.get('hex')))
            return None
        raise ValueError('Unknown bridge command')

    async def session(self, client, _path=None):
        self.clients.add(client)
        try:
            await client.send(json.dumps(self.refresh()))
            async for raw in client:
                try:
                    event = await self.command(client, json.loads(raw))
                    if event is not None:
                        await client.send(json.dumps(event))
                except Exception as error:
                    await client.send(json.dumps({'type': 'error', 'message': str(error)}))
        finally:
            if self.owner is client:
                self.disconnect()
            self.clients.discard(client)

    async def watch_ports(self):
        while True:
            await asyncio.sleep(1)
            old = self.devices
            event = self.refresh()
            if old == self.devices:
                continue
            if self.connected:
                for device, midi in zip(self.connected, (self.input, self.output)):
                    if device['name'] not in midi.get_ports():
                        await self.emit({'type': 'disconnected'})
                        self.disconnect()
                        break
            for client in list(self.clients):
                try:
                    await client.send(json.dumps(event))
                except Exception:
                    pass


async def run(args):
    import rtmidi
    from websockets.legacy.server import serve
    loop = asyncio.get_running_loop()
    midi_in = rtmidi.MidiIn(rtmidi.API_LINUX_ALSA, 'Eleven Rack Editor Input')
    midi_out = rtmidi.MidiOut(rtmidi.API_LINUX_ALSA, 'Eleven Rack Editor Output')
    bridge = Bridge(midi_in, midi_out, loop)
    if args.list:
        print(json.dumps(bridge.ports(), indent=2))
        return
    stopped = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stopped.set)
    def stdin_ready():
        line = sys.stdin.readline()
        if not line or line.strip() == 'SHUTDOWN':
            loop.remove_reader(sys.stdin)
            stopped.set()
    if not sys.stdin.isatty():
        loop.add_reader(sys.stdin, stdin_ready)
    try:
        async with serve(bridge.session, '127.0.0.1', 57121,
                         origins=[None, 'null', 'file://'], max_size=131072):
            print('Linux ALSA bridge listening on 127.0.0.1:57121', flush=True)
            watcher = asyncio.create_task(bridge.watch_ports())
            try:
                await stopped.wait()
            finally:
                watcher.cancel()
    finally:
        bridge.disconnect()
        midi_in.delete()
        midi_out.delete()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true')
    try:
        asyncio.run(run(parser.parse_args()))
    except Exception as error:
        print(f'Linux MIDI bridge: {error}', file=sys.stderr)
        sys.exit(1)

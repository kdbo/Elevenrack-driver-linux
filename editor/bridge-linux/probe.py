#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Koen de Boevé
"""Read-only WebSocket/MIDI probe; no preset selection or parameter writes."""
import asyncio
import json
import sys
from pathlib import Path

from websockets.legacy.client import connect


async def probe():
    process = await asyncio.create_subprocess_exec(
        sys.executable, str(Path(__file__).with_name('bridge.py')),
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT)
    try:
        line = await asyncio.wait_for(process.stdout.readline(), 5)
        if b'listening' not in line:
            raise RuntimeError(line.decode().strip())
        async with connect('ws://127.0.0.1:57121', origin='file://') as socket:
            ports = json.loads(await socket.recv())['devices']
            selected = []
            for kind in ('in', 'out'):
                candidates = [p for p in ports if p['kind'] == kind and
                              'eleven rack' in p['name'].lower() and
                              'external' not in p['name'].lower()]
                if len(candidates) != 1:
                    raise RuntimeError(f'Ambiguous Rig {kind} port: {ports}')
                selected.append(candidates[0]['index'])
            await socket.send(json.dumps({'cmd': 'connect', 'inPort': selected[0], 'outPort': selected[1]}))
            status = json.loads(await socket.recv())
            if status['type'] != 'connected':
                raise RuntimeError(status)
            print('Connected to Eleven Rack Rig MIDI ports')
            for label, request, prefix in (
                ('identity', 'F0 7E 7F 06 01 F7', [240,126]),
                ('Rig Input', 'F0 13 0B 0F 01 3D F7', [240,19,11,15,18,61]),
            ):
                await socket.send(json.dumps({'cmd': 'send', 'hex': request}))
                deadline = asyncio.get_running_loop().time() + 4
                while True:
                    remaining = deadline - asyncio.get_running_loop().time()
                    reply = json.loads(await asyncio.wait_for(socket.recv(), max(0, remaining)))
                    if reply['type'] == 'error':
                        raise RuntimeError(reply['message'])
                    if reply.get('bytes', [])[:len(prefix)] == prefix:
                        print(f'{label}: {reply["hex"]}')
                        break
    finally:
        if process.returncode is None:
            process.stdin.write(b'SHUTDOWN\n')
            await process.stdin.drain()
            try:
                await asyncio.wait_for(process.wait(), 3)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()


if __name__ == '__main__':
    asyncio.run(probe())

#!/usr/bin/env python3
"""Check backend linking and preservation of the distro's SPA factories without audio hardware."""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path


class Factory(ctypes.Structure):
    _fields_ = [('version', ctypes.c_uint32), ('name', ctypes.c_char_p)]


def factories(path):
    library = ctypes.CDLL(str(path))
    enumerate_factory = library.spa_handle_factory_enum
    enumerate_factory.argtypes = [ctypes.POINTER(ctypes.POINTER(Factory)), ctypes.POINTER(ctypes.c_uint32)]
    enumerate_factory.restype = ctypes.c_int
    index = ctypes.c_uint32()
    factory = ctypes.POINTER(Factory)()
    names = []
    for _ in range(256):
        result = enumerate_factory(ctypes.byref(factory), ctypes.byref(index))
        if result < 0:
            raise RuntimeError(f'Factory enumeration failed for {path}: {result}')
        if result == 0:
            return names
        names.append(factory.contents.name.decode())
    raise RuntimeError('Factory enumeration did not terminate')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, default=Path(__file__).resolve().parent.parent / 'build/latency')
    args = parser.parse_args()
    metadata = json.loads((args.build / 'backend-build.json').read_text())
    backend = args.build / 'libspa-eleven-latency.so'
    if hashlib.sha256(backend.read_bytes()).hexdigest() != metadata['library_sha256']:
        raise RuntimeError('Library checksum does not match build metadata')
    original = factories(metadata['system_alsa_plugin'])
    actual = factories(backend.resolve())
    replacements = ['api.alsa.pcm.source', 'api.alsa.pcm.sink', 'api.alsa.pcm.device']
    expected = replacements + [name for name in original if name not in replacements]
    if actual != expected or len(set(actual)) != len(actual):
        raise RuntimeError(f'Backend lost or duplicated distribution factories: {actual!r} != {expected!r}')
    print(f'PipeWire {metadata["pipewire_version"]}: loaded backend and preserved {len(actual)} SPA factories')


if __name__ == '__main__':
    main()

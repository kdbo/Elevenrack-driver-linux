#!/usr/bin/env python3
# Copyright (c) 2026 Koen de Boevé
# SPDX-License-Identifier: MIT
"""Generate known-pitch calibration tones; no playback or device changes."""
import math
from pathlib import Path
import struct
import wave

RATE = 48000
DEST = Path(__file__).resolve().parents[2] / 'build' / 'tuner-reference.wav'
DEST.parent.mkdir(parents=True, exist_ok=True)
with wave.open(str(DEST), 'wb') as audio:
    audio.setparams((2, 2, RATE, 0, 'NONE', 'not compressed'))
    for index, cents in enumerate((-40, -20, 0, 20, 40)):
        frequency = 220 * 2 ** (cents / 1200)
        print(f'{index * 7:02d}–{index * 7 + 5:02d}s: A3 {cents:+d} cents, {frequency:.6f} Hz')
        samples = bytearray()
        for frame in range(5 * RATE):
            fade = min(1, frame / (RATE * .02), (5 * RATE - 1 - frame) / (RATE * .02))
            sample = round(32767 * .06 * fade * math.sin(2 * math.pi * frequency * frame / RATE))
            samples.extend(struct.pack('<hh', sample, sample))
        audio.writeframes(samples)
        audio.writeframes(bytes(2 * RATE * 4))
print(DEST)

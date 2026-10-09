# Tuner calibration

The tuner note mapping has been corrected using an actual E/A/D capture.
The scale of the companion 0x41 needle stream remains unverified. A cents
label must wait for measured calibration rather than an assumed multiplier.

Generate a known reference with:

```bash
python3 editor/tools/make-tuner-reference.py
```

This creates `build/tuner-reference.wav`: stereo PCM at 48 kHz, amplitude
0.06, containing A3 (220 Hz at A=440) at the following offsets. Each tone
lasts five seconds, followed by two seconds of silence.

| Time | Offset | Frequency |
| --- | --- | --- |
| 0–5 s | −40 cents | 214.975 Hz |
| 7–12 s | −20 cents | 217.473 Hz |
| 14–19 s | 0 cents | 220 Hz |
| 21–26 s | +20 cents | 222.556 Hz |
| 28–33 s | +40 cents | 225.142 Hz |

Set the Rack's tuner reference to A=440. Connect a **separate audio source**
(such as the computer's headphone output) to the Rack's Line Input L and
select Line In L as Rig Input. Start source volume low and play the WAV
through that source, not through the Rack's Main Out. Open the tuner in the
editor. Restore the previous Rig Input afterward.

Record raw 0x41 needle and 0x42 note/tune replies during each plateau,
discarding attack/decay transitions. Compare stable values against the known
offsets, test whether the response is linear, and independently validate at
another note before adding calibrated cents labels. The stream can be
captured using `npm start -- --logs` from `editor`; logs are in the app's
user-data `logs` folder.

This procedure has been prepared but has not yet been performed on hardware.

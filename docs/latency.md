# Eleven Rack latency investigation

The Control panel's buffer duration is one buffer's frames divided by sample
rate. It is not a measured round-trip latency (RTL).

## REAPER / PipeWire-JACK loopback, 2026-10-09

Main Out L was connected to physical Line Input L, confirmed as capture
channel 7. REAPER recording compensation was disabled and both manual offsets
were zero, confirmed by the user. The sample rate was 48 kHz.
Cross-correlation against an offline-rendered copy of the click source gave:

| PipeWire quantum | Measured timeline delay | REAPER input + output | Difference |
| --- | --- | --- | --- |
| 64 | 9.04 ms | 2 + 2 ms | 5.04 ms |
| 128 | 12.42 ms | 4 + 4 ms | 4.42 ms |
| 256 | 21.60 ms | 8 + 8 ms | 5.60 ms |

The differences are not yet a calibrated constant. Each setting has one take;
repeat runs and a recording with compensation enabled are still needed.
See [recorded metadata](latency-measurements.json).

## Direct ALSA diagnostic

`tools/alsa-loopback.c` uses linked, nonblocking ALSA playback/capture streams
at 48 kHz, six playback channels and eight capture channels. It sends three
-30 dBFS windowed tone bursts only to playback channel 1 and saves capture
channel 7. It never feeds captured audio back to playback. An xrun fails the
test rather than silently recovering. Building requires `libasound2-dev`:

```sh
gcc -Wall -Wextra -O2 tools/alsa-loopback.c -lasound -lm -o /tmp/eleven-alsa-loopback
```

Close audio applications and release PipeWire's device ownership before running
it. Restore the audio services afterwards. Select the actual Rack card number;
`hw:1,0` is only the card used in this session. Keep Rig Input on Guitar and
Main output volume low. Usage:

```sh
/tmp/eleven-alsa-loopback hw:1,0 64 /tmp/eleven-capture.raw
```

The output is mono signed 32-bit native-endian PCM at 48 kHz. On this amd64
host it is little-endian. The log includes actual periods/buffers and snapshots
of `snd_pcm_delay()` in frames. Buffer capacity is not necessarily actual
queue latency.

Three runs (periods 64/128/256, respective buffers 256/512/1024) completed
without xruns. Captured sample offsets were 172, 188, and 199 frames
(3.58, 3.92, and 4.15 ms), stable across the three bursts in each run.
See [direct-test metadata](latency-direct-alsa.json).

These offsets compare the input and output sample timelines, not application
write-to-read wall-clock latency. A linked ALSA start does not prove that the
USB endpoints start at exactly the same sample phase. Consequently, these
values must not be substituted for REAPER RTL or treated as exact converter
latency. Start-phase effects and queue-delay accounting require validation.

## Driver reporting and next steps

The inspected local Linux 7.0 USB PCM driver estimates additional delay from
in-flight USB bytes and USB frame counters (`snd_usb_pcm_delay()` in
`sound/usb/pcm.c`). Our current patches add no Eleven Rack-specific converter
or DSP delay term. This identifies a possible gap, not a validated correction.

Next: repeat linked tests to quantify startup phase variability, inspect
PipeWire/JACK latency ranges for the actual connected ports, and verify REAPER
recording placement with compensation enabled. Establish any device-specific
input/output contribution separately before changing ALSA or PipeWire latency
reporting. No fixed correction has been applied.

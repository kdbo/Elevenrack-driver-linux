# USB packet-capacity fix (development branch)

Branch: `fix/implicit-feedback-packet-capacity`. This is a driver development
fix, with short hardware validation and remaining audio failures. It is not a
stable release or a fix for the machine's firmware/SMI latency.

## Two distinct changes

### Bound implicit-feedback descriptor counts

The upstream ALSA change
[`76a986c980bb502c7688d605ac7a67fd257a9a1b`](https://github.com/torvalds/linux/commit/76a986c980bb502c7688d605ac7a67fd257a9a1b)
records the number of allocated isochronous descriptors per USB request and
clamps both the adopted feedback packet count and the packet-size copy to that
capacity. Payload byte bounds alone do not protect the descriptor array.

For the inspected Rack configuration, playback could allocate four descriptors
while capture supplied eight packet sizes. Several normal audio packets still
fit within the playback byte buffer, so the byte check did not prevent indexing
past the four descriptors. The earlier `hcpriv=0x108` / active-URB warning is
consistent with such corruption, but the exact memory overwrite was not traced.
We therefore describe the proven source-level bounds defect separately from
that plausible explanation of the observed warning.

Preparation backports the upstream change only when absent. A recognized
existing fix is preserved; partial/unfamiliar variants stop the build for review.
This safety change affects implicit-feedback users of the packaged
`snd-usb-audio` module generally, not only Eleven Rack. Distribution sources
outside the private build tree are not modified.

### Align the known Rack playback packet capacity with capture

The generic bound prevents out-of-bounds access, but it can discard part of a
feedback group when playback has fewer allocated packet descriptors. In the
short clamp-only experiment, 88.2/96 kHz with 128/256-frame graph buffers still
showed severe sine waveform mismatch.

The Rack advertises 416 bytes for both endpoint packet ceilings, although its
playback and capture channel counts differ:

- Capture: 416 / (8 channels × 4 bytes) = 13 maximum whole frames per packet.
- Playback as advertised: 416 / (6 × 4) = 17 maximum whole frames per packet.
- Playback with this quirk: 312 / (6 × 4) = 13 maximum frames per packet.

The patch sets the software playback ceiling to 312 bytes, so the allocation
arithmetic uses the same 13-frame ceiling on both directions. It does not
rewrite the hardware descriptor or change the six/eight channel formats.

The adjustment requires all of: USB ID `0dba:b011`, playback, interface 3,
alternate setting 1, endpoint `0x03`, six channels, `datainterval == 0` and
an original 416-byte ceiling. Other devices, capture, and differing layouts
retain their original ceiling. It remains a device-specific development quirk;
its fixed ceiling must be revisited for other formats, intervals or rates.

With both changes, all eight original short sine screenings passed, including
the four high-rate/small-buffer cases that failed with the bound alone. PCM
restart evidence still overrides a passing waveform screening. The subsequent
white-noise tests below expose further remaining failures.

## Validation and limits (2026-10-15)

Host: Dell Latitude 5490, BIOS 1.38.0, kernel `7.0.0-38-generic`.
The test module has srcversion `BFA8216A48C7CCD7D84B7B8`. A clean build from
this branch produces the same srcversion; comparison of all 119 C/header
files against the hardware-tested prototype finds no code differences after
removing comments/whitespace. The revised comments document the now-completed
short hardware tests.

Automated checks:

```sh
python3 tools/test-driver-capacity-backport.py
python3 tools/test-driver-packet-normalization.py
```

The six backport tests cover missing, recognized, partial and unfamiliar fixes.
The normalization test compiles and executes the generated quirk for the known
layout and nine device/direction/layout variations, and rejects an unknown
source function. The complete module also builds against the current headers.
Other kernel/distribution builds remain to be revalidated for this change.

Hardware white-noise tests used this candidate, reporting enabled, configured
playback headroom 256 frames and a physical Main Out L → Line In L loopback:

| Test | Result |
| --- | --- |
| 300 s, 88.2 kHz / 128 frames | No SMI increment or waveform fault; one JACK xrun, so overall FAIL |
| 60 s on each of 24 rate/buffer combinations | 16 PASS, 8 FAIL |
| Six 60 s repeats per buffer on 48 kHz, all six permutations | 128: 6/6 PASS; 256: 5/6; 512: 4/6 |

The last test contains three failed waveforms despite zero JACK xruns. All
three failed captures have SMI activity and fresh timer expiry lateness of
approximately 23–27 ms. On 2026-10-16 those SMIs were traced to Dell
keyboard-backlight writes from GNOME's idle dimming; see
[firmware pauses](system-pauses.md) and the open 44.1 kHz issue below. The 128-frame captures had no SMI events, so their
6/6 result does not establish better tolerance of firmware pauses. Likewise,
256 frames is not intrinsically broken: five repeated captures passed.

The 24-profile matrix also includes a waveform/PCM failure without SMI activity
in that trace window. Not every remaining failure has been attributed to
firmware. SMI counts do not measure time in SMM or identify a firmware handler;
perf interval timing uses an approximate pre-exec realtime anchor. No claim is
made that the USB fix prevents or repairs firmware pauses, all xruns, every
restart, or every analog-path residual mismatch.

One fixed analog filter response is validated on separate windows and then used
without adapting across faults. Delay steps, dense residual faults, PCM
restarts and xruns remain failures. Large residual-block counts after a lasting
change do not represent independent glitches. Successful short profiles are
screenings, not a long-term stability guarantee. The full multi-signal
1/5/15/30-minute regression suite on this candidate is still pending.

Compact machine-readable measurements are in
[packet-capacity-validation.json](packet-capacity-validation.json). Original raw
recordings, graphs, timestamps and traces remain locally under
`build/latency/usb-errors-20261015/`, in `noise-post-bios-1.38.0-171912`,
`white-matrix-post-bios-1.38.0-172801` and
`white-balanced-48k-post-bios-1.38.0-200753`.

## Investigation: delay steps at 44.1 kHz (2026-10-16)

Superseded by the resolution below. Both candidates in this section were
ruled out: neither capture errors nor PipeWire resyncs occurred at any step.

With GNOME idle dimming disabled, no SMIs occurred in any regression run that
day. One failure mode remains. With the same module (srcversion
`BFA8216A48C7CCD7D84B7B8`), 3 of 10 five-minute 44.1 kHz / 128-frame
white-noise runs failed:

| Run | Delay step | Time into recording |
| --- | --- | --- |
| `nodim-white-20261016-080517` | +34 frames | 60.6 s |
| `rate441-repeat-20261016-084608`, cycle 1 | +34 frames | 13.4 s |
| `rate441-editor-20261016-090624`, cycle 1 | +33 frames | 3.1 s |

Each failure has the same signature:

- The loopback delay increases once and stays there; about 35 ms of samples
  around the step fail the residual check.
- At the same moment, the playback latency reported by PipeWire rises by
  8–10 frames and does not return.
- There is no JACK xrun, PCM restart, callback stall, SMI or kernel message.
- All steps fell within the first minute, while the reported playback/capture
  latencies are still settling (about 60–90 s in every run). After that point,
  about 20 minutes of settled recording contained no step.
- No step has been seen at 48 kHz.

Ruled out:

- **SMIs:** the counter did not change.
- **The Editor and its MIDI traffic:** MIDI bytes were logged every 100 ms;
  traffic occurred only during setup, about 12 s before the closest step.
- **A WebKit process crash:** one coincided with the first failure, but not
  with the others.

### Candidate 1: implicit-feedback zero-size packets (driver)

In `sound/usb/endpoint.c`, each playback URB copies the packet layout of a
received capture URB:

- A capture packet with a non-zero status, such as a missed microframe, makes
  the matching playback packet size 0.
- A capture URB without any valid bytes produces no playback URB at all. This
  avoids 0-byte OUT URBs, which stop M-Audio devices.

Either way, playback silently sends fewer frames than the device consumes, and
the loopback delay grows. Nothing reports an xrun. At 44.1 kHz high-speed
packets alternate between 5 and 6 frames, so six packets total 33 or 34 frames,
the measured step sizes. At 48 kHz six packets would be 36 frames.

Other implementations derive playback packet sizes from a history of
received capture packets, rather than pairing each playback URB with one
capture URB. With a history, a failed capture packet does not leave a hole
in playback, because a plausible size is always available.

### Candidate 2: PipeWire follower resync (backend)

The playback node (`hw:1,0p`) follows the capture clock without resampling
(`matching:0`). When its timing error exceeds `max_resync`
(`min(quantum + headroom, max_error)`), `alsa-pcm.c` rewinds or inserts
silence. This also produces a step without an xrun. It is logged only at
INFO level, so the default journal shows nothing.

With `PIPEWIRE_DEBUG=2,spa.alsa:3`, three 44.1 kHz / 128 runs showed one
resync per stream start, during warmup, and none during recording. Those runs
had no step, so this neither confirms nor excludes the candidate.

### Distinguishing the two

Enable both logs, then run 44.1 kHz / 128 tests until a step occurs:

```sh
systemctl --user set-environment PIPEWIRE_DEBUG="2,spa.alsa:3"
echo 'module snd_usb_audio format "frame %d active" +pt' | sudo tee /proc/dynamic_debug/control
```

The second command enables the existing rate-limited `retire_capture_urb`
message for capture packets with a non-zero status. It resets on reboot or
module reload. Afterwards, disable both:

```sh
systemctl --user unset-environment PIPEWIRE_DEBUG
echo 'module snd_usb_audio format "frame %d active" -p' | sudo tee /proc/dynamic_debug/control
```

At the step time, compare the kernel log (`journalctl -k`) and the user
journal (`journalctl --user | grep resync`):

| Evidence at the step | Conclusion |
| --- | --- |
| `frame N active: <status>` lines | Candidate 1: driver implicit-feedback path |
| `follower … resync` line | Candidate 2: PipeWire backend |
| Neither | Below both, for example the Rack's firmware; trace the URBs |

### Fix direction if candidate 1 is confirmed

Make this a device-specific quirk for `0dba:b011`, in the same style as the
packet-capacity normalization:

- When a capture packet fails, take its playback size from recent valid
  capture packets instead of 0. The frame count then follows the device clock.
- When an entire capture URB fails, still produce a playback URB with
  history-based sizes rather than skipping it.

The aim is to reproduce the benefit of a packet-size history without
changing the generic implicit-feedback design that other devices depend on.

Before relying on this, establish:

1. Whether the Rack itself tolerates zero-length OUT packets. The M-Audio
   behaviour shows that devices differ.
2. The error status the capture packets actually report.
3. That the fix removes the 44.1 kHz steps without new faults at 48, 88.2 and
   96 kHz.

Upstream ALSA already has `QUIRK_FLAG_IFB_SILENCE_ON_EMPTY` for devices that
need an OUT packet even when the whole capture URB failed. That quirk still
sends zero-size packets, so it would not prevent the frame loss.

## Resolution: playback ring underruns and a 2 ms lead (2026-10-17)

An xHCI event trace (`xhci_handle_event`, filtered to completion codes other
than Success and Short Packet) found the cause. Every delay step was preceded
by a `Ring Underrun` on the Rack's playback endpoint (EP 0x03): 13 of 13 steps
in the two-minute 24-profile matrices, at all four sample rates. The steps
were 25-81 frames, roughly the time the ring stayed empty.

Upstream implicit feedback submits no playback until capture URBs return.
Each capture completion then releases one playback URB of 0.5-1 ms, so the
OUT ring holds very little. When a capture completion is handled late, the
ring runs empty and the next playback is scheduled later, with no xrun or log
message. Keeping the CPU out of deep C-states (`cpu_dma_latency` = 0) did not
prevent it.

`QUIRK_FLAG_PLAYBACK_FIRST` (0x10) removed the underruns but queued every URB,
adding 2-14 ms of latency. The driver now queues a bounded lead instead:
`eleven_playback_lead_ms`, 2 ms by default, for `0dba:b011` only. It is
writable at runtime and read at each stream start. 0 restores upstream
behaviour, for example with `options snd_usb_audio eleven_playback_lead_ms=0`.

| Two-minute matrix, 24 profiles | Failures | Playback underruns | Extra latency |
| --- | --- | --- | --- |
| No lead | 7 | 13 | - |
| `PLAYBACK_FIRST` | 4 | 0 | 2-14 ms |
| 2 ms lead | 1 | 0 | 0.3-1.4 ms |

Part of the lead does not add latency: PipeWire sees the queued audio and
keeps correspondingly less in its own buffer. REAPER's latency compensation
stays correct. The automated REAPER click test (`tools/reaper-click-test.py`)
places recordings within about +/-0.2 ms of the played click after the
correction retune in `config/52-eleven-rack-latency.conf`; those corrections
were measured with the 2 ms lead.

Remaining observations:

- Rare small steps of about one USB packet (5-7 samples) without any USB,
  ALSA or PipeWire event; the cause is not visible from the host.
- Rare early steps at 88.2/96 kHz without an underrun (3 in 48 runs with a
  lead, none in 24 without). Too few to attribute.
- Occasional underruns still occur (1 in about 25 click-test runs, 1 in 4.5
  nightly hours), mostly absorbed by the lead without a step.
- Only the Ubuntu 7.0 source has been patched and built with the lead. Other
  kernel series must pass the compatibility builds before a release.

## Local DKMS trial

The development install uses the separate local DKMS version
`0.1.2~beta12+packetfix1`. The repository `VERSION` and released beta12 package
identity are unchanged. The original beta12 DKMS source is retained for rollback.
The current-kernel trial is not an assertion that other kernels have been
successfully built or tested. Local installation evidence is retained in
`build/latency/packet-capacity-branch-validation/installation.json`.

To return the current kernel to the original version, close audio clients and
stop PipeWire/WirePlumber before unloading the module, then run:

```sh
sudo modprobe -r snd_usb_audio
sudo dkms remove -m eleven-rack -v '0.1.2~beta12+packetfix1' --all
sudo dkms install -m eleven-rack -v '0.1.2~beta12' -k "$(uname -r)" --force
sudo update-initramfs -u -k "$(uname -r)"
sudo modprobe snd_usb_audio
```

Restart the previously active user audio services afterwards and verify the
hardware rate and PipeWire settings. These commands change the installed driver;
keep work saved and the local trial installation log available when rolling back.

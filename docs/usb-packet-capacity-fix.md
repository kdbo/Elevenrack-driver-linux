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
approximately 23–27 ms. The 128-frame captures had no SMI events, so their
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

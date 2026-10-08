# Investigation, 2026-10-08

## Observed on the connected hardware

- USB vendor/product: `0dba:b011`; device revision `20.01`; high speed.
- Running ALSA version reports kernel `7.0.0-38-generic`.
- ALSA card 1 is Eleven Rack; `midi0` reports two inputs and two outputs.
- `/proc/asound/pcm` contains only the built-in sound card. Eleven Rack has no
  PCM nodes or stream description. MIDI transfer itself has not been tested.
- Interface 0 is firmware update; interface 1 is vendor-specific control,
  subclass 1, protocol `0x20`, with UAC2-shaped class-specific descriptors.
- Interface 2 is standard USB MIDI.
- Interface 3, alt 1: six-channel playback, endpoint `0x03`, asynchronous isochronous.
- Interface 4, alt 1: eight-channel capture, endpoint `0x83`, asynchronous
  isochronous with implicit-feedback usage.
- Both audio endpoints advertise 416-byte maximum packets and interval 1.
- Format descriptors advertise four-byte samples with 32-bit resolution.
- Descriptor inspection succeeded from cached descriptors; opening the USB
  device failed due to permissions, so no live clock-control requests were made.

## Comparison with existing implementations

[Matt Housley's MIT-licensed macOS driver](https://github.com/Matt-Housley/eleven-rack-driver)
uses interfaces 3 and 4 at alternate setting 1. Its `erengine.c` treats capture
as eight interleaved little-endian 32-bit words per audio frame and describes
24-bit audio left-justified in those words. It sends six interleaved 32-bit
playback samples per frame. This supports trying ALSA's S32_LE transport.
The advertised bit resolution and actual effective precision differ; hardware
validation is needed before refining format metadata.

The engine uses UAC2-style interface control requests:

| Operation | Request type | Request | Value | Index | Payload |
| --- | --- | --- | --- | --- | --- |
| Select clock | `0x21` | `0x01` | `0x0100` | `0x8001` | 1 byte: 1 internal, 2 AES, 3 S/PDIF |
| Set internal rate | `0x21` | `0x01` | `0x0100` | `0x8101` | 4-byte little-endian Hz |
| Read internal rate | `0xa1` | `0x01` | `0x0100` | `0x8101` | 4 bytes |

The reference lists 44100, 48000, 88200, and 96000 Hz. Its playback scheduler
uses nominal rate pacing; that is not evidence that capture-based feedback has
been tested on Linux.

Linux upstream's `sound/usb/quirks-table.h` has Digidesign entries but no
`0dba:b011` entry. Standard stream parsing already accepts vendor-class streaming
interfaces with UAC2 protocol. The generic UAC2 implicit-feedback path in
`implicit.c` requires audio class, so the Eleven Rack needs an explicit pairing.
`helper.c` falls back to the first control interface if no stream/control link
exists; probing interface 1 first gives the intended control interface.

Sources: [quirk table](https://github.com/torvalds/linux/blob/master/sound/usb/quirks-table.h),
[stream parser](https://github.com/torvalds/linux/blob/master/sound/usb/stream.c),
[feedback](https://github.com/torvalds/linux/blob/master/sound/usb/implicit.c),
[probe](https://github.com/torvalds/linux/blob/master/sound/usb/card.c),
[clock handling](https://github.com/torvalds/linux/blob/master/sound/usb/clock.c).

## First experimental patch

1. Match the vendor-class interfaces and restrict the quirk to control interface 1.
2. Use a composite quirk to retain standard MIDI and parse audio interfaces 3/4.
3. Pair playback with capture endpoint `0x83` on interface 4 for implicit feedback.

The control interface is claimed without creating a mixer in this first patch.
ALSA clock handling still reads its descriptors and uses its controls. Mixer
controls and channel labels are follow-up work after basic streaming succeeds.

This assumes the device supports UAC2 rate-range and clock-validity queries
used by ALSA. The reference driver's SET_CUR/GET_CUR implementation does not
prove GET_RANGE works. If enumeration fails there, capture control traffic and
add a narrowly scoped rate/clock quirk rather than inventing a full USB driver.

## Validation and next steps

The initial patch was checked against upstream files. After dependencies were
installed, it was regenerated against Ubuntu source package `7.0.0-38.38` and
compiled successfully using GCC 15.2.0 and the installed `7.0.0-38-generic`
headers. Module vermagic matches the running kernel and its USB aliases include
the Eleven Rack. BTF generation was skipped because vmlinux is unavailable;
compilation and module symbol checks passed. Secure Boot is disabled.

The module has not been loaded: the attempted temporary load stopped at sudo
authentication before executing any module commands. Run
`sudo bash tools/load-experimental.sh` locally to proceed. Audio remains untested.

Obtain the exact Ubuntu source matching the running kernel and install the
compiler/build dependencies. Check/port the patch there and build the USB audio
module through the distribution's kernel build workflow. Keep the existing
module available for rollback; module signing may be required by Secure Boot.

After loading the experimental module and reconnecting:

1. Inspect kernel logs and `/proc/asound/card*/stream*`; confirm 6 output and
   8 input channels and the supported rates.
2. Record first at 48 kHz and verify channel order and clean samples.
3. Test playback at low output level, then simultaneous capture/playback.
4. Test all four rates, playback-only feedback, sustained streaming, stop/start,
   and unplug/reconnect. Measure xruns and latency.
5. Confirm both MIDI ports still transfer correctly.

Passing patch application is not evidence of working audio. Hardware results
must determine whether additional initialization or clock quirks are needed.

## First hardware probe

The user loaded the first module. Its loaded source version matches the build.
Kernel logs show both streams were rejected at `parse_audio_format_rates_v2v3()`:
"unable to retrieve number of sample rates (clock 129)". This means control
interface and clock-source discovery progressed, but the initial GET_RANGE
request failed. There is no PCM device yet.

Patch 0002 adds a fallback in the existing rate-query failure path for this
specific USB ID: 44100, 48000, 88200, and 96000 Hz, as used by the reference
driver. It retains normal UAC2 clock controls and only bypasses the failed
range query. These rates still need hardware streaming validation.

## Second hardware probe

The rate fallback module loaded successfully (source version
`5D4C27113F477D293F2A653`). The loader printed PCM status too early; a subsequent
read shows `01-00: USB Audio` with playback and capture. `stream0` confirms
S32_LE, six output channels, eight input channels, all four rates, and capture
endpoint 0x83 as playback implicit feedback.

Kernel logs show repeated failed endpoint PITCH enable requests, including
when userspace tries opening capture. Patch 0003 clears the pitch-control
attribute for this USB ID; clock frequency control remains enabled. Streaming
is still unverified. The loader now waits briefly for PCM registration.

## First recording, 48 kHz

After loading patch 0003, `arecord` produced a complete 5-second, 8-channel
S32_LE WAV: 240000 frames at 48000 Hz. Channels 3/4 have strong signal
(peak -2.8 dBFS, RMS -14.0 dBFS); channel 1 peaks at -19.0 dBFS. These levels
are consistent with processed rig stereo on 3/4 and dry guitar on 1, using the
reference mapping. Channels 5/6 are silent; other channels contain low-level
signal/noise. This verifies short capture with signal, not audible fidelity or
long-term timing. No clipping was observed in the peak measurements.

The recent journal contains a USB disconnect/reconnect at 15:56:42 with an URB
submission error during disconnect, followed by successful re-enumeration.
This alone does not establish a streaming fault. Earlier pitch errors precede
the updated module. Sustained recording and playback remain to be tested.

A stereo extraction is at `/tmp/eleven-rig-stereo.wav`. A 6-channel playback
test is at `build/eleven-main-out-test.wav`: rig channels copied to outputs 1/2
with amplitude divided by four; outputs 3–6 are silent. Play with
`aplay -D hw:CARD=Rack,DEV=0 build/eleven-main-out-test.wav` and verify sound
at the main/headphone output. This test file is generated from the user's
recording and is excluded from version control with the build directory.

## First audible playback, 48 kHz

The user confirmed hearing the prepared recording through the Eleven Rack.
This establishes basic capture and audible playback at 48 kHz with the three
patches. It does not establish simultaneous duplex operation, sustained
stability, latency, or the remaining sample rates. The module remains a
temporary load; the installed distribution module is unchanged.

## Sample-rate control fix

Direct userspace USB controls failed with EBUSY while ALSA owned the control
interface. The rate utility now uses an exact-rate ALSA hardware capture and
discards the samples. One-second capture/configuration completed successfully
at 44100, 48000, 88200, and 96000 Hz; the device was returned to 48000 Hz.
This validates the rate-change path and short capture at those rates, not
audible fidelity or sustained duplex performance. The GUI no longer requests
administrator authentication for sample-rate selection.

## ALSA clock selector

Patch 0004 enables standard mixer parsing on control interface 1, maps unit
0x80 to `Eleven Rack Clock Source`, and gives its selections the names
Internal, AES, and S/PDIF. Proprietary units 0x20/0x40/0x41 are excluded.
The module compiled successfully. The settings utility and GUI now use
amixer for clock source/status, without direct userspace USB requests or
administrator authentication. Reloading and hardware validation are pending.

The user loaded patch 0004; loaded module version matches the build and ALSA
exposes the writable three-choice clock selector and external validity controls.
Internal reads successfully. S/PDIF writes through both numeric and named
amixer selections still read back Internal. S/PDIF validity is off. This does
not establish whether missing external signal explains rejection. The Rack
was restored to Internal after tests. The generic selector callback discards
write errors; patch 0005 reports those errors for this USB ID. Further hardware
validation is required. Clock-lock queries were corrected to use iface=CARD.

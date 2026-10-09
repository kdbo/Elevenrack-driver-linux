# Linux editor investigation

Reviewed on 2026-10-09. The editor remains separate from the audio-driver
package. The first Linux port now lives in [editor/](../editor/README.md).

## Upstream comparison

| Project | Reviewed revision | Relevant components |
| --- | --- | --- |
| [CharlesWardick/Eleven-Edit](https://github.com/CharlesWardick/Eleven-Edit) | `64516e2ae86188faf09aaae80805c0e6a0618a1e` | v1.1.0 Electron editor, Java MIDI bridge, optional audio helper |
| [damielolar-CODE/Eleven-Edit](https://github.com/damielolar-CODE/Eleven-Edit) | `3b543c89eac5418b12721cd72445f2c2ef6fcc5c` | v2.0.0 macOS fork, Studio interface, native CoreMIDI bridge |

The macOS fork is the proposed starting point. Its UI and rig/preset logic
already communicate with a replaceable MIDI bridge. Its `NOTICE` credits
Charles Wardick, Damilola Olalere (MrDees), and Guillaume Schmid's earlier
ElevenHack protocol work. Preserve upstream `LICENSE` and `NOTICE` when
importing code; our own MIT copyright does not replace theirs.

Upstream Charles Wardick's `LICENSING.md` identifies the main editor as MIT
and `audio-helper.js` as GPL-3.0-or-later. The reviewed macOS fork does not
include that helper in its package file list and has no audify dependency.
Any imported components and assets still need their notices retained and
reviewed. The macOS driver and native meter helper are not required for the
first Linux editor and should not be imported as Linux implementations.

## Linux work needed

1. Preserve the renderer's WebSocket contract on loopback port 57121.
   Commands are `list_ports`, `connect`, `disconnect`, and `send` (hex MIDI).
   Replies/events include `ports`, `connected`, `disconnected`, `midi_in`,
   `error`, and `log`. Port indexes must refer to one combined list, with
   explicit input/output direction, matching the renderer's expectations.
2. Implement and test a Linux MIDI bridge. ALSA MIDI via a suitable transport
   such as RtMidi is a candidate, not yet a selected or validated dependency.
   Handle complete SysEx assembly, CC/program changes, disconnects, and
   shutdown. Keep the same JSON contract so rig logic can be reused.
3. Add an explicit Linux startup path to `main.js`. Currently only macOS
   selects the native bridge; Linux falls into the Java/Windows path.
   Audit Windows process cleanup, Java version checks, platform messages,
   macOS meter integration, and the macOS `afterPack` hook.
4. Validate device discovery and firmware identity on physical Linux hardware,
   followed by read-only rig name, chain and parameter synchronization.
   The fork accepts firmware builds `0157` and `0153`; preserve its gate.
5. Test a reversible parameter change with readback, then rig navigation and
   disk `.tfx` handling. Validate slot writes and backup/restore separately.
6. Package the editor separately, with Linux assets, dependencies, preserved
   upstream licensing, and its own release/build checks. The reviewed checkout
   cannot yet be described as a working Linux editor.

The driver panel also accesses the Rack's MIDI ports. Test concurrent access
and reply ownership explicitly; the unresolved VM Rig Input readback is not
evidence that the editor bridge will work correctly there.

## Live UI tuner

The UI now shows the hardware tuner note and a relative tuning needle.
Charles Wardick's ElevenEdit Technical Reference, section LIVE TUNER DATA,
documents the read request `F0 13 0B 0F 01 42 F7` and reply
`F0 13 0B 0F 12 42 [note] [tune] F7`. The note packs octave/chromatic
index in its nibbles; tune is centered at 0x40. The documented idle reply
is note=0/tune=0x40 (ambiguous with a tuned C0).

Polling runs at 15 Hz only while the confirmed hardware tuner is on and
MIDI is connected. Turning off, changing presets or disconnecting stops it.
No audio capture or additional pitch algorithm is needed. The hardware's
reference setting applies; no cents conversion is claimed without a verified
calibration. Decoder/lifecycle tests pass. Live guitar tuning remains to be
verified on hardware.

## Initial Linux implementation

The macOS UI has been imported with upstream MIT license and notices. Linux
startup now launches a Python ALSA/RtMidi bridge, bypasses Windows process
cleanup and Java checks, and selects the Rig MIDI ports by direction/name.
The bridge implements the existing WebSocket contract, session ownership,
input callbacks, port-change notifications, and graceful shutdown.

The physical hardware probe returned firmware build `0157` and Rig Input
`guitar`. The running Electron renderer reported `bridgeReady`,
`bridgeMidiReady`, and `firmwareOk` all true, received a ten-block effect chain,
and identified amp model `97 RB-01b Blue`. This validates read-only startup
synchronization on the Ubuntu 26.04 host. It does not validate editing, saving,
backup/restore, audio metering, or the requested pitch display.

## Original investigation limits

Both source trees and their bridge/startup code were inspected. No editor was
launched, built for Linux, or tested against the device. Node/npm are not
currently available on the development host's PATH. The next concrete milestone
is a Linux bridge plus successful read-only startup synchronization, before
adding tuner metering or audio monitoring.

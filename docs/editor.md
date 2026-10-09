# Linux editor investigation

Reviewed on 2026-10-09. The editor remains separate from the audio-driver
package; no upstream editor code has been imported into this repository yet.

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

## Requested UI tuner (later)

Clicking Tuner should eventually show a software tuner in the editor UI,
including note, cents offset, and tuning indication. This is deferred until
the basic editor works on Linux.

The reviewed fork's `handleTunerBroadcast()` and `handleTunerCC()` handle
tuner enabled/disabled status, not measured pitch. Do not assume those events
carry note or cents data. First investigate whether the device exposes pitch
telemetry. Otherwise implement software pitch detection from a verified dry
guitar capture channel, with separate audio access and tuning-mode tests.
The hardware tuner may change routing, so confirm that the required signal
remains available when it is enabled.

## Current validation limits

Both source trees and their bridge/startup code were inspected. No editor was
launched, built for Linux, or tested against the device. Node/npm are not
currently available on the development host's PATH. The next concrete milestone
is a Linux bridge plus successful read-only startup synchronization, before
adding tuner metering or audio monitoring.

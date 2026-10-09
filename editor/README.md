# Eleven Rack Editor for Linux

Initial Linux port of Charles Wardick's Eleven Edit, based on Damilola Olalere's
macOS fork at `3b543c89eac5418b12721cd72445f2c2ef6fcc5c`.
Original MIT license and attribution are preserved in [LICENSE](LICENSE) and
[NOTICE](NOTICE). Linux integration: Koen de Boevé.

## Run from source

On Ubuntu 24.04 or newer:

```sh
sudo apt install nodejs npm python3-rtmidi python3-websockets
cd editor
npm ci
npm start
```

The launcher clears IDE environment settings that otherwise cause Electron
to run as Node or use incompatible GTK schemas. No Java or macOS driver is
used. The Python bridge uses ALSA sequencer MIDI and listens only on loopback
port 57121. Close other editor instances before launching this one.

Input/output selectors default to the Eleven Rack Rig ports when unambiguous.
The firmware gate is retained (builds `0157` and `0153`). The control panel
also uses MIDI; concurrent control-panel/editor access is not yet validated.

## Build and check

```sh
npm test
npm run build:linux
```

The editor `.deb` appears under `editor/dist/`, separately from the DKMS driver
package. It declares Python MIDI/WebSocket dependencies. It does not install
or replace the kernel driver. The bundled UserManual.txt describes the current Linux interface, tuner,
reference-frequency control and output mutes, and preserves upstream credits.

To check MIDI without launching the UI:

```sh
python3 bridge-linux/bridge.py --list
python3 bridge-linux/probe.py
```

The probe sends identity and Rig Input read requests only and releases its
ports when done. It must run while the editor is closed.

## Validation

On 2026-10-09, physical Eleven Rack tests on the Ubuntu 26.04 development host
confirmed MIDI port enumeration, a firmware `0157` identity reply, and Rig Input
readback (`guitar`). The Electron UI connected, passed its firmware check, and
loaded the current rig's ten-block effect chain and `97 RB-01b Blue` amp model.
Six bridge regression tests cover port mapping, stale indexes, session ownership,
message validation, sending, and cleanup.

Parameter changes, disk presets, slot writes, backup/restore, unplug/reconnect,
Ubuntu 24.04 editor installation, and audio meters remain unvalidated. The UI
tuner now displays the hardware's live note and relative tuning needle using
CMD 0x42 at 15 Hz while the hardware tuner is active. It stops on tuner-off,
patch changes, or disconnect. The needle is not calibrated in cents; the
hardware reference setting applies. The documented idle value cannot be
distinguished from an exactly tuned B-flat0. Decoder and lifecycle tests pass;
live tuning with a guitar still needs verification. Protocol credit:
Charles Wardick's ElevenEdit Technical Reference (live tuner section).

The tuner also has an `A=… Hz` reference input and ±1 Hz buttons. Two original
editor MIDI captures established CMD 0x41 reference writes and the 438–440 Hz
mapping. A reference reply confirms the displayed value. If no initial reply
arrives, enter a desired value explicitly; the editor does not assume A=440.
The user confirmed on 2026-10-09 that reference changes from the Linux editor
are applied by the Rack. See
[capture analysis](../docs/tuner-reference-capture.md).

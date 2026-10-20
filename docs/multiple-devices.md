# Two connected Eleven Racks

The driver control panel and Linux editor support choosing one active Rack while
two units remain connected. They do not combine the units or synchronize their
hardware clocks. One editor bridge currently owns one active MIDI pair; two
independent editor windows editing different Racks concurrently are not supported.

## Device selection

The visible names are **Eleven Rack 1** and **Eleven Rack 2**, corresponding to ALSA's internal
`Rack` and `Rack_1` names. System sound settings distinguish `Eleven Rack 1 Inputs/Outputs` from `Eleven Rack 2 Inputs/Outputs`.
JACK nicknames remain unchanged for existing routing scripts.
The USB location is shown alongside the name in the device selectors. ALSA card
numbers/names can change after reconnecting; saved selections use physical USB
location instead. Moving a Rack to another USB port requires selecting it again.
No unique USB serial was exposed by either of the two units tested on this host.
The friendly number alone is therefore not a permanent identity of a physical unit.

The driver UI and editor show their Device selector only with multiple connected
Racks. With a single Rack, selection is automatic and the selector is hidden. Clock source, hardware status, monitoring,
Rig Input, firmware cache and meters follow that choice. Replies from an earlier
selection are discarded after switching. If only one Rack remains connected, it is selected automatically after pending
operations finish. The editor reloads before using that unit. With two units and no
selection, controls wait for an explicit choice. With one unit, it is selected
automatically.

Sample rate and buffer controls explicitly refer to the **shared PipeWire session**.
They are not independent per-Rack graph settings. Changing session rate can affect
other devices. Hardware clock source and monitoring controls address the selected
ALSA card. Each Rack's capture/playback pair has its own clock name in the provided
WirePlumber configuration: `api.alsa.Rack` versus `api.alsa.Rack_1`.

## Editor

On Linux, the bridge maps ALSA sequencer clients to their hardware cards and USB
locations. The device selector picks a complete Rig MIDI input/output pair. Mixed
pairs from different Racks are rejected by the bridge. When multiple units are
present on first startup, a device-choice dialog is available while the splash is
still visible. A saved physical identity is preferred over changing port indices.
Adding another Rack does not reconnect the currently selected unit.

Switching the editor device disconnects the old MIDI pair and reloads the renderer.
This discards old rig state, patch-name caches, timers and pending knob writes,
then reads the newly selected Rack. Save any unsaved edits before switching.
The native driver UI's shared Rig Input requests include a device identity; a
request for another Rack is never forwarded through the editor's connected unit.

## USB handling with two Racks

Two Racks on the same USB host controller share its interrupt, so delays in
the kernel's USB handling can affect both at the same moment. Each Rack counts
such events in its own `/proc/asound/<card>/eleven_stats`. The recommended
interrupt and `ksoftirqd` settings protect both; see
[clicks and shifted latency from delayed USB handling](usb-completion-delays.md#two-racks).

## Command line

List devices and select explicitly when more than one unit is connected:

```bash
python3 tools/eleven-rack-settings.py devices
python3 tools/eleven-rack-settings.py --device Rack status
python3 tools/eleven-rack-settings.py --device Rack_1 monitor
```

`--device` also accepts an ALSA card number or the full `usb:…` identity from the
list. For scripts, set `ELEVEN_RACK_DEVICE` to that physical identity so a card
renumbering cannot silently select another unit. Existing regression scripts that
assume one Rack need explicit selection and routing before testing two units.
The display names contain spaces; CLI selectors remain the internal IDs above.

## Validation

Automated tests cover ambiguous selection, missing devices, per-device caches,
USB identity independent of card number, cross-device MIDI pair rejection,
wrong-device shared Rig Input requests, and frontend pair grouping. The existing
bridge suite remains covered. Hardware checks with both connected units confirmed
separate identity replies, 48 kHz status and firmware 2.0.1 / build 0157.

Source UI smoke checks are recorded under `build/multi-device-*-validation.json`.
Physical unplug/replug and concurrent digital audio/clock tests remain separate
hardware validation tasks. The changes require updating/relaunching the installed
control panel/editor; WirePlumber configuration changes take effect after the
configuration is installed and the audio session is restarted.

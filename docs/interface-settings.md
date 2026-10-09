# Channel names and interface settings

The installed WirePlumber configuration exposes all 8 inputs and 6 outputs
in hardware order. Port names were verified in the running PipeWire graph:
Guitar In, Mic In, Eleven Rig L/R, Digital In L/R, Line In L/R; Main Out L/R,
Re-Amp L/R, Digital Out L/R. JACK/PipeWire routing applications can display
these names. Apps that open ALSA directly may still display channel numbers.
This replaces the misleading surround profile for this device only.

During the physical loopback check, Line Input L was confirmed on capture
channel 7, previously mislabeled Digital In L. The last two pairs have therefore
been relabeled: Digital In L/R on 5/6, Line In L/R on 7/8. Channel 7 is
hardware-confirmed; the remaining members of these pairs still need separate
physical validation. This changes display names, not audio stream order or
MIDI Rig Input values. Existing installations need the updated configuration
and an audio-session restart before applications show the corrected names.

The configuration is `config/51-eleven-rack.conf`, installed at
`~/.config/wireplumber/wireplumber.conf.d/51-eleven-rack.conf`. Restart
WirePlumber after changing it. Removing the installed file and restarting
WirePlumber restores automatic profile handling.

## Command-line controls

For the orange-and-black desktop panel, run
`python3 tools/eleven-rack-settings.py gui`. It uses native GTK 3 and offers the
channel table, connection status, clock status/source, internal rate, and Rig
Input. Controls use ALSA with normal user permissions. The panel requires
python3-gi and gir1.2-gtk-3.0.
Hardware monitoring is visibly unavailable until its command is identified.
Controls execute in a background thread so hardware reads
do not freeze the panel. Dropdown selections apply immediately. Hardware
readback updates do not trigger writes. Controls are disabled during requests;
failed changes revert to the last confirmed value, or blank if unknown.
The Buffer size dropdown applies PipeWire's session-wide force-quantum setting
immediately: Automatic or 64–2048 samples. It shows milliseconds per buffer at
the current PipeWire rate, which excludes other round-trip latency. Automatic
removes the override. Changes affect the shared graph, including system audio;
this control applies to REAPER running through PipeWire/JACK, not direct ALSA.
Buffer metadata is refreshed every two seconds to reflect external changes.
The dot beside Clock source is green when the selected hardware clock is
locked, gray when unlocked or unknown. Its tooltip explains the state.
Status is read on opening and after setting changes. The panel subscribes to
ALSA control events through `amixer events`, refreshing on clock events.
There is no periodic clock polling or Read Status button. Hardware lock
transitions can only trigger refresh if the device/driver emits an ALSA event;
the Rack's clock notifications have not yet been verified. USB reconnects are
still checked every three seconds and re-establish the subscription.
The actual ALSA PCM rate is checked from hw_params every 250 ms while the
panel is idle. A rate change made by Reaper updates the dropdown without
triggering a write. This reflects the device stream rate; a DAW project rate
resampled by PipeWire can differ. No PCM rate control events are emitted by
the current driver, so these rate updates use a lightweight read rather than
an ALSA event subscription.
Input and output channel lists are compact, independently collapsible sections,
collapsed initially to keep the interface settings visible.

Run from the repository:

```bash
python3 tools/eleven-rack-settings.py channels
python3 tools/eleven-rack-settings.py rig-input
python3 tools/eleven-rack-settings.py rig-input reamp
python3 tools/eleven-rack-settings.py rig-input guitar
python3 tools/eleven-rack-settings.py status
python3 tools/eleven-rack-settings.py clock internal
python3 tools/eleven-rack-settings.py clock aes
python3 tools/eleven-rack-settings.py clock spdif
python3 tools/eleven-rack-settings.py rate 48000
```

When the updated editor is connected to the Rack, Control sends Rig Input
requests through the editor's local MIDI bridge and verifies the hardware reply.
Without an active editor connection, it uses the direct ALSA MIDI route.
Both applications must be updated for shared access; restart the editor after
updating. An older running bridge reports an error rather than being bypassed.

Rig Input uses ALSA USB MIDI and accepts only the reference driver's known
values: guitar, reamp, mic, line-l, line-r, line-lr, digital-l, digital-r,
digital-lr. Reading the current Rig Input was hardware tested and returned
guitar. Writes include a readback but have not yet been hardware tested here.

Patch 0004 creates the standard ALSA mixer for interface 1 and names the
clock selector `Eleven Rack Clock Source`, with Internal, AES, and S/PDIF
choices. Proprietary routing units are excluded from mixer probing. The
utility uses amixer to read/write the selector and verifies its readback.
Clock validity is read from ALSA's read-only clock-source controls. Loading
the rebuilt module is required; this control has not yet been hardware tested.

Stop audio apps before changing the clock or rate. The utility refuses writes
while ALSA reports a running stream. An external clock needs a valid AES or
S/PDIF input. The rate command sets the internal hardware clock while idle;
ALSA and PipeWire applications choose their streaming rate when opening the
device, so this is not a persistent sample-rate preference. Select the desired
rate in your DAW for recording/playback. Status reports the clock selection
and lock state where available; ALSA's standard mixer does not expose the
internal clock frequency as a readable control.

The original direct USB sample-rate control returned EBUSY (Errno 16) because
ALSA owns interface 1. Rate selection now opens an exact-rate ALSA hardware
capture for one second, discarding its samples. ALSA handles clock controls
inside the driver; no root authentication or USB detach is needed. An active
capture stream prevents the change. Clock source/status now use the kernel's
ALSA mixer path rather than userspace USB controls.

Sources: [Eleven Rack reference driver](https://github.com/Matt-Housley/eleven-rack-driver),
[PipeWire channel names](https://pipewire.pages.freedesktop.org/pipewire/group__pw__keys.html),
[WirePlumber ALSA rules](https://pipewire.pages.freedesktop.org/wireplumber/daemon/configuration/alsa.html).

## Required: hardware monitoring toggle

The monitoring selector should expose two modes: **Hardware** and **DAW Only**.
Hardware enables the direct rig monitoring path. DAW Only disables that path
while preserving USB recording and DAW playback; hearing the live input then
requires monitoring in the DAW. The device command and readback for these modes
still need verification before enabling the selector in the GUI.
The user identified these mode labels in the R11 macOS driver
(https://r11audio.com/), rather than the Rack's front-panel settings. The public
R11 landing page does not provide the monitoring request or driver source.
An R11 USB capture of both transitions would provide a reference to investigate.

The user needs a switch to mute the local rig-to-output monitor path while
retaining the rig signal sent to USB inputs 3/4 and DAW playback on outputs 1/2.
This is a separate control from DAW input monitoring, Rig Input selection,
rig volume, or muting the entire Main output.

The downloaded macOS reference driver, JxEngel's community editor, and
ElevenHack do not provide an identified command for this toggle. The Rack's
control descriptors include mixer/extension units, but their presence does
not identify which setting controls direct monitoring. No guessed control
writes were sent and no nonfunctional toggle was added to the GUI.

Next: identify the existing driver/editor toggle and capture its USB control
traffic (and MIDI if applicable) across on/off transitions. Verify the exact
request and state readback, then implement it in the utility. Validate that
monitor-off still records signal on USB 3/4 and still plays DAW audio through
Main Out L/R. Confirm monitor-on restores the direct rig path.

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
DAW-only monitoring is controlled through the driver’s ALSA mixer control.
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
The selected hardware clock frequency is read every two seconds through the
read-only ALSA `Eleven Rack Sample Rate` control, including when PCM is idle.
It uses USB CUR reads of selector 0x80 and selected clock 0x81, 0x82 or 0x83;
no stream is opened and no clock settings are written. USB reconnects are
checked every three seconds and re-establish the subscription.
PCM hw_params are read every 250 ms solely for the stream activity label.
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

## DAW-only monitoring

The panel exposes **Off · Hardware monitoring** and **On · DAW only**.
Hardware mode returns monitoring control to the box; it does not mute the
Main output. DAW-only mode takes software control and silences all eight
input crosspoints. Hearing live input then requires DAW input monitoring.

Paul Bender (R11 Audio) supplied the protocol directly on 2026-10-10:
all writes use bmRequestType 0x21, bRequest 0x03, interface 1.
Hardware mode writes byte 2 with wValue 0, wIndex 0x2001.
DAW-only writes byte 1 to that gate, then eight four-byte payloads
`00 80 00 80` (two signed 0x8000 silence gains) to wIndex 0x4001,
wValue `0x27 + 6 * input`, with input numbered 0 through 7.

The kernel exposes `Eleven Rack Monitoring Mode` through ALSA. Interface 1
remains owned by ALSA; no USB detach, userspace root access or libusb is needed.
Clock, rate, USB PCM routing and MIDI Rig Input are not changed by this control.

```bash
python3 tools/eleven-rack-settings.py monitor
python3 tools/eleven-rack-settings.py monitor daw-only
python3 tools/eleven-rack-settings.py monitor hardware
```

The driver reads the actual hardware state with bmRequestType 0xA1,
bRequest 0x03, using the same wValue/wIndex and lengths as the writes.
A read-only probe confirmed all nine addresses return full-length data;
request 0x01 instead stalls and is not used. A second test confirmed gate 1
in DAW-only mode and gate 2 in Hardware mode. See
[readback validation](monitoring-readback-validation.json).

Gate 2 means Hardware, irrespective of crosspoint gains. Gate 1 means DAW
Only only if all eight L/R crosspoints equal silence. Otherwise it is a custom
Software Mix. Unknown gate values remain Unknown. Failed or short reads are
reported as errors, never replaced by a cached setting. Writes include actual
readback verification; failed writes or verification attempt gate 2 to recover
hardware monitoring and preserve the original error.

The panel reads on connection, after writes, on ALSA notifications, and every
five seconds. A small **Refresh all settings** icon in the header refreshes
monitoring, Rig Input, clock status/source, hardware sample rate, and buffer size
together. Individual read buttons have been removed. The refresh sends no
setting changes and continues reading other fields if one read fails. The sample
rate remains visible while idle because it comes from the device clock. Opening or
refreshing the panel sends no monitoring writes. A custom software mix is
shown separately rather than mislabelled Hardware or DAW-only. Old asynchronous
reads cannot override a newer selection or a disconnected device's status.

Package 0.1.2~beta4 was installed and activated on 7.0.0-38-generic. Its first
read after driver reload returned Hardware before any monitoring write, and
both Hardware and DAW-only were subsequently verified through the new ALSA
readback. The test restored Hardware and force-quantum 128/rate 48000. See
[active driver verification](monitoring-readback-activation.json).

The protocol and each failure position were tested against the actual kernel
callbacks using injected USB responses; the module builds for 7.0.0-38-generic. Package 0.1.2~beta3 was installed and
the driver reloaded on that kernel. Both modes were accepted by the connected
Rack without USB errors, and the test returned to Hardware. The fixed graph
quantum 128 and rate 48000 were restored. See
[USB validation](monitoring-usb-validation.json). The user additionally confirmed, with REAPER closed and guitar input, that
DAW-only silences direct monitoring and Hardware restores it. USB rig capture
and DAW playback while DAW-only is enabled still require a separate check.
Direct monitoring suppression and restoration are physically confirmed.
USB rig capture on inputs 3/4 and DAW playback while DAW-only is enabled have
not yet been separately verified.

Package 0.1.2~beta5 adds the read-only hardware frequency control. On the
connected Rack it returned 96000 Hz before any audio stream was opened;
PipeWire retained its independent forced rate of 48000 and buffer of 128.
Validation: `sample-rate-readback-validation.json`.

Selecting Sample rate now applies the hardware clock and the PipeWire session
rate together. After the hardware accepts the rate, the control sets
clock.rate and clock.force-rate, leaving clock.force-quantum unchanged.
This prevents a new JACK/REAPER session from reopening the Rack at the old
PipeWire default. A failed PipeWire change restores previous metadata and
hardware rate; restoration failures are reported. This affects the shared
PipeWire graph. The selected session rate lasts until changed or PipeWire
is restarted; startup persistence is not added by this hotfix.

The installed hotfix was checked by selecting 96 kHz and opening ordinary
REAPER with the existing test project: hardware, ALSA playback/capture and
PipeWire remained at 96 kHz. The pre-existing forced quantum of 256 was
unchanged. See [rate synchronization validation](sample-rate-session-sync-validation.json).

At 88.2/96 kHz the control offers fixed buffers 512, 1024 and 2048 only.
256 was reported audibly scrambled at both rates; 64/128 and Automatic are
conservatively excluded until shown usable. This is a minimum-buffer safety
policy, not validation of every offered buffer. Selecting a high rate with
a smaller/automatic buffer raises it to 512. CLI writes enforce the same
policy; hardware reads remain unchanged and external unsupported settings
are shown as unsupported rather than silently rewritten by polling.

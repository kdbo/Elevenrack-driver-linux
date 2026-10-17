# REAPER with Eleven Rack and system audio

For the general explanation of hardware access and shared audio, see
[DAWs, the Eleven Rack, and system audio](daw-audio.md).

ALSA exposes 8 capture and 6 playback channels. REAPER's saved direct ALSA
configuration already requests those counts. PipeWire currently holds both
hardware streams, so REAPER cannot concurrently open the same hardware PCM.

Use PipeWire's JACK client compatibility to share the device and access the
named ports configured in this repository:

```bash
sudo apt install pipewire-jack
```

Close REAPER normally, saving any project, and relaunch it through pw-jack:

```bash
pw-jack /path/to/REAPER/reaper
```

In REAPER's Audio → Device preferences choose JACK, disable automatic jackd
launching, and use 8 input and 6 output channels where those fields are offered.
Select/route the Eleven Rack ports rather than the built-in sound card. Input
3/4 is Eleven Rig L/R; output 1/2 is Main Out L/R. PipeWire/JACK routing may
need explicit connections depending on REAPER's auto-connect options.

This PipeWire/JACK approach was used to address the project's REAPER and
system-audio sharing issue. It does not establish validation of every REAPER
recording/playback scenario or other DAWs.

The local launcher and wrapper are kept outside this repository in
`~/.local/share/eleven-rack-local/reaper/`. They are not shipped in the driver
package. The installed desktop launcher references that local wrapper.

The local launcher now executes REAPER directly, without `pw-jack`. The user
confirmed that a direct launch with REAPER's audio system set to **JACK** shares
audio with system applications on this machine. This depends on the installed
JACK library resolving to PipeWire's implementation; direct launch does not
switch REAPER to ALSA. On systems where that library is not selected by default,
use the `pw-jack` command above. The desktop entry checks the REAPER executable
itself with `TryExec`, rather than requiring the `pw-jack` wrapper.

The start method is configurable in
`~/.local/share/eleven-rack-local/reaper/launch-mode`. Put exactly one value on
the first line: `direct` (the current default) or `pw-jack`. Both modes clear
`PIPEWIRE_NODE` and hide playback monitor ports. Keep REAPER's audio system set
to JACK in either mode. Fully quit REAPER before relaunching after a change.
An optional `REAPER_LAUNCH_MODE=direct` or `REAPER_LAUNCH_MODE=pw-jack`
environment variable overrides the file for a launch. An invalid mode stops
the launcher with an error; selecting `pw-jack` requires that command to be
installed.

The launcher unsets `PIPEWIRE_NODE` and sets
`PIPEWIRE_PROPS='{ jack.show-monitor=false }'` to hide playback monitor ports.
It leaves JACK hardware port enumeration unrestricted so both audio and MIDI
are available. Other audio devices may also appear; explicitly select/route the
Eleven Rack ports. Fully quit and relaunch REAPER after changing the launcher.

## MIDI ports and “Not Found”

In REAPER 7.82, open Options → Preferences → Audio → MIDI Inputs and MIDI
Outputs. Enable the desired ports on each page:

- **Eleven Rack Rig** communicates with the internal rig.
- **Eleven Rack External** accesses the physical MIDI IN/OUT connectors.

ALSA exposes these USB MIDI ports. PipeWire's `Midi-Bridge` makes them available
to JACK clients such as REAPER. This bridge is already provided by PipeWire;
no additional bridge application is required for this setup.

The previous local launcher set `PIPEWIRE_NODE='Eleven Rack'` to restrict audio
port enumeration. MIDI ports belong to `Midi-Bridge`, so that filter also hid
them. REAPER retained their cached names but displayed **Not Found**. On
2026-10-14, the ports were confirmed present in ALSA (`aconnect -l`) and
PipeWire (`pw-link -o` / `pw-link -i`); restarting REAPER without the filter
made MIDI visible. The launcher now clears the filter, including an inherited
value from the environment.

To diagnose the same symptom with an older launcher, save your project, quit
REAPER completely, and run:

```bash
env -u PIPEWIRE_NODE pw-jack /path/to/REAPER/reaper
```

Check the MIDI Inputs and MIDI Outputs pages again. Visibility verifies port
discovery; it does not by itself verify MIDI recording, playback, or SysEx.

[PipeWire pw-jack documentation](https://docs.pipewire.org/page_man_pw-jack_1.html)
explains how the wrapper loads its JACK client libraries.

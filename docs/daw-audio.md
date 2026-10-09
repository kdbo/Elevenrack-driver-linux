# DAWs, the Eleven Rack, and system audio

## Why direct ALSA can cause trouble

The patched driver exposes the Eleven Rack's audio channels through ALSA.
On a PipeWire desktop, PipeWire normally opens the hardware and shares it
between applications, including browsers and other system audio.

A DAW configured to open the Rack's ALSA hardware device directly bypasses
PipeWire. If PipeWire already owns that PCM device, the DAW may report that
the device is busy or fail to start audio. If the DAW obtains exclusive access,
other applications may lose access to the Rack. This ownership conflict can
occur with other USB interfaces and audio applications too; it is separate
from whether the Eleven Rack driver loads successfully.

For a DAW that supports JACK, use **PipeWire's JACK compatibility** to access
the Rack's multichannel ports through the same server as desktop audio.
This was the approach used for the project's REAPER setup. Other applications
need their own routing and recording/playback validation.

## Configure an application to use PipeWire/JACK

These instructions assume a running PipeWire desktop with the Rack visible
as an audio device. On Ubuntu, install the JACK compatibility package:

```sh
sudo apt install pipewire-jack
```

Save work, fully close the application, and launch its native Linux executable:

```sh
pw-jack /path/to/your-audio-application
```

Select **JACK** in the application's audio settings. Disable automatic
launching of a separate `jackd` server if that option is present: PipeWire
provides the JACK service in this setup. A separate JACK server trying to open
the same hardware would reintroduce the ownership conflict.

Connect the application's inputs and outputs to the Eleven Rack ports using
its own routing controls or a PipeWire/JACK patchbay. Selecting JACK does not
necessarily select the Rack or connect all channels automatically.

| Task | Eleven Rack ports |
| --- | --- |
| Record the processed rig | Eleven Rig L/R (capture channels 3/4) |
| Record the dry guitar | Guitar In (capture channel 1) |
| Play DAW audio through the main outputs | Main Out L/R (playback channels 1/2) |

The Rack exposes eight capture and six playback channels in total. See
[interface settings](interface-settings.md) for the complete channel list.
Route desktop audio to the Rack as well if you want both desktop and DAW
playback through its outputs; sharing PipeWire does not change the desktop's
selected output device automatically.

`pw-jack` makes the application load PipeWire's JACK client libraries. On a
system where those libraries already replace JACK globally, the wrapper may
be unnecessary. See the [official pw-jack documentation](https://docs.pipewire.org/page_man_pw-jack_1.html).
Sandboxed applications can require additional audio permissions or integration;
these launch instructions describe native Linux applications.

## Sample rate and buffer size

With this setup, PipeWire manages the shared audio graph. The **Buffer size**
control in Eleven Rack Control applies to that shared session, including
system audio. It is not an independent buffer setting for one DAW.

A DAW's project sample rate can differ from the hardware stream rate when
resampling is involved. Check the active stream rate in Eleven Rack Control
rather than assuming the project setting changed the hardware clock.
Stop audio applications before changing hardware clock source or internal rate.

## When audio is missing

- **Device busy with ALSA selected:** switch the application to JACK through
  PipeWire and fully restart it.
- **JACK starts but there is no signal:** check the connections to the Rack;
  the application may have connected to the built-in sound card instead.
- **DAW audio works but desktop audio uses another device:** select the Rack
  as the desktop output and check its playback connections.
- **No Rack audio ports appear anywhere:** first check driver loading and
  device detection using the [installation guide](packaging.md).

Direct ALSA remains an option for a dedicated setup that deliberately manages
exclusive hardware access. The PipeWire/JACK approach is intended for sharing
the interface with desktop audio while retaining multichannel DAW routing.

See [the REAPER example](reaper.md) for application-specific settings and the
optional launcher filter used during development.

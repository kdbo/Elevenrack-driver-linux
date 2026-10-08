# REAPER with Eleven Rack and system audio

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

The installed native REAPER executable inspected in this session was
`/home/koen/Downloads/reaper782_linux_x86_64/reaper_linux_x86_64/REAPER/reaper`.
The JACK package was not installed when these instructions were written.
REAPER recording/playback through this path still needs validation.

The local launcher and wrapper are kept outside this repository in
`~/.local/share/eleven-rack-local/reaper/`. They are not shipped in the driver
package. The installed desktop launcher references that local wrapper.

That launcher sets `PIPEWIRE_NODE=Eleven Rack` to filter JACK port
enumeration to the Rack's node-name prefix, plus
`PIPEWIRE_PROPS='{ jack.show-monitor=false }'` to hide playback monitor ports.
A JACK client test verified exactly eight named capture ports and six named
playback ports. This only affects applications started through this launcher;
desktop audio retains all its devices. Fully quit and relaunch REAPER to apply
the filter. If the Rack is disconnected, this view has no hardware ports.

[PipeWire pw-jack documentation](https://docs.pipewire.org/page_man_pw-jack_1.html)
explains how the wrapper loads its JACK client libraries.

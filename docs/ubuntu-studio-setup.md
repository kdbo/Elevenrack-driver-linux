# Ubuntu Studio audio setup for Eleven Rack

Ubuntu Studio provides audio configuration tools that can be added to an
existing Ubuntu desktop. This is optional: install the Eleven Rack packages
using the [installation guide](../INSTALLATION.md) regardless of which desktop
you use. Ubuntu Studio does not replace the patched Eleven Rack driver.

## Install the audio tools

On Ubuntu or an official Ubuntu flavor:

```sh
sudo apt update
sudo apt install ubuntustudio-installer
```

Open **Ubuntu Studio Installer** from the application menu. Select the audio
configuration, low-latency settings, and performance tweaks available for your
release, then apply the selection. You can leave unrelated creative applications
unselected. Follow any request to log out and back in so new audio permissions
take effect; reboot if kernel settings have changed.

The [official installer guide](https://ubuntustudio.org/ubuntu-studio-installer/)
explains this route. It adds Ubuntu Studio packages to your current desktop;
it does not convert the distribution into Ubuntu Studio.

Alternatively, install Ubuntu Studio itself using its
[official download and installation instructions](https://ubuntustudio.org/download/).
Then install this project's driver and Control panel using the linked guide.

## Configure the audio session

Open **Ubuntu Studio Audio Configuration** and keep PipeWire with its JACK
compatibility enabled for this project's normal desktop workflow. A separate
JACK server is unnecessary for applications using PipeWire-JACK.

Start with **48,000 Hz and a quantum of 128 frames**. Ubuntu Studio's interface
varies by release; consult its
[Audio Configuration guide](https://ubuntustudio.org/audio-configuration/).
Use Eleven Rack Control to set the Rack's sample rate and buffer size for the
current session. Its buffer setting affects the shared PipeWire graph, including
other audio applications. Avoid conflicting rate/buffer settings in application
launch options or other configuration tools.

For a JACK-capable DAW, select JACK as the audio system and launch through
PipeWire's compatibility wrapper when needed, for example:

```sh
pw-jack reaper
```

Close audio applications before changing the hardware sample rate. In Control,
check that the hardware and ALSA rates agree once audio is running. If playback
crackles or drops out, increase the buffer to 256 or 512 frames and check again.
Higher sample rates and smaller buffers need separate stability testing.

At 48 kHz, 128 frames represent 2.67 ms per buffer. That is only one component
of roundtrip latency: USB scheduling, playback/capture queues, and the hardware
also contribute. Our loopback measurements at this setting were around
10.94 ms; this is a measured reference, not a guarantee for every installation.
Control displays the active audio graph's reported roundtrip latency when
available. See [regression testing](audio-regression-tests.md) for physical
loopback checks and longer stability tests.

## Low-latency kernel settings and real-time permissions

Ubuntu Studio 24.10 and newer use a generic kernel with low-latency boot
options available through Audio Configuration. The official guide describes
`preempt=full` and `threadirqs`; apply kernel options through that utility and
reboot before checking them. Ubuntu Studio 24.04 uses a different kernel setup,
so follow the instructions for your release rather than copying another
release's kernel package or boot configuration.

Useful checks after logging in again:

```sh
uname -r
cat /proc/cmdline
id -nG
ulimit -r
ulimit -l
systemctl --user status pipewire wireplumber
wpctl status
ps -eLo pid,tid,cls,rtprio,pri,comm
```

The permission limits are ceilings, not proof that an audio thread runs at
that priority. PipeWire, RTKit, and service limits also affect the priorities
actually granted. The Eleven Rack driver does not assign real-time priorities
to PipeWire, DAWs, or USB interrupt threads.

## Development machine reference

Inspected on 2026-10-11: Ubuntu 26.04.1 LTS with Ubuntu Studio packages added
to the existing desktop:

| Package | Installed version |
| --- | --- |
| `ubuntustudio-installer` | `2.0.7` |
| `ubuntustudio-lowlatency-settings` | `26.04.34` |
| `ubuntustudio-performance-tweaks` | `26.04.34` |
| `ubuntustudio-pipewire-config` | `26.04.34` |

The booted kernel was `7.0.0-38-generic`. Its current command line did not
include `preempt=full` or `threadirqs`; installing the tools alone does not
establish that those options are active. The installed Ubuntu Studio limits
file allows the `audio` and `pipewire` groups an RT priority ceiling of 95 and
unlimited locked memory. Actual group membership, session limits, and thread
priorities must still be checked on the target machine.

No system settings are changed by this document.

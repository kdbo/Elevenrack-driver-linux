# Eleven Rack on Linux

Experimental ALSA support for the Digidesign Eleven Rack (`0dba:b011`).

The connected device currently exposes two MIDI inputs and outputs through
`snd-usb-audio`, but no PCM audio device. This repository contains a first
kernel compatibility patches. A five-second 8-channel recording at 48 kHz has
been verified to contain signal, and the user confirmed audible playback of
the recording through the Eleven Rack at 48 kHz. Other rates, simultaneous
recording/playback, and long-term stability still need testing.

See [the investigation](docs/investigation.md) and
[the experimental patch](patches/0001-eleven-rack-uac2-experimental.patch).
See [interface settings](docs/interface-settings.md) for named PipeWire ports
and the clock/rate/Rig Input utility.

For the combined Ubuntu 24.04-and-newer beta package, see
[packaging](docs/packaging.md). Build a local `.deb` with
`python3 tools/build-deb.py`. Kernel compatibility requires matching sources,
headers, and testing; the package is not yet a production release.

For automatic package builds and publishing tagged GitHub Releases, see
[CI and release management](docs/releases.md).

The patch now targets Ubuntu source package `7.0.0-38.38` and compiled successfully
against headers for `7.0.0-38-generic`. No system modules have been changed.

Build with `bash tools/build-module.sh`. Temporarily load with
`sudo bash tools/load-experimental.sh` after closing USB audio/MIDI clients.
This retains the installed driver and makes no persistent configuration changes.
To restore it, run `sudo modprobe -r snd_usb_audio` followed by
`sudo modprobe snd_usb_audio`, or reboot.

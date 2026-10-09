# Credits and references

Project development and Linux integration: **Koen de Boevé**.

## Driver and protocol references

- **Matt Housley — [eleven-rack-driver](https://github.com/Matt-Housley/eleven-rack-driver).**
  The macOS driver was a reference for USB audio behavior, supported sample
  rates, channel mapping, and MIDI Rig Input messages. See the documented
  findings in [the investigation](docs/investigation.md) and
  [interface settings](docs/interface-settings.md).
- **Linux kernel and ALSA contributors — [Linux source](https://github.com/torvalds/linux/tree/master/sound/usb).**
  This project patches and rebuilds ALSA's existing `snd-usb-audio` driver.
  Its USB quirks, stream parsing, clock handling, and implicit-feedback code
  provide the implementation foundation. Kernel code retains its upstream
  license and copyright notices.
- **Ubuntu kernel team — [Ubuntu kernel sources](https://git.launchpad.net/~ubuntu-kernel/ubuntu/+source/linux/+git/noble).**
  Matching Ubuntu sources and headers are used for DKMS builds and the
  compatibility checks, including the Ubuntu 24.04 HWE source packages.
- **Paul Bender — [R11 Audio](https://r11audio.com/).**
  Paul explained the monitor-extension gate and crosspoint muting used by
  his macOS driver's Hardware/DAW Only modes. This is a reference for future
  investigation; the monitoring toggle is not implemented in this project.

## Editor projects reviewed

These projects were examined as protocol references or possible starting
points for a future Linux editor. No editor code is currently included.

- **Charles Wardick — [Eleven-Edit](https://github.com/CharlesWardick/Eleven-Edit).**
  Original Eleven Edit rig editor/librarian, with an Electron interface and
  Java MIDI bridge.
- **damielolar-CODE — [Eleven-Edit](https://github.com/damielolar-CODE/Eleven-Edit).**
  macOS fork of Charles Wardick's editor, including a native CoreMIDI bridge.
- **JxEngel — [11Rack.Controller.App](https://github.com/JxEngel/11Rack.Controller.App).**
  Community editor reviewed during the investigation of the Eleven Rack
  protocol and hardware monitoring.
- **ElevenHack.** Also reviewed during the monitoring investigation; no code
  from it is included in this project.

## Documentation and infrastructure

- **PipeWire and WirePlumber contributors:**
  [channel properties](https://pipewire.pages.freedesktop.org/pipewire/group__pw__keys.html),
  [WirePlumber ALSA configuration](https://pipewire.pages.freedesktop.org/wireplumber/daemon/configuration/alsa.html),
  and [pw-jack documentation](https://docs.pipewire.org/page_man_pw-jack_1.html)
  informed channel naming, routing, and REAPER integration.
- **DKMS contributors — [DKMS](https://github.com/dkms-project/dkms).**
  Provides kernel-module build and update integration.

## Licensing

The [MIT License](LICENSE) applies to original project code. Credits do not
relicense external code, kernel patches, or dependencies. Their respective
licenses and copyright notices remain applicable. Any future editor import
must preserve the licensing and attribution of the exact upstream revision.

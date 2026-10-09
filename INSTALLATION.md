# Installation guide

This guide covers the Ubuntu `.deb` packages for **Eleven Rack Control and the
patched audio driver**, and the separate **Eleven Rack Editor**. The packages
target Ubuntu 24.04 LTS and newer; actual test coverage is listed in the
[README distribution matrix](README.md#distribution-test-matrix).
These are experimental beta packages.

## 1. Download the packages

Open [GitHub Releases](https://github.com/kdbo/Elevenrack-driver-linux/releases)
and choose the release you want to install. Expand **Assets** and download:

- `eleven-rack-driver_<version>_all.deb`: the audio driver, Control panel, and
  routing configuration.
- `eleven-rack-editor-linux_<version>_amd64.deb`: the optional rig editor for
  x86_64/amd64 computers.
- `SHA256SUMS`: checksums for the release packages.

The editor and driver are installed separately. To use the Rack's audio
channels with this project, install the driver package first. You can skip
the editor if you only need audio and interface settings.

The examples below use `0.1.1~beta3`. Substitute the exact downloaded filenames
when installing another release. Keep each release's downloads in its own
folder so older packages are not accidentally selected.

Optionally verify the files from that folder:

```sh
sha256sum --check --ignore-missing SHA256SUMS
```

Each downloaded package should report `OK`. Stop if a checksum fails.

## 2. Prepare the kernel headers

Save your work and close audio and MIDI applications. Open a terminal in the
download folder, then update APT and install headers for the running kernel:

```sh
sudo apt update
sudo apt install linux-headers-$(uname -r)
```

The driver is built locally by DKMS for your kernel. Matching headers and
Ubuntu kernel sources are required. The package resolves its declared build
and runtime dependencies through APT; the DKMS helper retrieves exact Ubuntu
sources when needed, including HWE sources. The first build may download
hundreds of MB and need several GB of temporary disk space and network access.

If exact headers or sources are unavailable, consult
[the packaging guide](docs/packaging.md) before proceeding. Custom, mainline, and
OEM kernels are not validated by this guide.

## 3. Install the driver and Control panel

From the download folder:

```sh
sudo apt install ./eleven-rack-driver_0.1.1~beta3_all.deb
```

Use `apt install` with the local filename so APT can install dependencies.
Wait for the DKMS build to finish successfully. Installation overrides the
system `snd-usb-audio` module with a patched build; that module also handles
other USB audio devices. Installation does not forcibly unload the active
module or restart your audio services.

If Secure Boot prompts you to create/enroll a Machine Owner Key (MOK), follow
Ubuntu's instructions and complete enrollment during reboot. A successfully
built module still needs a trusted signing key to load under Secure Boot.

After successful installation, reboot. Connect and power on the Eleven Rack,
then open **Eleven Rack Control** from the application menu, or run:

```sh
eleven-rack-control gui
```

## 4. Check device detection

Control should report a connected device. You can also check:

```sh
dkms status
aplay -l
arecord -l
wpctl status
```

Look for the Eleven Rack among ALSA's playback and capture devices and in
PipeWire's device/node list. MIDI detection alone does not confirm that the
patched audio driver is active.

The configured interface has eight capture and six playback channels:
**Eleven Rig L/R** are capture channels 3/4, and **Main Out L/R** are playback
channels 1/2. See [interface settings](docs/interface-settings.md) for the complete
mapping and Control's clock, rate, Rig Input, and buffer settings.

Start with an internal clock and 48 kHz for the first audio check; capture and
playback at that rate have been tested. Stop audio applications before changing
hardware clock source or internal rate. The hardware-monitoring switch is not
implemented yet.

## 5. Install the optional editor

From the download folder:

```sh
sudo apt install ./eleven-rack-editor-linux_0.1.1~beta3_amd64.deb
```

APT installs the editor's declared runtime dependencies, including the Python
MIDI bridge dependencies. Node.js and npm are not required to run the packaged
editor.

Open **Eleven Rack Editor** from the application menu. With the Rack connected,
select its MIDI ports if they are not selected automatically. If another
application is using the same MIDI ports, close it and retry.

The application is installed under `/opt/Eleven Rack Editor/`; its launcher
is installed under `/usr/share/applications/`. See
[the editor guide](editor/README.md) for usage and current limitations.

## 6. Set up DAW and desktop audio

If you want desktop audio through the Rack, select it as the output device in
Ubuntu's sound settings.

For a JACK-capable DAW on a PipeWire desktop, use PipeWire's JACK compatibility
so the DAW and desktop audio can share the interface. Direct ALSA hardware
access can conflict with PipeWire's ownership of the device.

Follow [DAWs, the Eleven Rack, and system audio](docs/daw-audio.md) for installation,
launching, port connections, and buffer settings. The
[REAPER example](docs/reaper.md) provides application-specific settings.

## Updates and removal

Install a newer downloaded package with `sudo apt install ./<filename>.deb`.
APT upgrades the installed package. After a driver update, reboot to use the
new module. After an editor update, fully close and reopen the editor.

DKMS rebuilds the driver for kernel updates when matching sources and headers
are available. Check `dkms status` after an update and confirm that the build
succeeded before relying on the new kernel for audio.

To remove the applications:

```sh
sudo apt remove eleven-rack-editor-linux eleven-rack-driver
```

Reboot after removing the driver to return to the distribution's module.
Use `apt purge` instead of `apt remove` if you also want package-owned
configuration removed. Per-user settings are not removed by these commands.

## Common installation problems

**DKMS reports a bad module build status:** read the `make.log` path printed
by DKMS. Check the exact kernel version, matching headers, and source download
failure before retrying. Once the cause is fixed, `sudo dpkg --configure -a`
retries package configuration. See [packaging](docs/packaging.md) for source handling
and log locations.

**APT says a local download was performed unsandboxed as root:** APT's `_apt`
user could not read the package or traverse its parent directories. This notice
alone is not a DKMS build failure. Copy the downloaded package to `/tmp/`, make
it readable, and install that copy if needed:

```sh
cp ./eleven-rack-driver_0.1.1~beta3_all.deb /tmp/
chmod 644 /tmp/eleven-rack-driver_0.1.1~beta3_all.deb
sudo apt install /tmp/eleven-rack-driver_0.1.1~beta3_all.deb
```

**The module built but the Rack has no audio devices:** reboot, check
`dkms status`, and check kernel logs for module-load or signature errors. Under
Secure Boot, confirm that the signing key was enrolled. Include the kernel
version and DKMS/kernel error when reporting an issue.

**The DAW reports a busy device or produces no sound:** use
[the shared-audio troubleshooting guide](docs/daw-audio.md#when-audio-is-missing).
Check audio connections to the Rack rather than the built-in sound card.

**Rig Input or editor MIDI reads fail:** another MIDI application may own the
port. Close competing applications, verify the selected ports, and retry.
USB passthrough in a VM may require separate investigation; a working audio
driver does not establish that every MIDI exchange is reliable there.

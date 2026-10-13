# Installation guide

Install the package set built for your distribution and architecture. The
`eleven-rack-driver` package includes the patched DKMS audio driver, Eleven Rack
Control, the PipeWire backend and audio configuration. The optional
`eleven-rack-editor-linux` package provides the rig Editor and Linux MIDI bridge.
Node.js and npm are not required to run the packaged Editor.

These are experimental beta packages. A successful package build or driver load
is not a complete hardware audio test. See the
[distribution test matrix](README.md#distribution-test-matrix) for coverage.

## Download and prepare

Download matching packages from
[GitHub Releases](https://github.com/kdbo/Elevenrack-driver-linux/releases) when
available. A distribution's build recipe does not guarantee that its packages
have already been published. For a supplied test artifact, extract it first.
Keep each package set in its own folder and open a terminal there.

Verify its checksums using the supplied checksum filename:

```sh
sha256sum --check --ignore-missing SHA256SUMS
```

Every downloaded package should report `OK`. Stop if a checksum fails. For sets
containing `package-target.json` or `README.txt`, check the supported kernel,
PipeWire and distribution versions before installation.

Save your work and close audio and MIDI applications. Installation replaces
`snd-usb-audio`, which also serves other USB audio devices. Reboot after a
successful driver installation. If Secure Boot is enabled, the DKMS module's
signing key must be trusted; complete any required key enrollment before use.

## Ubuntu 24.04 and newer

Use the Ubuntu `.deb` package set. Install headers for the running kernel, then
install the downloaded packages through APT so dependencies are resolved:

```sh
sudo apt update
sudo apt install "linux-headers-$(uname -r)"
sudo apt install ./*.deb
dkms status
sudo reboot
```

You can install only the driver if you do not need the Editor by replacing the
wildcard with its exact filename. Wait for the DKMS build to succeed before
rebooting. The installer obtains matching Ubuntu kernel sources when needed;
network access and temporary disk space are required. Custom, mainline and OEM
kernels are not validated by this guide.

The universal Ubuntu package builds its PipeWire backend locally from bundled,
verified sources. PipeWire updates trigger a rebuild. A PipeWire version outside
the bundled catalog requires an updated Eleven Rack package. The Editor uses
the Ubuntu 24.04 amd64 baseline.

For optional audio tools and desktop setup, see
[Ubuntu Studio setup](docs/ubuntu-studio-setup.md).

## Fedora

Use RPMs built for your Fedora release (currently Fedora 43 or 44), not CentOS
RPMs. The running kernel must be one of the package's bundled targets. Install
its full module packages and development files before the Eleven Rack RPMs:

```sh
sudo dnf install "kernel-devel-$(uname -r)" "kernel-modules-core-$(uname -r)" "kernel-modules-$(uname -r)" "kernel-modules-extra-$(uname -r)"
sudo dnf install ./*.rpm
dkms status
sudo reboot
```

Use `dnf install` rather than installing RPMs without dependency resolution.
The package set records its supported kernel and PipeWire versions; rebuild or
obtain an updated set before upgrading beyond those targets. The Editor needs
the matching Fedora Python ABI.

## CentOS Stream 10

Use the CentOS Stream 10 x86_64 RPM set. Enable CRB and EPEL for dependencies,
then install the running kernel's module packages and development files:

```sh
sudo dnf install dnf-plugins-core
sudo dnf config-manager --set-enabled crb
sudo dnf install https://dl.fedoraproject.org/pub/epel/epel-release-latest-10.noarch.rpm
sudo dnf install "kernel-devel-$(uname -r)" "kernel-modules-core-$(uname -r)" "kernel-modules-$(uname -r)" "kernel-modules-extra-$(uname -r)"
sudo dnf install ./*.rpm
dkms status
sudo reboot
```

The package's recorded kernel, PipeWire and Python versions must match the
installation. Fedora RPMs are not interchangeable with CentOS RPMs. CentOS
hardware audio validation is still pending.

## Arch Linux

Use the x86_64 Arch package set for the stock `linux` kernel. Check that the
kernel, headers and PipeWire match the package's recorded targets:

```sh
uname -r
pacman -Q linux linux-headers pipewire
sudo pacman -U ./*.pkg.tar.zst
dkms status
sudo reboot
```

Pacman resolves declared dependencies. The package pins its kernel/header and
PipeWire versions. Obtain a rebuilt set before updating those pinned components;
`linux-lts`, custom kernels and ARM are not covered by this package. The complete
driver includes its backend, so a separate backend package is not needed.

## First use on every distribution

Connect and power on the Eleven Rack. Open the applications from the desktop
menu or run:

```sh
eleven-rack-control gui
eleven-rack-editor-linux
```

Check audio registration:

```sh
dkms status
cat /proc/asound/cards
cat /proc/asound/pcm
aplay -l
arecord -l
wpctl status
```

The Eleven Rack should have both playback and capture devices. MIDI alone does
not confirm that the patched audio driver is active. Start with Internal clock
and 48 kHz, then test capture and playback in your DAW.

The interface has eight capture and six playback channels. Eleven Rig L/R are
capture channels 3/4; Main Out L/R are playback channels 1/2. See
[interface settings](docs/interface-settings.md) for clock, rate, monitoring,
buffer settings and the full channel mapping.

Select the Eleven Rack in your desktop sound settings for desktop playback.
For a JACK-capable DAW on PipeWire, use its JACK compatibility layer so the DAW
and desktop can share the device. See [DAW setup](docs/daw-audio.md),
[REAPER setup](docs/reaper.md) and the [Editor guide](editor/README.md).

## Updates and removal

Control and the Linux Editor check for newer published packages at startup.
Successful checks are cached for 24 hours. Use **About → Check for updates** to
check immediately. Beta installations also see newer beta releases; stable
installations only see stable releases.

An update notice appears only when a newer release contains one matching package
for the application, distribution release and architecture. **Download and
install…** shows the package name, installation command and an **Open download
page** button. Download and verify the files, check the release requirements,
then run the proposed command yourself. Nothing is downloaded or installed by
the update checker. Driver updates require a reboot; close the Editor before
installing its update and reopen it afterward.

Checks use the public GitHub releases API and require internet access. A failed
background check does not interrupt audio or MIDI; a manual check reports the
failure. Private build artifacts are not offered as public updates.

Install updates using the same distribution package manager and the new local
package filenames. Reboot after a driver update; restart the Editor after an
Editor update. Check DKMS output before booting a new kernel. Fedora, CentOS and
Arch sets need matching build targets; Ubuntu rebuilds when matching sources and
headers are available.

Remove the applications with your distribution's package manager:

```sh
# Ubuntu
sudo apt remove eleven-rack-editor-linux eleven-rack-driver
# Fedora / CentOS
sudo dnf remove eleven-rack-editor-linux eleven-rack-driver
# Arch
sudo pacman -R eleven-rack-editor-linux eleven-rack-driver
```

Reboot after driver removal to return to the distribution's USB audio module.
Per-user settings are retained.

## Troubleshooting

**DKMS build failure:** read the build-log path printed by DKMS. Check the
running kernel, matching development files and supported package targets. See
[packaging](docs/packaging.md) for log locations. On Ubuntu, after fixing the
cause, `sudo dpkg --configure -a` retries incomplete package configuration.

**Unknown ALSA/media symbols:** verify that the running kernel's complete module
packages are installed, including `kernel-modules` and `kernel-modules-extra`
on Fedora/CentOS. A matching `kernel-devel` package alone is insufficient.

**MIDI only after installing kernel packages:** check `modinfo -n snd_usb_audio`
and `modinfo -p snd_usb_audio`. If the stock module is selected, reinstall the
patched module using the version reported by `dkms status`:

```sh
sudo dkms install -m eleven-rack -v '<installed-version>' -k "$(uname -r)" --force
sudo depmod -a
modinfo -n snd_usb_audio
sudo reboot
```

For the tested RPM installation, the patched module path is under `extra/`.
Confirm playback and capture registration after reboot.

**Module built but no audio device:** check kernel logs for module-load and
signature errors. Under Secure Boot, verify that the signing key is trusted.
Include the kernel release and DKMS/kernel errors in an issue report.

**DAW device busy or no sound:** check
[shared-audio troubleshooting](docs/daw-audio.md#when-audio-is-missing) and use
Eleven Rack ports rather than built-in sound-card ports. Close competing MIDI
applications if Editor communication fails.

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

## Distribution test matrix

Status as of 2026-10-09, for x86_64/amd64. **Passed** means the stated check
succeeded; **Partial** means limited testing; **Not tested** means no result
is recorded. A successful build does not establish full distribution support.

| Distribution | Package | Package build/check | Driver compilation | Package installation | Audio on hardware |
| --- | --- | --- | --- | --- | --- |
| Ubuntu 24.04 LTS | `.deb` | Not tested on this OS | Passed: `6.8.0-31-generic` | Not tested | Not tested |
| Ubuntu 24.04 LTS, HWE 7.0 | `.deb` | beta5 built/checked on development host | Passed: `7.0.0-38-generic` HWE sources/headers | Passed: beta5, user-confirmed on VM | Specific audio tests not recorded |
| Ubuntu 24.10 | `.deb` | Not tested on this OS | Passed: `6.11.0-8-generic` | Not tested | Not tested |
| Ubuntu 25.04 | `.deb` | Not tested on this OS | Passed: `6.14.0-15-generic` | Not tested | Not tested |
| Ubuntu 25.10 | `.deb` | Not tested on this OS | Passed: `6.17.0-5-generic` | Not tested | Not tested |
| Ubuntu 26.04 LTS | `.deb` | Passed locally | Passed: `7.0.0-38-generic` | Partial: beta4 installed on development host | Partial: capture and playback at 48 kHz |
| Ubuntu 26.10 beta | `.deb` | Not tested on this OS | Passed: `7.3.0-9-generic` | Not tested | Not tested |
| Fedora Workstation | `.rpm` proposed; not implemented | Not tested | Not tested | Not tested | Not tested |
| Debian | `.deb` adaptation not validated | Not tested | Not tested | Not tested | Not tested |
| openSUSE | `.rpm` proposed; not implemented | Not tested | Not tested | Not tested | Not tested |
| Arch Linux | PKGBUILD/AUR proposed; not implemented | Not tested | Not tested | Not tested | Not tested |

The Ubuntu driver compilation checks used matching sources and headers on the
Ubuntu 26.04 development host, rather than separate installations of each OS.
Exact kernel versions, fingerprints, and historical build
results are in [the build matrix](docs/compatibility-builds.json) and
[the HWE regression result](docs/hwe-build.json).
HWE/OEM kernels, other architectures, and later kernel updates are not covered.
The additional distributions above are candidates, not supported targets.

The user confirmed on 2026-10-09 that beta5 installs and works on the Ubuntu
24.04 VM with HWE kernel `7.0.0-38-generic`, resolving beta4's missing-source
failure. Specific audio scenarios, reboot, upgrade/removal, and Secure Boot
results were not reported for this VM.

The beta4 installation check confirms the package is installed on the existing
development host; clean installation, upgrade, removal, and reboot validation
are still pending. The hardware result covers a five-second capture and audible
playback at 48 kHz with an earlier driver revision, not complete testing of the
current packaged driver. See [the hardware investigation](docs/investigation.md).
Simultaneous recording/playback, sustained audio, REAPER audio, Secure Boot,
and all controls/rates still need full validation.

The [CI workflow](.github/workflows/package.yml) builds and checks the `.deb`
and compiles the Ubuntu 24.04 HWE driver, but its GitHub run has not yet been
verified here. It does not install the driver package, load the driver, or
provide hardware test coverage.

The patch now targets Ubuntu source package `7.0.0-38.38` and compiled successfully
against headers for `7.0.0-38-generic`. No system modules have been changed.

Build with `bash tools/build-module.sh`. Temporarily load with
`sudo bash tools/load-experimental.sh` after closing USB audio/MIDI clients.
This retains the installed driver and makes no persistent configuration changes.
To restore it, run `sudo modprobe -r snd_usb_audio` followed by
`sudo modprobe snd_usb_audio`, or reboot.

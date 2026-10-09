# Eleven Rack on Linux

Experimental Linux audio support for the Digidesign Eleven Rack (`0dba:b011`).
This project patches the existing ALSA USB audio driver so the Eleven Rack can
be used for recording and playback, alongside its USB MIDI connections.
It also provides **Eleven Rack Control** for interface settings and a separate
**Eleven Rack Editor** for editing rigs.

## Driver: standard ALSA behavior

Linux normally handles USB audio and MIDI devices through the ALSA
`snd-usb-audio` kernel module. It reads the device's USB descriptors to identify
audio streams, channels, sample rates, and controls. Device-specific exceptions
are handled through ALSA's existing *quirk* mechanism.

On the Eleven Rack setup investigated for this project, the unpatched driver
exposes two MIDI inputs and two MIDI outputs, but no PCM audio device for
recording or playback. The Rack's audio interfaces are marked as
vendor-specific, even though they contain USB Audio Class 2 (UAC2) descriptors.
The generic ALSA paths do not fully handle this combination and the Rack's
nonstandard control behavior.

## Driver: what this patch changes

This is a compatibility patch to `snd-usb-audio`, using ALSA's existing audio,
MIDI, and mixer implementation. It does not introduce a separate audio stack.
The changes are restricted to the Eleven Rack's USB device ID.

| Area | Behavior added by this project |
| --- | --- |
| Interface recognition | Explicitly handles the vendor-specific interfaces as standard MIDI, audio, and mixer interfaces, making PCM recording and playback available. |
| Stream synchronization | Pairs playback with capture endpoint `0x83` on interface 4 for implicit feedback, allowing the capture stream to provide playback timing information. |
| Sample rates | Supplies a fallback list of 44.1, 48, 88.2, and 96 kHz because the Rack does not support the standard `GET_RANGE` request. These advertised rates are not all hardware-tested. |
| Pitch control | Skips the unsupported endpoint pitch-control request and uses the existing clock-frequency path. |
| Clock selection | Exposes an ALSA clock selector with Internal, AES, and S/PDIF choices, while excluding proprietary routing units from mixer probing. |
| Error reporting | Reports failed clock-selector writes instead of treating them as successful. |

The resulting audio interface provides **8 input channels and 6 output
channels**. The included WirePlumber configuration gives them useful names
and replaces the misleading surround profile for this device:

| Inputs | Outputs |
| --- | --- |
| Guitar In, Mic In | Main Out L/R |
| Eleven Rig L/R | Re-Amp L/R |
| Line In L/R | Digital Out L/R |
| Digital In L/R | |

ALSA provides the driver; PipeWire and WirePlumber handle desktop audio and
routing above it. Applications opening ALSA directly may still show channel
numbers rather than these names. See [the investigation](docs/investigation.md)
and [the patches](patches/) for implementation details and hardware findings.

## Installation and use

Start with the [installation guide](docs/installation.md) for downloading
release packages, installing the driver and editor, first-use checks, and
troubleshooting.

The Ubuntu `.deb` package includes the driver patches, DKMS build instructions,
Eleven Rack Control, and WirePlumber routing configuration. The editor is
packaged separately.

DKMS builds a patched `snd-usb-audio` module from matching Ubuntu kernel sources
and headers. The installed module overrides the distribution's module, so it
also handles other USB audio devices connected to the system. DKMS rebuilds it
for kernel updates when the required headers and sources are available.
Starting with beta5, the build helper can retrieve matching Ubuntu sources,
including HWE sources, without changing the system's APT repository files.

Build a local package:

```sh
python3 tools/build-deb.py
```

Install it through APT so package dependencies are resolved:

```sh
sudo apt install ./build/packages/eleven-rack-driver_0.1.1~beta3_all.deb
```

Matching headers for the target kernel must be available. Close audio
applications before installation, then reboot to use the installed driver.
For source retrieval, Secure Boot, updates, removal, and troubleshooting,
see [the packaging guide](docs/packaging.md).

### Eleven Rack Control

Open **Eleven Rack Control** from the application menu, or run:

```sh
eleven-rack-control gui
```

The panel provides clock source and status, internal sample-rate selection,
Rig Input, input/output channel information, and PipeWire buffer-size settings.
The buffer setting applies to the shared PipeWire session. Stop audio
applications before changing the hardware clock or sample rate; applications
choose their streaming rate when opening the device.

The hardware-monitoring switch remains unavailable pending protocol
verification. See [interface settings](docs/interface-settings.md) for control
behavior and limitations, and [REAPER setup](docs/reaper.md) for DAW routing.

### DAWs and system audio

On a PipeWire desktop, opening the Rack directly through ALSA in a DAW can
conflict with PipeWire's hardware access. For applications that support JACK,
use PipeWire's JACK compatibility so the DAW and system audio share the
interface while retaining multichannel routing. This approach was used for
our REAPER setup and can also apply to other JACK-capable audio applications.

See [DAWs, the Eleven Rack, and system audio](docs/daw-audio.md) for setup,
channel routing, buffer settings, and troubleshooting.

## Validation and distribution compatibility

This remains an experimental beta. A five-second, 8-channel recording at
48 kHz contained signal, and playback of that recording through the Eleven
Rack was confirmed audible. Ubuntu 24.04 LTS with HWE kernel
`7.0.0-38-generic` was also reported to install and work with beta5.
These results do not establish validation of every rate, control, kernel,
or sustained simultaneous recording and playback.

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

## Building and temporarily testing the driver

For development without installing the `.deb`, build the module with:

```sh
bash tools/build-module.sh
```

After closing USB audio and MIDI clients, temporarily load it with:

```sh
sudo bash tools/load-experimental.sh
```

This leaves the installed module on disk and makes no persistent configuration
changes. To restore the installed driver, reboot or run:

```sh
sudo modprobe -r snd_usb_audio
sudo modprobe snd_usb_audio
```

Matching kernel sources and headers are required. See
[the investigation](docs/investigation.md) for the recorded build and audio tests.

## Eleven Rack Editor

The separate Linux editor is in [editor/](editor/README.md). It provides a rig
interface, preset browsing and transfer controls, and a tuner. Tuner note
recognition and reference-frequency changes have been confirmed on hardware;
editing and preset writes still need broader validation.

See [the editor guide](editor/README.md) for startup, packaging, and use, and
[the editor investigation](docs/editor.md) for its upstream ancestry and
protocol research.

## Releases

For automatic package builds and publishing tagged GitHub Releases, see
[CI and release management](docs/releases.md).

## Licensing and credits

Original tools and the control panel use the [MIT License](LICENSE).
Original kernel patches and the kernel patch helper use GPL-2.0-or-later.
Existing kernel code and third-party components retain their upstream licenses.
See [the licensing overview](LICENSING.md) for the exact scope and license texts.

[Credits and references](CREDITS.md) record the projects, developers, and
examples used during development, including the editor's upstream authors
and Paul Bender's contributions to the monitoring investigation.

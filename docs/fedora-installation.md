# Fedora packages

The private [ElevenRack-builds repository](https://github.com/kdbo/ElevenRack-builds)
provides the manual **Fedora package set** workflow. It produces exactly two RPMs:

- `eleven-rack-driver`: DKMS sources prepared from Fedora's matching signed kernel
  source RPM, Control panel, PipeWire latency backend and configuration.
- `eleven-rack-editor-linux`: Electron Editor and Linux MIDI bridge.
  Python-RtMidi is built inside Fedora and bundled next to the bridge, so the
  RPM does not depend on a `python3-rtmidi` repository package. It requires the
  matching Python ABI; Fedora major upgrades need a matching Editor build.

Select Fedora 43 or 44, a public source branch/commit/tag, and leave publication
disabled to build downloadable artifacts without creating a release. Download
`fedora-package-set-<version>` from the completed Actions run and extract the ZIP.
Publication requires an existing version tag containing the packaging changes;
older tags cannot build tools that were added later.

```sh
sha256sum --check SHA256SUMS
sudo dnf install ./*.rpm
dkms status
sudo reboot
```

After reboot, run `eleven-rack-control gui` and `eleven-rack-editor-linux`.

This initial set targets x86_64 Fedora with WirePlumber 0.5 or newer. Fedora 44
builds bundle the current repository kernel and `6.19.10-300.fc44.x86_64` by
default. The optional `additional_kernel_releases` input accepts space-separated
kernel releases available in the selected Fedora repositories.

There is still one driver RPM and one Editor RPM. DKMS builds a separate module
for each bundled kernel and selects its matching source tree. The running kernel
loads its own module; Control is shared. Both module builds and their vermagic
are checked in CI before the artifact is uploaded.

Installation builds only for the currently running, bundled kernel; other kernels
are skipped. Matching headers are required. CI explicitly builds every bundled
target because containers run the host kernel. The driver pins
PipeWire to the versions recorded in `package-target.json` (the `kernels` list).
Boot one of those kernels; build an updated set for kernels outside the list.
Other Fedora releases and RPM distributions are not implicitly supported.
The build fails if its PipeWire version has no verified source in the catalog.

With Secure Boot enabled, trust the DKMS module-signing key before loading the
patched module. Hardware audio and physical latency still require Fedora testing;
the package includes the existing Ubuntu measurement defaults.

CI checks both RPMs, installs them in Fedora, verifies DKMS against the installed
Fedora headers (not the container host's kernel), checks backend factories and
Editor runtime libraries, and tests removal. It does not start desktop/audio
services or claim USB audio validation inside a container.

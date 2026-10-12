# Fedora packages

The private [ElevenRack-builds repository](https://github.com/kdbo/ElevenRack-builds)
provides the manual **Fedora package set** workflow. It produces exactly two RPMs:

- `eleven-rack-driver`: DKMS sources prepared from Fedora's matching signed kernel
  source RPM, Control panel, PipeWire latency backend and configuration.
- `eleven-rack-editor-linux`: Electron Editor and Linux MIDI bridge.

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

This initial set targets x86_64 Fedora with WirePlumber 0.5 or newer. The driver
pins kernel-devel and PipeWire to the versions recorded in `package-target.json`.
Boot the matching kernel; build an updated set before upgrading these packages.
Other Fedora releases and RPM distributions are not implicitly supported.
The build fails if its PipeWire version has no verified source in the catalog.

With Secure Boot enabled, trust the DKMS module-signing key before loading the
patched module. Hardware audio and physical latency still require Fedora testing;
the package includes the existing Ubuntu measurement defaults.

CI checks both RPMs, installs them in Fedora, verifies DKMS against the installed
Fedora headers (not the container host's kernel), checks backend factories and
Editor runtime libraries, and tests removal. It does not start desktop/audio
services or claim USB audio validation inside a container.

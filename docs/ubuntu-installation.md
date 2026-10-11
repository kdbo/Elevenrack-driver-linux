# Universal Ubuntu package set

Builds run in the private `kdbo/ElevenRack-builds` repository. The public source
repository does not need Actions enabled.

Open **Actions → Ubuntu package set → Run workflow**:

- `source_ref`: public source branch, tag or commit, normally `main`.
- `publish_release`: off for private artifact downloads. For public publication,
  select an existing public version tag containing the universal packager and
  enable this option.

There is no Ubuntu version input. The workflow builds one set and automatically
checks those same packages (including 24.04 GA and HWE) in Ubuntu 24.04, 24.10, 25.04, 25.10, 26.04 and
preliminary 26.10 containers. Publication requires those checks to pass.

Download `ubuntu-package-set`, containing exactly two Debian packages:

- `eleven-rack-driver`: reusable across Ubuntu versions from 24.04 onward.
  Includes DKMS driver sources, Control, verified PipeWire source archives,
  compatible latency patches and configuration for WirePlumber 0.4 and 0.5.
- `eleven-rack-editor-linux`: the same amd64 Editor and Linux MIDI bridge package
  across those Ubuntu versions, built on the Ubuntu 24.04 baseline.

Extract the artifact ZIP, open a terminal in that directory, then run:

```sh
sha256sum --check SHA256SUMS
sudo apt install ./*.deb
sudo reboot
```

The installer detects the installed PipeWire version and its system SPA plugin
path and compiles the matching backend locally. Backend source downloads are
not needed during installation. APT installs the compiler and runtime dependencies;
DKMS uses matching kernel source and headers for the installation's kernel.
After reboot, launch `eleven-rack-control gui` and `eleven-rack-editor-linux`.

PipeWire package updates trigger a backend rebuild automatically. A matching,
verified existing build is reused. Runtime build metadata is stored in
`/var/lib/eleven-rack/latency/backend-build.json`. Removal deletes the generated
library and service overrides. An incompatible update or failed build disables
the previous backend instead of leaving an incompatible library active.

The bundled catalog currently covers PipeWire 1.0.5, 1.2.4, 1.2.7, 1.4.7, 1.6.2
1.6.8 and 1.6.9. A future or custom PipeWire version outside this catalog requires an
updated driver package; the installer reports this explicitly and does not ask
which Ubuntu version to use. The package does not pin PipeWire to one distro's
version.

Archived Ubuntu validation inputs use the signed old-releases repository.
26.10 is preliminary. Successful install, DKMS, linking and factory checks do not
establish hardware audio or physical latency accuracy on every Ubuntu release.
The agreed Ubuntu correction defaults remain in use.

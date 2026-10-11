# Complete Ubuntu package sets

Builds run in the private `kdbo/ElevenRack-builds` repository. The public source
repository does not need Actions enabled.

Open **Actions → Ubuntu package set → Run workflow**:

- `source_ref`: public source branch, tag or commit, normally `main`.
- `ubuntu_version`: 24.04, 24.10, 25.04, 25.10, 26.04 or preliminary 26.10.
  `all` builds all six targets independently.
- `publish_release`: off for private artifact downloads. For public publication,
  select an existing public version tag and enable this option.

Each successful target produces `ubuntu-package-set-VERSION`, containing exactly
two amd64 Debian packages:

- `eleven-rack-driver`: DKMS driver sources, Control, native PipeWire backend,
  configuration for WirePlumber 0.4 and 0.5, and Ubuntu correction defaults.
- `eleven-rack-editor-linux`: Editor and Linux MIDI bridge.

Packages carry an Ubuntu suffix so different target releases can coexist as
downloads in one public release. Install only the set for your Ubuntu version.
Extract its artifact ZIP, open a terminal in that directory, then run:

```sh
sha256sum --check SHA256SUMS
sudo apt install ./*.deb
sudo reboot
```

After reboot, launch `eleven-rack-control gui` and `eleven-rack-editor-linux`.
The backend pins PipeWire and its stock SPA modules to the build version. Rebuild
before updating those libraries. The checksum manifest includes backend build
metadata and the module vermagic from the pipeline's kernel compilation check.
DKMS builds against the installation's actual kernel and matching source/headers.

The pipeline uses each release's own Ubuntu container, libraries and headers.
Archived 24.10, 25.04 and 25.10 inputs come from Ubuntu's signed old-releases archive.
26.10 is preliminary; its package versions and kernel compatibility can change.
Unknown PipeWire releases fail explicitly until their source hash and compatible
patch are added. Compiler, link, factory and package checks do not establish
physical latency accuracy on every Ubuntu release. Corrections remain the agreed
Ubuntu defaults; cross-version hardware validation is separate.

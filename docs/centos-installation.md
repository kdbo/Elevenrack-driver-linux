# CentOS Stream 10 packages

Run **CentOS Stream 10 package set** in the private
[ElevenRack-builds Actions](https://github.com/kdbo/ElevenRack-builds/actions).
Use public `main` for initial testing and leave publication disabled.
The artifact `centos-stream10-package-set` contains exactly two x86_64 RPMs:
the complete driver/Control/backend and the Editor with its MIDI bridge.

Enable CRB and EPEL on the CentOS VM for dependencies, then install:

```sh
sudo dnf install -y dnf-plugins-core
sudo dnf config-manager --set-enabled crb
sudo dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-10.noarch.rpm
sha256sum --check SHA256SUMS
sudo dnf install ./*.rpm
dkms status
sudo reboot
```

After reboot, use `eleven-rack-control gui` and `eleven-rack-editor-linux`.
Boot the kernel recorded in `package-target.json`. The first driver RPM pins its
kernel-devel and PipeWire dependencies; rebuild before upgrading them.
The Editor bundles native Python-RtMidi and requires the build's Python ABI.
These packages are built for CentOS Stream 10, not interchangeable Fedora RPMs.

The pipeline prepares the exact matching signed kernel source RPM and performs
installation, DKMS, backend and Editor runtime checks in CentOS. Its first
successful run and physical audio testing are required before claiming validated
CentOS support. Ubuntu latency defaults are included without CentOS hardware
calibration. Secure Boot additionally requires trusting the DKMS signing key.

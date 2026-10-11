# VirtualBox package testing

Use separate Arch and CentOS Stream 10 guests for package and kernel-module
tests. These guests do not replace physical-machine audio regression testing.
CentOS Stream coverage does not establish RHEL or Fedora coverage.

The initial setup uses two CPUs, 3 GiB RAM, NAT networking, EFI, and a dynamically
allocated 40 GiB disk per guest. Run one guest at a time on the development
laptop. Neither guest captures the Eleven Rack automatically.

```sh
python3 tools/create-test-vms.py --directory /path/to/test-vms
# Review the commands, then create the powered-off machines:
python3 tools/create-test-vms.py --directory /path/to/test-vms --execute
```

The tool refuses existing VM names or directories. If creation fails midway,
inspect the partial VM in VirtualBox before retrying; the tool does not delete
or overwrite it.

Download installation media from [Arch](https://archlinux.org/download/) and
[CentOS](https://www.centos.org/download/), and verify their published SHA-256
checksums before attaching them to the DVD drives. The CentOS boot ISO requires
network access to install packages. Install a desktop in each guest for Control
and Editor tests; use a regular account for package builds.

After installation, remove the installation ISO and take a clean baseline
snapshot. Copy a source snapshot or release package into the guest; avoid
giving a guest write access to the development checkout. Follow the
[Arch package guide](arch-installation.md) for the initial Arch recipe.
RPM packaging still needs an implementation before equivalent CentOS tests.

Record distribution version, kernel release, package version, build output,
installation result, module vermagic and loaded module path. Check a reboot,
Control launch, kernel update, uninstall, and restoration of the original
`snd-usb-audio`. Keep VM package results separate from physical audio results.

USB passthrough is an explicit later test: attach only device `0dba:b011` when
host audio and regression tests are stopped. This transfers device access away
from the host. Start with detection and basic playback/capture. Guest timing
includes virtualization overhead, so latency/dropout results cannot establish
native-driver performance.

## Development host preparation, 2026-10-11

VirtualBox `7.2.6-dfsg-4` and its DKMS modules were installed on Ubuntu
26.04.1, kernel `7.0.0-38-generic`. Both machines were created under
`/home/koen/VirtualBox-Tests`, successfully started headlessly, and powered off
after the startup check. Guest operating systems have not yet been installed.

| VM | Attached installation medium |
| --- | --- |
| `ElevenRack-Arch` | `archlinux-2026.10.01-x86_64.iso` |
| `ElevenRack-CentOS-Stream10` | `CentOS-Stream-10-20261006.0-x86_64-boot.iso` |

The ISO files are in `build/vm-test/isos`; both SHA-256 checksums matched those
published by their respective distributions. They must remain at those paths
until installation finishes, or the DVD attachments must be updated.

Open VirtualBox, select a machine, and start it to install the guest OS. Start
with one guest at a time. USB controllers and device filters remain disabled
in this initial setup; no Eleven Rack passthrough or guest package tests have
been performed.

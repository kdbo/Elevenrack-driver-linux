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

## Installation reports

`tools/vm-guest-report.py` collects one JSON report per guest. It runs without
root inside the guest, after the packages are installed and the Rack is passed
through:

```sh
python3 vm-guest-report.py --audio-check
```

It records the distribution, kernel, package and DKMS state, the loaded
`snd-usb-audio` module, the Rack's devices and driver counters, PipeWire's
scheduling, the Monitor's diagnostics and the Rack's kernel messages. With
`--audio-check` it plays a 997 Hz tone on Main Out and records Line In L/R;
with a Main Out -> Line In cable or loopback the signal shows on Line In. The
report is written to the home folder.

Driver gap counters and xruns are expected in a guest: USB passthrough timing
is not representative. Judge only function: module loaded, counters present,
audio both ways.

## Results with 0.1.2 beta15

| Distribution | Kernel | PipeWire | DKMS | Rack | Counters | Audio check |
| --- | --- | --- | --- | --- | --- | --- |
| Arch Linux (2026-10-21) | 7.2.11-arch1-1 | 1.6.9 | installed | detected | yes | signal on Line In (0.058) |
| Fedora 44 Workstation (2026-10-21) | 7.2.11-200.fc44 | 1.6.9 | installed | detected | yes | signal on Line In (0.058) |
| CentOS Stream 10 (2026-10-21) | 6.12.0-277.el10 | 1.6.9 | installed | detected | yes | signal on Line In (0.059) |

**Arch:** PipeWire first ran with normal scheduling (`TS`): Arch lists
`rtkit` only as an optional PipeWire dependency, and the guest had neither
`rtkit` nor `realtime-privileges`. After `sudo pacman -S rtkit` and a reboot,
PipeWire's `data-loop.0` ran at `FF 88`, its clients at `FF 83`. The Arch
package depends on `rtkit` from beta16. The Monitor's remaining warning, that
`ksoftirqd` runs at normal priority, is expected without `threadirqs`.

**Fedora 44:** the package contains driver sources only for the kernels it was
built for (`7.2.11-200.fc44` and `6.19.10-300.fc44`), and its installation
script builds only for the running kernel. The guest ran `7.2.9-201.fc44`, so
the installation registered DKMS but built nothing, with only a warning. After
`sudo dnf install kernel-7.2.11-200.fc44 kernel-devel-7.2.11-200.fc44` and a
reboot, DKMS built the driver at boot. A `0.1.2~beta8` DKMS entry left from an
earlier test showed as `broken`; `dkms remove` refuses a broken entry, so
remove it with `sudo rm -rf /var/lib/dkms/eleven-rack/0.1.2~beta8`. PipeWire ran at
`RR 20` through RTKit, enough without `threadirqs`. Fedora's kernel does not
provide `srcversion` for loaded modules; `eleven_stats` and the module path
under `extra/` show that the patched driver is loaded. The unsigned module
taints the kernel; the guest has no Secure Boot.

**CentOS Stream 10:** as on Fedora, beta15 only builds for its bundled kernel
(`6.12.0-277.el10`); the guest ran `6.12.0-273.el10` and was updated first.
CRB and EPEL were enabled as in the installation guide. PipeWire ran at
`RR 20` through RTKit. The counters in the report were read before its audio
check and are therefore all zero. A `0.1.2~beta8` DKMS entry from an earlier
test was again `broken`.

**Kernel sources for other kernels (after beta15):** the fetcher
`packaging/fetch-fedora-kernel-source.py`, used by DKMS for kernels without
bundled sources, was run in the guests on 2026-10-21 for kernels beta15 cannot
build: `7.2.9-101.fc43` (signed copy removed by Fedora, rebuilt from the
signature cache) and `6.12.0-273.el10` (signed source RPM from the CentOS
mirror). Both passed `rpm --checksig` and gave `sound/usb` with the spec's
patches. A full DKMS installation with these changes needs a new package set.

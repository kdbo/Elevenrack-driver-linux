# Ubuntu package (experimental)

For step-by-step installation of released driver and editor packages, see
[the installation guide](../INSTALLATION.md). This document covers package
construction and kernel compatibility in more detail.

One `eleven-rack-driver_*_all.deb` contains the driver control panel, logo,
application-menu launcher, routing configuration, and DKMS build instructions.
The rig editor is a separate application and is not included.

## Compatibility

The package targets Ubuntu 24.04 LTS and newer. This is a compatibility target,
not a claim that every newer Ubuntu release or kernel has been tested.
The Python/GTK application does not depend on a particular kernel version.
WirePlumber 0.4 gets a Lua fragment; 0.5 and newer get a SPA-JSON fragment.

The release/kernel mapping is pinned in `packaging/ubuntu-kernels.json`, with
links to the official release notes. Ubuntu 26.10 is a development release as
of 2026-10-08; its final release is scheduled for 2026-10-15. Its 7.3 beta
kernel can be build-tested now, but final-release validation remains pending.

Ubuntu 24.10, 25.04 and 25.10 are older interim releases. If their configured
APT mirrors no longer provide dependencies, use Ubuntu's appropriate archive
repositories. This package does not rewrite APT sources or upgrade Ubuntu.

The driver replaces the system `snd-usb-audio` module using DKMS's module
override mechanism, affecting all devices handled by that module. DKMS builds
from the distro's kernel sources and matching headers rather than
using a precompiled module. The driver adaptations work with the older quirk
initializers used by Linux 6.8 as well as the Linux 7.0 layout. Unrecognized
source layouts or existing Eleven Rack support cause a build failure.
For kernel 7.3, the build helper preserves ALSA's newer generic selector-write
error handling while adding the Eleven Rack-specific error propagation.

The following **amd64 kernel builds** have passed, with matching Ubuntu source
and headers. These are build results, not full Ubuntu installation or hardware
validation. Exact versions, module vermagic and fingerprints are recorded in
[`compatibility-builds.json`](compatibility-builds.json).

| Ubuntu | Tested kernel | Build |
| --- | --- | --- |
| 24.04 LTS | 6.8.0-31-generic | Passed |
| 24.10 | 6.11.0-8-generic | Passed |
| 25.04 | 6.14.0-15-generic | Passed |
| 25.10 | 6.17.0-5-generic | Passed |
| 26.04 LTS | 7.0.0-38-generic | Passed |
| 26.10 beta | 7.3.0-9-generic | Passed; final release pending |

All builds ran on the Ubuntu 26.04 development host with GCC 15. Older/newer
kernel packages can report compiler-version differences; native builds using
each Ubuntu release's default toolchain still need validation. HWE/OEM/other
architectures and all future kernel updates are not covered by this table.

Headers and sources must match the kernel being built. Starting with beta5,
HWE kernels use the exact source package and version recorded by the installed
kernel packages (for example `linux-hwe-7.0=7.0.0-38.38~24.04.4`). Missing
standard kernel source archives also use this automatic retrieval route.
The helper derives temporary `deb-src` entries from the configured repositories,
uses isolated APT lists/caches with signature and checksum verification, and
applies the Ubuntu source changes before caching only `sound/usb` under
`/var/cache/eleven-rack/kernel-sources/`. System repository files are not edited.

The first build for each fetched source version needs network access and several
GB of temporary disk space; the HWE 7.0 test downloaded approximately 258 MB.
Subsequent builds of that source version use the cache. An unavailable exact
source version or a repository/network failure stops the build with an error;
the helper never substitutes another kernel version. Source downloads happen
during the DKMS build, including package configuration and kernel updates.
OEM, mainline and custom kernels remain unvalidated; matching headers must
already be installed. No recursive package installation is performed by DKMS.

## Build

```sh
python3 tools/build-deb.py
```

The package is written to `build/packages/`. No root is needed to build it.

## Install

Save work and close audio applications. Install the local package through APT
so dependencies are resolved:

```sh
sudo apt install ./build/packages/eleven-rack-driver_0.1.1~beta3_all.deb
```

For an HWE kernel, ensure its exact headers are installed:

```sh
sudo apt install linux-headers-$(uname -r)
```

Then reboot and open **Eleven Rack Control** in the application menu, or run
`eleven-rack-control gui`. GUI settings do not require root. Installation does
not unload a live audio module, restart audio services, alter REAPER settings,
or overwrite per-user configuration. Existing user WirePlumber overrides take
precedence over package configuration and should be reviewed if routing differs.

With Secure Boot enabled, follow DKMS/Ubuntu's MOK enrollment instructions
when prompted. Do not disable Secure Boot to use this package. A module can
build successfully but fail to load if its signing key is not trusted.

## Updates and removal

DKMS rebuilds for kernel updates when matching sources and headers are available.
For HWE kernels, an uncached source version is fetched automatically as above.
Check `dkms status` after updates. DKMS prints the build-log path on failure;
depending on its version, logs are under
`/var/lib/dkms/eleven-rack/<version>/build/` or the kernel/architecture `log/`
subdirectory beneath that version.

```sh
sudo apt remove eleven-rack-driver
```

Removal unregisters the DKMS module. Reboot to return to the distribution's
driver: an already loaded module is never forcibly replaced. Use `apt purge`
instead of `remove` if you also want package-owned routing configuration deleted.

## Release status

This is a local beta artifact, not a published release. Monitoring switching
still awaits verified protocol details; clock selection has known limitations
documented in `interface-settings.md`. Full hardware testing on Ubuntu 24.04
is required before advertising production support. Original tools and the panel
are MIT-licensed; original kernel patches and the patch helper use GPL-2.0-or-later.
See [LICENSING.md](../LICENSING.md) and [credits](../CREDITS.md) for scope and
attribution. Release maintainer details and licensing
of any future imported components must be reviewed before public release.

Build validation: the package build helper compiled successfully against the
Ubuntu 24.04 `6.8.0-31-generic` sources/headers and Ubuntu 26.04
`7.0.0-38-generic` sources/headers. The 6.8 check used GCC 15 on the development
host and emitted a compiler-version warning; a native Ubuntu 24.04 installation
with its GCC 13 toolchain remains to be tested. No 6.8 module was loaded on the
7.0 host. Packaging build tests do not establish hardware or Secure Boot support.
An actual DKMS 3.2.2 add/build run also succeeded in an isolated temporary tree
against 7.0.0-38, including signing with a temporary test certificate. Neither
the package nor its module was installed into the running system.

## Reproduce the build matrix

Place the source, common headers and amd64 generic headers `.deb` files with
the exact versions from `packaging/ubuntu-kernels.json` in a download cache.
Then run, for example:

```sh
python3 tools/check-kernel-builds.py --releases 24.10 25.04 25.10 26.10 \
  --cache /tmp/eleven-package-check --work-dir /tmp/eleven-ubuntu-matrix
```

The checker uses the same build helper shipped in the `.deb`, checks module
vermagic, records SHA-256 fingerprints of the input packages and output module,
and saves per-release logs and JSON results in `build/compatibility/`.
It does not install the `.deb`, load a module, or modify the running system.
Full Ubuntu installation, Secure Boot and hardware validation remain separate.

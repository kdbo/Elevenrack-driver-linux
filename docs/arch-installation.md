# Arch Linux: build and download two packages

Use the GitHub **Arch package set** workflow to produce exactly two native Arch
packages, without publishing a release:

- `eleven-rack-driver`: the patched DKMS driver, Control, PipeWire latency
  backend with the Ubuntu measurement defaults, and all audio/service configuration.
- `eleven-rack-editor-linux`: the Electron editor and Linux MIDI bridge.

## Manual GitHub build

1. Open **Actions → Arch package set → Run workflow** and select `main`.
2. To match the VM with kernel `7.2.9-arch1-1`, enter **`7.2.9.arch1-1`** in
   `kernel_package_version`. This field takes the `pacman -Q linux` package
   version, not the `uname -r` release string. Leave it empty for current stable
   Arch `linux` and `linux-headers`.
3. After a successful run, download **arch-package-set** under **Artifacts**.
   Sign in to GitHub to download; the artifact is retained for 30 days.

GitHub builds in an Arch container. It installs matching kernel/header packages,
checks out their exact official Arch kernel packaging tag, verifies the upstream
source checksums and PGP signatures with `makepkg`, and runs the distribution's
`prepare()` step. It does not build a complete kernel image. The patched USB
module is compiled against those headers and its vermagic is checked. The
container's `uname -r` is never used to choose the Arch target, because containers
share the Ubuntu runner's host kernel.

The backend is built for the installed Arch PipeWire version. The driver package
pins `linux`, `linux-headers`, `pipewire` and `pipewire-audio` to those build inputs.
The downloadable set includes `package-target.json`, the kernel packaging commit,
module vermagic, installation instructions and `SHA256SUMS`. The checker rejects
extra packages, mismatched versions, and missing driver, Control, backend or
editor components.

The previous separate Control/DKMS/backend Arch packages are compatibility
components provided by the combined driver package; do not install the separate
backend artifact alongside the combined set.

## Install in the Arch VM

Extract the artifact ZIP, open a terminal in that folder and run:

```sh
sha256sum --check SHA256SUMS
uname -r
pacman -Q linux linux-headers pipewire
sudo pacman -U ./*.pkg.tar.zst
```

Check that your kernel and PipeWire versions match `README.txt` and
`package-target.json`. Pacman installs normal Arch runtime dependencies; the
artifact contains only the two Eleven Rack packages. If Arch's repositories
have moved to a newer PipeWire release, rebuild the set for the updated machine
rather than mixing an old backend with new libraries. The manual kernel input
selects the kernel only; PipeWire comes from the current Arch repository.

Review DKMS output before rebooting. Then start:

```sh
eleven-rack-control gui
eleven-rack-editor-linux
```

No Eleven Rack USB passthrough is enabled by the pipeline. Kernel modules are
compiled and packaged, not loaded on GitHub's runner. Hardware audio and physical
latency on Arch remain unvalidated. The Ubuntu measurement corrections are the
agreed defaults; physical validation and long regression tests can follow on an
actual Arch machine with the Eleven Rack connected.

## Kernel updates and removal

The package contains prepared sources for one exact stock Arch `linux` release;
DKMS is restricted to it. Rebuild the package set before updating the pinned
kernel or PipeWire. This workflow currently targets x86_64 and stock `linux`,
not `linux-lts`, custom kernels or ARM.

The module replaces `snd-usb-audio`, also used by other USB audio devices.
Installation/removal uses standard DKMS hooks, followed by an initramfs refresh
with `mkinitcpio` or `dracut` when available. Secure Boot module signing must be
configured on a machine where Secure Boot is enabled. After removal, reboot to
restore the distribution module; check that no user-modified Eleven Rack module
options remain in `/etc/modprobe.d`.

## Local recipe inputs (optional)

The same workflow script can run as a regular user on an Arch build machine with
its dependencies installed:

```sh
bash tools/build-arch-package-set.sh
```

It creates the packages under `build/arch-set`. Fresh build directories are
required; the script refuses an existing kernel checkout rather than replacing
it. The package preparation helper also accepts verified, distribution-prepared
sources and a backend already built on Arch:

```sh
python tools/prepare-arch-package.py \
  --kernel-source /path/to/prepared/arch/kernel \
  --kernel-release 7.2.9-arch1-1 \
  --linux-package-version 7.2.9.arch1-1 \
  --backend-build build/latency \
  --output build/arch-driver
```

See [portable backend builds](backend-building.md) for source/version checks and
correction provenance. Neither local staging checks on Ubuntu nor a successful
GitHub build establishes actual hardware audio performance.

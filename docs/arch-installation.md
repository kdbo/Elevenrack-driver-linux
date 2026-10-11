# Arch Linux local package preparation

The initial recipe builds separate `eleven-rack-control` and
`eleven-rack-driver-dkms` packages. It is a local build recipe, not a published
AUR package. Arch installation and hardware validation are still required.
The Electron editor is not included in this first recipe. The PipeWire latency
backend has a separate [portable build and package workflow](backend-building.md),
including an Arch package. It reuses the Ubuntu measurement corrections as
defaults; physical latency on Arch has not yet been validated.

## Prepare the matching kernel sources

Install Arch build tools and the headers for the selected kernel, for example
`base-devel`, `dkms`, and `linux-headers` for the stock `linux` kernel. For LTS,
use its matching headers instead.

Obtain the official Arch kernel packaging revision that produced your target
kernel. Follow its source verification and `prepare()` step to obtain clean
kernel sources with Arch's patches applied. Use the official
[kernel packaging repository](https://gitlab.archlinux.org/archlinux/packaging/packages/linux)
and [package creation guide](https://wiki.archlinux.org/title/Creating_packages).
Headers alone are insufficient. Do not substitute Ubuntu sources or an
unpatched kernel.org tree.

The package preparation tool expects that prepared tree and the exact target
kernel release (the value of `uname -r` when building for the running kernel):

```sh
python tools/prepare-arch-package.py \
    --kernel-source /path/to/prepared/arch/kernel \
    --kernel-release "$(uname -r)" \
    --output build/arch
cd build/arch
makepkg -s
```

Run `makepkg` as a regular user. The preparation tool creates two local source
archives and a PKGBUILD with their SHA-256 checksums. It does not retrieve or
authenticate kernel sources; the official kernel preparation step must do that.
It also cannot prove that a manually supplied release string matches the
supplied sources. That relationship must be established before packaging.

Inspect the resulting packages, then install both with `pacman -U` using their
exact filenames. Review DKMS output before rebooting. Control requires a
PipeWire/WirePlumber desktop and PipeWire's JACK compatibility. The driver
package follows [Arch's DKMS packaging approach](https://wiki.archlinux.org/title/DKMS_package_guidelines)
rather than invoking DKMS from a custom package installation script.

## Kernel updates and validation

This first driver package contains clean sources for one exact kernel release.
DKMS rejects other releases with an explanation rather than compiling against
mismatched sources. Prepare a new package when the kernel changes. Automatic
source retrieval and multiple concurrent kernel versions are not implemented.

The module replaces `snd-usb-audio`, which also serves other USB audio devices.
Validate installation, reboot activation, audio, a kernel update, removal,
restoration of the distribution module, and Secure Boot signing where enabled
on an Arch test machine before distributing the packages. Check initramfs
handling if that module is included in the boot image.

Local checks on the Ubuntu development host can verify recipe syntax,
checksums, and package staging; they do not constitute an Arch package build
or an Arch hardware test.

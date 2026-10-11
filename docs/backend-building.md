# Building the latency backend on Linux distributions

The Eleven Rack backend builds against a specific upstream PipeWire release.
It replaces the PCM source/sink/device factories and delegates enumeration,
ACP and MIDI factories to the distribution's original ALSA plugin. The plugin
path is detected on the build machine, including Debian multiarch, Arch
`/usr/lib`, and RPM `/usr/lib64` layouts. Build on the target distribution and
architecture; a binary built on Ubuntu is not a universal Linux binary.

The same correction configuration is shipped on every distribution. Its values
come from Ubuntu measurements with PipeWire 1.6.2; six small high-rate profiles
are estimates. These defaults are not hardware validated on Arch or RPM
systems. A VM checks compilation, factory loading and packaging. Physical
latency and long audio regression tests require the Eleven Rack connected to a
physical machine running the target distribution.

## Requirements

Python 3.12 or newer, a C compiler, ALSA development headers, `patch`, and the
installed PipeWire ALSA plugin are required. WirePlumber 0.5 or newer and the
patched Eleven Rack kernel driver with `eleven_delay_hires` are runtime
requirements. Stock `snd_usb_audio` does not implement that option.

Typical build dependencies:

```sh
# Ubuntu/Debian (in addition to a PipeWire/WirePlumber desktop)
sudo apt install build-essential python3 libasound2-dev patch pkg-config libspa-0.2-dev

# Arch
sudo pacman -S --needed base-devel python alsa-lib pipewire pipewire-audio wireplumber

# Fedora
sudo dnf install gcc python3 alsa-lib-devel patch pkgconf-pkg-config pipewire-devel pipewire-alsa wireplumber rpm-build
```

## Build and check

```sh
python3 tools/build-latency-backend.py
python3 tools/check-latency-backend.py
```

The builder detects the installed PipeWire version. The source catalog pins
upstream archives and SHA-256 checksums for 1.6.2 and 1.6.9. Downloads use HTTPS,
the archive checksum is checked before extraction, and patching refuses fuzzy
matches. Upstream archives omit distribution-specific source changes; if a
distribution patches these ALSA files, review those changes before deployment.

A local archive or a different source release can be selected explicitly:

```sh
python3 tools/build-latency-backend.py \
  --pipewire-version 1.6.9 --archive /path/to/pipewire-1.6.9.tar.gz

# For an unlisted version, supply an independently verified checksum:
python3 tools/build-latency-backend.py \
  --pipewire-version X.Y.Z --archive /path/to/pipewire-X.Y.Z.tar.gz \
  --sha256 VERIFIED_SHA256
```

New PipeWire versions may require a patch update. A successful build and
factory check do not establish physical latency accuracy. Use
`--spa-plugin-dir /path/to/spa-0.2` when automatic detection is ambiguous;
this must be the original system directory, not the Eleven Rack override.
Use `--output` to keep builds for different targets separate.

## Packages

Run packaging on the same distribution with its matching PipeWire installed:

```sh
python3 tools/build-latency-package.py --format deb   # Ubuntu/Debian
python3 tools/build-latency-package.py --format arch  # Arch; regular user
python3 tools/build-latency-package.py --format rpm   # Fedora/RPM
python3 tools/build-latency-package.py --format tar   # payload for other distro packagers
```

Arch requires `makepkg`/`fakeroot`; RPM requires `rpmbuild`; Debian requires
`dpkg-deb`. Packages are written to `build/packages`, with individual SHA-256
files. Native packages pin the installed PipeWire package version to prevent
silent use after an incompatible PipeWire update; rebuild the backend package
with the update. The build metadata records source, patch and binary checksums,
architecture, PipeWire version, plugin path and correction provenance.

Install the matching patched driver first. Debian uses `eleven-rack-driver`;
Arch/RPM packages require `eleven-rack-driver-dkms`. The RPM backend recipe does
not provide an RPM kernel-driver package. Install the native backend with
`apt install ./FILE.deb`, `pacman -U FILE.pkg.tar.zst` or `dnf install ./FILE.rpm`.
The tarball is a staged filesystem payload for packaging on other distributions,
not a universal binary or an automatic installer. It needs the same runtime
requirements and target paths as the native packages.

The packages install the correction rule, the kernel module option and systemd
user service overrides for PipeWire and WirePlumber. Debian/RPM refresh the
initramfs using available native tooling; Arch refreshes it with `mkinitcpio`
when available. Restart the audio session or reboot after installation or
removal. Systems without systemd must configure their audio service environment
with the `SPA_PLUGIN_DIR` value recorded in the package's service overrides.

The compatibility commands `tools/build-latency-backend.sh` and
`tools/build-latency-backend-deb.py` use the shared builders. The old positional
archive argument to the shell command still selects PipeWire 1.6.2.

## Pipeline

`.github/workflows/latency-backend.yml` builds and checks in Ubuntu, Arch and
Fedora containers and uploads native packages, staged tarballs, checksums and
build metadata. It runs for relevant pull requests, pushes to main, release
tags and manual dispatch. It publishes build artifacts only; it does not install
on the user's host or attach the Eleven Rack. An unknown PipeWire version fails
with an explicit source/checksum requirement rather than guessing compatibility.
Research measurements remain in the external archive and are not build inputs.

To build without a release, open the GitHub repository's **Actions** tab, select
**Latency backend packages**, click **Run workflow**, and select the branch.
After the run completes, open it and download the ZIP files under **Artifacts**:
`latency-backend-ubuntu`, `latency-backend-arch`, and `latency-backend-fedora`.
They contain the native packages, tar payloads, checksums and build metadata,
and remain available for 30 days. Downloading artifacts requires signing in to
GitHub. Manual runs do not create a release or a tag. The separate **Build and
release** workflow can also run manually; its release job only runs on tag pushes.

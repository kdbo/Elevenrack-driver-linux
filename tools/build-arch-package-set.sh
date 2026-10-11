#!/bin/bash
# Run as an unprivileged builder inside Arch, with linux and matching headers installed.
set -euo pipefail
if [ "$(id -u)" -eq 0 ]; then
    echo 'Run as a regular user; makepkg refuses root.' >&2
    exit 1
fi
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo"
mkdir -p build/arch-set build/arch-kernel-check
linux_version=$(pacman -Q linux | awk '{print $2}')
header_version=$(pacman -Q linux-headers | awk '{print $2}')
[ "$linux_version" = "$header_version" ] || { echo 'linux and linux-headers must match' >&2; exit 1; }
headers_file=$(pacman -Ql linux-headers | awk '$2 ~ /\/include\/config\/kernel.release$/ {print $2}')
[ -f "$headers_file" ] || { echo 'Cannot locate installed Arch kernel headers' >&2; exit 1; }
headers=${headers_file%/include/config/kernel.release}
kernel_release=$(cat "$headers_file")
# Do not use uname here: a CI container shares the Ubuntu runner's kernel.
source_tag=${linux_version#*:}
git clone --depth 1 --branch "$source_tag" \
    https://gitlab.archlinux.org/archlinux/packaging/packages/linux.git build/arch-kernel-packaging
(
    cd build/arch-kernel-packaging
    makepkg --printsrcinfo > package.SRCINFO
    source_version=$(awk '$1 == "pkgver" {v=$3} $1 == "pkgrel" {r=$3} END {print v "-" r}' package.SRCINFO)
    [ "$source_version" = "$source_tag" ] || { echo 'Arch packaging tag/version mismatch' >&2; exit 1; }
    mapfile -t signing_keys < <(awk '$1 == "validpgpkeys" {print $3}' package.SRCINFO)
    [ "${#signing_keys[@]}" -gt 0 ] || { echo 'Kernel recipe declares no signing keys' >&2; exit 1; }
    gpg --batch --keyserver hkps://keyserver.ubuntu.com --recv-keys "${signing_keys[@]}"
    # makepkg checks the official source checksums and signatures, then runs prepare().
    # Kernel documentation/full-image build dependencies are unnecessary for prepare().
    makepkg --nodeps --nobuild --noconfirm
)
prepared=$(python3 - "$kernel_release" <<'PY'
from pathlib import Path
import sys
matches = [p.parent for p in Path('build/arch-kernel-packaging/src').glob('*/version')
           if p.read_text().strip() == sys.argv[1] and (p.parent / 'sound/usb/Makefile').is_file()]
if len(matches) != 1:
    raise SystemExit('Prepared Arch kernel release does not match installed headers')
print(matches[0].resolve())
PY
)
python3 tools/build-latency-backend.py
python3 tools/check-latency-backend.py
python3 tools/prepare-arch-package.py --kernel-source "$prepared" --kernel-release "$kernel_release" \
    --linux-package-version "$linux_version" --backend-build build/latency --output build/arch-driver
(
    cd build/arch-driver
    makepkg --nodeps --cleanbuild --noconfirm
)
# Build the packaged DKMS sources, not a separate copy of the project driver.
(
    cd build/arch-kernel-check
    tar -xzf ../arch-driver/eleven-rack-source.tar.gz
    tar -xzf ../arch-driver/eleven-rack-kernel.tar.gz
    mkdir dkms-source
    cp eleven-rack-source/packaging/{build-driver-common.sh,prepare-driver.py,mixer-eleven-rack.h} dkms-source/
    cp eleven-rack-source/packaging/arch/build-driver.sh dkms-source/
    cp -a eleven-rack-kernel dkms-source/prepared-kernel
    bash dkms-source/build-driver.sh "$kernel_release" "$headers"
    modinfo -F vermagic kernel-source/sound/usb/snd-usb-audio.ko > vermagic.txt
    grep -Fq "$kernel_release " vermagic.txt
)
(
    cd editor
    npm ci
    editor_version=$(tr -d '\n' < ../VERSION)
    editor_version=${editor_version/\~/-}
    npm run pack -- --x64 --config.extraMetadata.version="$editor_version"
)
python3 tools/prepare-arch-editor.py --unpacked-dir editor/dist/linux-unpacked --output build/arch-editor
(
    cd build/arch-editor
    makepkg --nodeps --cleanbuild --noconfirm
)
cp build/arch-driver/eleven-rack-driver-*.pkg.tar.zst build/arch-set/
cp build/arch-editor/eleven-rack-editor-linux-*.pkg.tar.zst build/arch-set/
python3 tools/check-arch-package-set.py --directory build/arch-set --target build/arch-driver/package-target.json
cp build/arch-driver/package-target.json build/arch-set/
cp build/arch-kernel-check/vermagic.txt build/arch-set/
git -C build/arch-kernel-packaging rev-parse HEAD > build/arch-set/kernel-packaging-commit.txt
(
    cd build/arch-set
    sha256sum ./*.pkg.tar.zst > SHA256SUMS
)
printf 'Arch package set built for kernel %s\n' "$kernel_release"

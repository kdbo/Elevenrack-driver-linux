#!/bin/bash
# DKMS invokes this from its private build directory, never from the kernel tree.
set -euo pipefail
kernel_release=${1:?Kernel release required}
headers=${2:-/lib/modules/$kernel_release/build}
kernel_series=$(printf '%s\n' "$kernel_release" | sed -E 's/^([0-9]+\.[0-9]+).*/\1/')
if ! dpkg --compare-versions "$kernel_series" ge 6.8; then
    echo "Eleven Rack requires kernel 6.8 or newer." >&2
    exit 1
fi
source_archive=${ELEVEN_SOURCE_ARCHIVE:-/usr/src/linux-source-${kernel_series}.0.tar.bz2}
if [ ! -f "$source_archive" ]; then
    echo "Missing matching kernel sources: $source_archive" >&2
    echo "Install linux-source-${kernel_series}.0 and linux-headers-$kernel_release, then run sudo dkms autoinstall -k $kernel_release." >&2
    exit 1
fi
test -f "$headers/Makefile" || { echo "Missing headers: $headers" >&2; exit 1; }
build_root="$PWD"
source_root="$build_root/kernel-source"
# DKMS can retry builds. Clear only the generated subtree in its build directory.
python3 - "$source_root" <<'PY'
from pathlib import Path
import shutil
import sys
p = Path(sys.argv[1])
if p.name != 'kernel-source' or p.parent != Path.cwd():
    raise SystemExit('Unexpected generated-source path')
if p.exists():
    shutil.rmtree(p)
p.mkdir()
PY
tar -xjf "$source_archive" -C "$source_root" --strip-components=1 \
    "linux-source-${kernel_series}.0/sound/usb"
python3 "$build_root/prepare-driver.py" "$source_root/sound/usb"
compiler=${CC:-gcc}
auto_conf="$headers/include/config/auto.conf"
if [ -z "${CC:-}" ] && [ -f "$auto_conf" ]; then
    compiler_major=$(sed -nE 's/^CONFIG_GCC_VERSION=([0-9]+)$/\1/p' "$auto_conf")
    if [ -n "$compiler_major" ]; then
        compiler_major=$((compiler_major / 10000))
        if command -v "gcc-$compiler_major" >/dev/null 2>&1; then
            compiler="gcc-$compiler_major"
        fi
    fi
fi
make -C "$headers" M="$source_root/sound/usb" CC="$compiler" -j"${ELEVEN_BUILD_JOBS:-2}" modules

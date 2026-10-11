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
test -f "$headers/Makefile" || { echo "Missing headers: $headers" >&2; exit 1; }
build_root="$PWD"
script_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source_prefix=${ELEVEN_SOURCE_PREFIX:-linux-source-${kernel_series}.0}
if [ -z "${ELEVEN_SOURCE_ARCHIVE:-}" ]; then
    source_identity=$(python3 "$script_root/fetch-kernel-source.py" "$kernel_release" --identify)
    if [[ "$source_identity" == linux-hwe-* ]] || [ ! -f "$source_archive" ]; then
        source_archive=$(python3 "$script_root/fetch-kernel-source.py" "$kernel_release")
        source_prefix=linux-source
    fi
fi
test -f "$source_archive" || { echo "Missing kernel sources: $source_archive" >&2; exit 1; }
source_root="$build_root/ubuntu-source"
# DKMS can retry builds. Clear only the generated subtree in its build directory.
python3 - "$source_root" <<'PY'
from pathlib import Path
import shutil
import sys
p = Path(sys.argv[1])
if p.name != 'ubuntu-source' or p.parent != Path.cwd():
    raise SystemExit('Unexpected generated-source path')
if p.exists():
    shutil.rmtree(p)
p.mkdir()
PY
tar -xjf "$source_archive" -C "$source_root" --strip-components=1 \
    "$source_prefix/sound/usb"
exec bash "$script_root/build-driver-common.sh" "$kernel_release" "$headers" "$source_root/sound/usb"

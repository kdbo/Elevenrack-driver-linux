#!/bin/bash
# Build from explicitly supplied, distribution-prepared sound/usb sources.
set -euo pipefail
kernel_release=${1:?Kernel release required}
headers=${2:?Kernel build directory required}
usb_sources=${3:?Clean sound/usb source directory required}
script_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
python3 - "$kernel_release" <<'CHECK'
import re
import sys
match = re.match(r"^(\d+)\.(\d+)", sys.argv[1])
if not match or tuple(map(int, match.groups())) < (6, 8):
    raise SystemExit('Eleven Rack requires kernel 6.8 or newer.')
CHECK
test -f "$headers/Makefile" || { echo "Missing kernel build files: $headers" >&2; exit 1; }
source_root="$PWD/kernel-source"
# Copy into a private build subtree; never patch the supplied source tree.
python3 - "$usb_sources" "$source_root" <<'COPY'
from pathlib import Path
import shutil
import sys
source = Path(sys.argv[1]).resolve()
target = Path(sys.argv[2]).resolve()
if target.name != 'kernel-source' or target.parent != Path.cwd().resolve():
    raise SystemExit('Unexpected generated-source path')
if target == source or target in source.parents or source in target.parents:
    raise SystemExit('Source and generated build tree must not overlap')
if not (source / 'Makefile').is_file():
    raise SystemExit('Missing sound/usb sources')
if target.exists():
    shutil.rmtree(target)
shutil.copytree(source, target / 'sound/usb')
COPY
python3 "$script_root/prepare-driver.py" "$source_root/sound/usb"
compiler=${CC:-gcc}
auto_conf="$headers/include/config/auto.conf"
if [ -f "$auto_conf" ]; then
    echo "Target kernel preemption configuration (runtime scheduling checked separately):"
    sed -nE '/^CONFIG_PREEMPT(_RT|_DYNAMIC|_LAZY|_VOLUNTARY|_NONE)?=y$/p' "$auto_conf"
fi
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

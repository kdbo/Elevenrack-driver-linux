#!/bin/bash
set -euo pipefail
kernel_release=${1:?Kernel release required}
headers=${2:-/lib/modules/$kernel_release/build}
script_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
expected=$(cat "$script_root/prepared-kernel/kernel-release")
if [ "$kernel_release" != "$expected" ]; then
    echo "Prepared Arch sources are for $expected, not $kernel_release." >&2
    echo "Rebuild the Eleven Rack package with sources matching the new kernel." >&2
    exit 1
fi
exec bash "$script_root/build-driver-common.sh" "$kernel_release" "$headers" \
    "$script_root/prepared-kernel/sound/usb"

#!/bin/bash
set -euo pipefail
kernel_release=${1:?Kernel release required}
headers=${2:-/lib/modules/$kernel_release/build}
script_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source_root="$script_root/prepared-kernel"
expected=$(cat "$source_root/kernel-release")
if [ "$kernel_release" != "$expected" ]; then
    source_root="$script_root/prepared-kernels/$kernel_release"
fi
if [ ! -f "$source_root/kernel-release" ] || [ "$(cat "$source_root/kernel-release")" != "$kernel_release" ]; then
    echo "Prepared Fedora sources are for $expected, not $kernel_release." >&2
    echo 'Build an updated Eleven Rack package for this kernel.' >&2
    exit 1
fi
exec bash "$script_root/build-driver-common.sh" "$kernel_release" "$headers" \
    "$source_root/sound/usb"

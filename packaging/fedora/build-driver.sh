#!/bin/bash
set -euo pipefail
kernel_release=${1:?Kernel release required}
headers=${2:-/lib/modules/$kernel_release/build}
script_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# The package bundles sources for the kernels it was built with; any other
# kernel gets its sources from the signed source RPM of its kernel-devel.
source_root="$script_root/prepared-kernel"
if [ "$(cat "$source_root/kernel-release" 2>/dev/null)" != "$kernel_release" ]; then
    source_root="$script_root/prepared-kernels/$kernel_release"
fi
if [ -f "$source_root/kernel-release" ] && [ "$(cat "$source_root/kernel-release")" = "$kernel_release" ]; then
    usb_sources="$source_root/sound/usb"
else
    usb_sources=$(python3 "$script_root/fetch-fedora-kernel-source.py" "$kernel_release")
fi
exec bash "$script_root/build-driver-common.sh" "$kernel_release" "$headers" "$usb_sources"

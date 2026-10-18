#!/bin/bash
set -euo pipefail
kernel_release=${1:?Kernel release required}
headers=${2:-/lib/modules/$kernel_release/build}
script_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
bundled="$script_root/prepared-kernel"
# The package bundles sources for the kernel it was built with; any other Arch
# kernel gets its sources from the Arch recipe of the installed version.
if [ -f "$bundled/kernel-release" ] && [ "$(cat "$bundled/kernel-release")" = "$kernel_release" ]; then
    usb_sources="$bundled/sound/usb"
else
    usb_sources=$(python3 "$script_root/fetch-arch-kernel-source.py" "$kernel_release")
fi
exec bash "$script_root/build-driver-common.sh" "$kernel_release" "$headers" "$usb_sources"

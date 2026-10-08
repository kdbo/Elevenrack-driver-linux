#!/bin/bash
set -eu
repo_dir=$(cd -- "$(dirname -- "$0")/.." && pwd)
kernel_release=$(uname -r)
source_archive=/usr/src/linux-source-7.0.0.tar.bz2
source_dir="$repo_dir/build/kernel-source/linux-source-7.0.0"
usb_dir="$source_dir/sound/usb"
test -f "$source_archive"
test -d "/usr/src/linux-headers-$kernel_release"
mkdir -p "$repo_dir/build/kernel-source"
if [ ! -f "$usb_dir/Makefile" ]; then
    tar -xjf "$source_archive" -C "$repo_dir/build/kernel-source" linux-source-7.0.0/sound/usb
fi
if ! grep -q 'USB_DEVICE_VENDOR_SPEC(0x0dba, 0xb011)' "$usb_dir/quirks-table.h"; then
    patch -p1 -d "$source_dir" -i "$repo_dir/patches/0001-eleven-rack-uac2-experimental.patch"
fi
if ! grep -q 'case USB_ID(0x0dba, 0xb011)' "$usb_dir/format.c"; then
    patch -p1 -d "$source_dir" -i "$repo_dir/patches/0002-eleven-rack-rate-range-fallback.patch"
fi
if ! grep -q 'Endpoint pitch SET_CUR fails' "$usb_dir/quirks.c"; then
    patch -p1 -d "$source_dir" -i "$repo_dir/patches/0003-eleven-rack-disable-pitch-control.patch"
fi
if ! grep -q 'eleven_rack_selectors' "$usb_dir/mixer_maps.c"; then
    patch -p1 -d "$source_dir" -i "$repo_dir/patches/0004-eleven-rack-alsa-clock-selector.patch"
fi
if ! grep -q 'Eleven Rack clock writes must report' "$usb_dir/mixer.c"; then
    patch -p1 -d "$source_dir" -i "$repo_dir/patches/0005-eleven-rack-report-clock-write-errors.patch"
fi
python3 - "$usb_dir/Makefile" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
s = p.read_text()
marker = '# Toplevel Module Dependency'
if marker in s:
    p.write_text(s[:s.index(marker)] + 'obj-m := snd-usb-audio.o\n')
PY
make -C "/usr/src/linux-headers-$kernel_release" M="$usb_dir" CC=gcc-15 -j4 modules

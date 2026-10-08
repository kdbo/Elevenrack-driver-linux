#!/bin/bash
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo 'Run this script with sudo.' >&2
    exit 1
fi
repo_dir=$(cd -- "$(dirname -- "$0")/.." && pwd)
module_path="$repo_dir/build/kernel-source/linux-source-7.0.0/sound/usb/snd-usb-audio.ko"
test -f "$module_path"
module_kernel=$(modinfo -F vermagic "$module_path")
case "$module_kernel" in
    "$(uname -r) "*) ;;
    *) echo 'Built module does not match the running kernel.' >&2; exit 1 ;;
esac

# Unload normally; never force removal of a module used by an audio client.
modprobe -r snd_usb_audio
module_dependencies=$(modinfo -F depends "$module_path")
IFS=',' read -r -a dependencies <<< "$module_dependencies"
for dependency in "${dependencies[@]}"; do
    modprobe "$dependency"
done
if ! insmod "$module_path"; then
    modprobe snd_usb_audio
    exit 1
fi
echo 'Experimental module loaded for this session.'
# ALSA registration can finish after insmod returns.
for attempt in {1..20}; do
    if grep -q 'USB Audio.*playback.*capture' /proc/asound/pcm; then
        break
    fi
    sleep 0.25
done
cat /proc/asound/cards
cat /proc/asound/pcm

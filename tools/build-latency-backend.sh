#!/bin/sh
# Compatibility entry point for the portable builder (also accepts a local archive).
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ "$#" -gt 0 ] && [ "${1#--}" = "$1" ]; then
    archive=$1
    shift
    exec python3 "$repo/tools/build-latency-backend.py" --pipewire-version 1.6.2 --archive "$archive" "$@"
fi
exec python3 "$repo/tools/build-latency-backend.py" "$@"

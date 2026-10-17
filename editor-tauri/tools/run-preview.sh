#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
profile=debug
build_args=()
if [[ "${1:-}" == --release ]]; then
    profile=release
    build_args=(--release)
    shift
fi
binary="$project/src-tauri/target/$profile/eleven-rack-editor-tauri"
if [[ ! -x "$binary" ]]; then
    echo "Build first: cargo build ${build_args[*]} --locked --manifest-path editor-tauri/src-tauri/Cargo.toml" >&2
    exit 1
fi
# VS Code Snap exports GTK/schema paths belonging to its bundled desktop stack.
# Use the host stack for this host-native WebKitGTK application.
if [[ "${XDG_DATA_DIRS:-}" == *"/snap/code/"* || "${GSETTINGS_SCHEMA_DIR:-}" == *"/snap/code/"* ]]; then
    unset GTK_PATH GIO_EXTRA_MODULES
    export GSETTINGS_SCHEMA_DIR=/usr/share/glib-2.0/schemas
    export XDG_DATA_DIRS=/usr/local/share:/usr/share:/var/lib/snapd/desktop
fi
exec "$binary" "$@"

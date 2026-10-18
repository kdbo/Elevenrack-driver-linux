# Eleven Rack Editor — Tauri/Rust

The Linux editor shipped in the distribution packages since 0.1.2 beta13,
replacing the Electron editor. The existing HTML/CSS/JavaScript interface is
reused from `../editor/src`; the native application host, MIDI transport and
VU-meter levels are Rust. The editor and kernel audio driver remain separate
packages.

## Run

Install the [Tauri Linux prerequisites](https://v2.tauri.app/start/prerequisites/),
plus ALSA development headers. On Ubuntu:

```sh
sudo apt install cargo rustc rustfmt libwebkit2gtk-4.1-dev libgtk-3-dev libasound2-dev libayatana-appindicator3-dev librsvg2-dev libssl-dev patchelf
```

Rust 1.93 or newer and Node.js 22 are required. The Debian distribution Rust
packages on older Ubuntu releases may be too old; use a current Rust toolchain
in that case. From the repository root:

```sh
npm ci --prefix editor-tauri
cargo build --locked --manifest-path editor-tauri/src-tauri/Cargo.toml
editor-tauri/tools/run-preview.sh
```

Build and run the optimized release alongside the debug build:

```sh
cargo build --release --locked --manifest-path editor-tauri/src-tauri/Cargo.toml
editor-tauri/tools/run-preview.sh --release
```

Without `--release`, the launcher uses the debug build. Close the running editor
before switching builds; both use the same preview preferences and instance lock.

The in-app Manual opens this preview's `UserManual.txt`, with Tauri launch,
logging and captures-folder instructions. Development commands below are for
building the application; users of a prebuilt binary do not need npm or Cargo.

The launcher removes incompatible VS Code Snap GTK/schema search paths when
present. It applies only to the child application environment. A normal Tauri
GUI starts immediately; the existing firmware/readiness gates remain in-page.
With no Rack attached, select ports or use the retry/quit gate.

Useful validation modes:

```sh
# Enumerates MIDI ports without opening device connections.
editor-tauri/tools/run-preview.sh --list-midi
# Sends only a universal MIDI identity request; no patch/settings changes.
editor-tauri/tools/run-preview.sh --probe-midi
# Loads the interface, tests panel layout/IPC and exits after 12 seconds.
# MIDI remains disabled for the entire smoke-test process.
editor-tauri/tools/run-preview.sh --smoke-test --logs
```

Avoid running live MIDI sessions in both editors at the same time. The preview
owns its MIDI connections and closes them on disconnect/exit. Its single-instance
lock is separate from Electron's. Hotplug refreshes are handled by the Rust actor.

## Architecture and implemented scope

- `src-tauri/src/midi.rs`: native `midir`/ALSA discovery, pairing, connect/send/
  disconnect, receive callbacks, Rig Input confirmation and hotplug refresh.
  A dedicated actor serializes port operations; session IDs prevent stale
  frontend instances from closing or using a newer session's connections.
- `src-tauri/src/protocol.rs`: complete MIDI/SysEx validation, 7-bit decoding,
  TFX headers/body checks and filename guards.
- `src-tauri/src/files.rs`: TFX load, XML/ZIP bank import and export, bounded
  archive expansion, duplicate-slot checks and path traversal protection.
- `src-tauri/src/host.rs`: native dialogs, preview preferences, logging,
  captures, zoom and external-link opening.
- `frontend/native.js`: compatibility implementation of the existing renderer's
  `electronAPI`. The historical name avoids rewriting protocol/UI code. MIDI
  `WebSocket` calls are translated into ordered Tauri commands/events; no
  localhost server, Python bridge or Electron runtime is started.
- `src-tauri/build.rs`: stages the shared frontend and assets into ignored
  `.generated/`, adds the native adapter and corrects asset-relative paths.
  The source Electron interface is not rewritten by staging.

The existing amp/effect protocol, firmware acceptance gate, parameter pacing
and upload sequencing remain in the shared JavaScript. Tauri still uses a web
interface; this does not turn the visual controls into native Rust widgets.

The content policy explicitly permits the inline **style attributes** used by
this interface (`style-src-attr 'unsafe-inline'`). Tauri's style nonce injection
otherwise made WebKit ignore initial `display:none` and flex rows: all effect
panels appeared at once and knobs stacked vertically. Remote connections,
frames and embedded objects remain restricted. The GUI smoke test now verifies
initial hidden panels, a horizontal tone row, exclusive effect selection and
returning to the amp view. It does not exercise bypass buttons or send MIDI.

## Data and file behavior

Data uses Tauri's application-data directory. The identifier keeps its original
`io.github.kdbo.elevenrack.editor.tauri-preview` name so existing settings,
captures and logs stay where they are, normally:

```text
~/.local/share/io.github.kdbo.elevenrack.editor.tauri-preview/
  settings.json
  captures/
  logs/editor.log
```

Electron preferences are not imported or modified. Native dialogs authorize
bank file/folder access; a renderer-supplied path alone cannot select arbitrary
bank inputs or export destinations. Existing bank exports are refused rather
than overwritten. ZIP imports currently require one XML manifest and plain
filenames at the archive root, with at most 256 archive entries and 16 MiB
expanded data. These deliberately narrower preview limits need compatibility
review against real bank collections.

## Validation

```sh
node editor-tauri/tests/native.test.cjs
cargo test --locked --manifest-path editor-tauri/src-tauri/Cargo.toml
cargo fmt --manifest-path editor-tauri/src-tauri/Cargo.toml -- --check
```

Locally checked on 2026-10-16, Ubuntu / kernel `7.0.0-38-generic`:

- Native application compiles; Rust unit tests and frontend compatibility tests
  pass. Tests cover MIDI framing/session guards, TFX codec/headers, loose/ZIP
  bank round trips, traversal rejection, preference persistence and IPC ordering.
- WebKit starts and the shared editor initializes. A MIDI-disabled GUI check
  tests real computed layout and panel button behavior; JavaScript startup errors
  or a broken layout make this check fail instead of silently passing.
- Native ALSA discovery identifies the Rack Rig and External ports. A read-only
  Rust MIDI identity request receives
  `F0 7E 0F 06 02 13 0B 00 01 00 30 31 35 37 F7` (build `0157`).
- A development `.deb` can be generated with the command below. It is not
  installed by the build and uses the separate preview identity. The package
  declares ALSA alongside the generated GTK/WebKit runtime dependencies.

The CI workflow repeats build/tests and runs the GUI check under Xvfb with MIDI
disabled. It is prepared here; remote CI execution has not been validated.

## Remaining acceptance work

This preparation is not yet full hardware/UI parity certification. In particular:

- Exercise every amp/effect/cab panel, tuner, patch capture, bank scan and device
  reconnect in a full live session; check WebKit rendering beyond the layout test.
- Validate complete SysEx rig reads and uploads, pacing and long bank transfers
  on hardware. Only discovery and the small identity reply have been checked
  live; do not infer large-message integrity from that test.
- Multiple Racks are grouped by native ALSA card association and physical USB
  location. Choose a Rack at startup or use the device selector; switching reloads
  the editor to clear patch caches. Save edits before switching. Moving a Rack to
  another USB port changes its saved identity. Hardware switching acceptance is
  still pending.
- Automatic release updates are unavailable, avoiding offers to install an
  Electron release over it. Windows/macOS-specific watchdog and MIDI-stack hooks
  have Linux compatibility responses; no Windows/macOS port is claimed here.
- The VU meters show the connected Rack's Rig L/R capture channels through
  `pw-record` (PipeWire). Computer playback and inputs that are not the Rig Input
  do not move them. Without `pw-record` they report no audio source.
- Review window-state persistence, optional startup flags and accessibility.

Build a development package:

```sh
npm --prefix editor-tauri run build -- --debug --bundles deb
```

Artifacts are under `editor-tauri/src-tauri/target/debug/bundle/deb/`. Debug builds
are for review and testing; release packages for each distribution are built by
the project's package pipeline.

The shared frontend/assets retain their upstream MIT notices and attribution to
Charles Wardick and the macOS port by Damilola Olalere. See `../editor/LICENSE`
and `../editor/NOTICE`, also included with the editor bundle.

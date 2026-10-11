# Tools

The obsolete latency experiments and temporary calibration bridge were moved
outside this repository to `/home/koen/eleven-rack-tools-archive/2026-10-11`.
The exact file list and checksums are in
[`docs/obsolete-tools-archive.json`](../docs/obsolete-tools-archive.json).
Historical reports may refer to their original paths. Restore an archived tool
to its original location before using it; most resolve the repository root from
their own location.

Current tools serve these workflows:

- Interface controls: `eleven-rack-settings.py`, `eleven-rack-panel.py`.
- Kernel/package builds and checks: `build-*`, `check-*`, `test-kernel-source.py`.
  `build-arch-package-set.sh` assembles the complete two-package Arch artifact;
  see [Arch build/download instructions](../docs/arch-installation.md).
  `fetch-latency-sources.py` verifies the bundled PipeWire archives;
  `build-deb.py --backend-sources build/latency-sources` assembles one reusable
  Ubuntu driver. `install-latency-backend.py` detects PipeWire and builds its
  backend automatically. The private workflow adds the Editor as the second package.
  See [Ubuntu build/download instructions](../docs/ubuntu-installation.md).
- Latency backend: `build-latency-backend.py`, `build-latency-package.py`,
  `check-latency-backend.py`, `spa-eleven-alsa.c`, `activate-profile-corrections.py`.
  See [multi-distribution builds and packages](../docs/backend-building.md).
- Current calibration: `test-full-latency-matrix.py`, `record-latency-status.py`,
  `jack-loopback.c`, `analyze-jack-loopback.py`, `latency-correlation.c`,
  `calculate-matrix-corrections.py`, `estimate-small-buffer-corrections.py`.
- REAPER profile helpers and their tests; monitor controls and their probes;
  editor rig-upload validation.

Latency research reports, measurements and experimental patches are archived
outside the repository in `/home/koen/eleven-rack-tools-archive/2026-10-11/docs`.
That directory contains `manifest.json` with original paths and SHA-256 checksums,
and can later be imported into a private repository. Relative links between the
archived documents retain their original layout.

Small high-rate buffers are selectable; six profiles use estimated corrections.
The archived `latency-small-buffer-estimates.json` and
`latency-profile-corrections.json` contain the research tables. Restore required
research inputs under `docs/` before rerunning calibration analysis tools; these
paths are ignored by Git. The backend package does not require or ship these
reports. Its build patch is in `packaging/pipewire-eleven-latency.patch`.

## Long-duration audio regression

`test-audio-regression.py` runs sine wave, white noise and pink noise tests on
selected profiles for 1, 5, 15 or 30 minutes. See
[instructions and limitations](../docs/audio-regression-tests.md).
`analyze-loopback-regression.py` analyzes the recorded audio;
`test-regression-analysis.py` checks the detector using synthetic faults.

## Control channel meters

`eleven-rack-meters.c` is the read-only JACK peak meter for eight capture channels
and six playback monitor ports. Control builds this small helper once in the
user cache and runs it only while at least one Channels group is open. The helper
does not output audio. Values are digital peak levels in dBFS; hardware direct
monitoring and analog output gain are not included in the playback monitor.
The nightly regression runner and tuning tool share
`/tmp/eleven-rack-regression-<uid>.lock`; Control pauses the meters while that lock
is held.

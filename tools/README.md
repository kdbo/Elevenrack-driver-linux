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
  See [installation instructions](../INSTALLATION.md#ubuntu-2404-and-newer); Ubuntu build documentation is maintained in the private build repository.
  `prepare-fedora-kernel.py` prepares Fedora's matching signed source RPM;
  `build-fedora-package-set.py` creates the complete driver and Editor RPMs.
  `check-fedora-package-set.py` verifies their payloads and version dependencies.
  Fedora installation and dependency documentation is maintained in the private build repository.
  The CentOS Stream 10 workflow reuses these RPM tools in its own container;
  CentOS installation and dependency documentation is maintained in the private build repository.
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
`smi-counter.c` and `platform_noise.py` record firmware SMIs during each matrix
and mark callback stalls and faults that coincide with them (`platform` in
`matrix.json`); `test-platform-noise.py` checks that attribution. The counter
needs the helper installed with `cap_perfmon`; see the regression instructions.

For physical white-noise loopbacks, `analyze-white-noise-path.py RECORDING.raw`
provides a separate offline diagnosis of stationary analog filtering and timing
faults. First build its helper with
`cc -shared -fPIC -O2 tools/loopback-filter.c -o build/latency/libloopback-filter.so -lm`.
The existing correlation helper must also be built, as for the regression tool.
The diagnostic estimates one fixed 65-tap response from 0.2 seconds and validates
it on independent data. It retains raw correlation results and rejects waveform
mismatches, delay steps over eight frames, recorded callback xruns and observed
PCM restarts. It does not recalibrate after a timing step. Missing PCM evidence
is reported as unavailable. Consecutive 512-sample residual blocks complement sparse alignment windows;
finite thresholds and the excluded startup/tail do not prove sample-perfect audio.
Results are saved separately as `.white-path.json`; the standard regression pass
criteria are not changed. Run `python3 tools/test-white-noise-analysis.py` for
synthetic filtering, discontinuity and calibration-failure checks.
`test-audio-regression.py --analog-white-noise` enables this diagnostic for its
white-noise measurements and builds the helper. Other signals retain their
existing analysis; raw white-noise scores are retained separately.

## Control channel meters

`eleven-rack-meters.c` is the read-only JACK peak meter for eight capture channels
and six playback monitor ports. Control builds this small helper once in the
user cache and runs it only while at least one Channels group is open. The helper
does not output audio. Values are digital peak levels in dBFS; hardware direct
monitoring and analog output gain are not included in the playback monitor.
The nightly regression runner and tuning tool share
`/tmp/eleven-rack-regression-<uid>.lock`; Control pauses the meters while that lock
is held.

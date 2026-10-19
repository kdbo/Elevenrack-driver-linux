# Long-duration loopback regression

`tools/test-audio-regression.py` uses the existing JACK/PipeWire loopback tool. Each profile gets a fresh audio start, six seconds of silent warmup, and then a sine wave (997 Hz), deterministic white noise or pink noise. The default series covers all 24 sample-rate/buffer combinations, three signals, and 1, 5, 15 and 30 minutes per signal. That is 61.2 hours of signal, plus startup time. High sample rates with small buffers are included so that possible faults are recorded.

## Connecting and starting

Temporarily connect **Main Out L to Line In L**. Do not use a microphone input. Keep the analog input clean: no effects or processing in the loopback path. Close REAPER and other audio applications. The test outputs a peak level of about -30 dBFS; check the physical routing beforehand and turn connected speakers down. The recording is never sent back to the output.

A first, targeted test:

```sh
python3 tools/test-audio-regression.py --output build/latency/regression-48k-128-1min --profiles 48000:128 --minutes 1
```

Then test the same combination for longer:

```sh
python3 tools/test-audio-regression.py --output build/latency/regression-48k-128-long --profiles 48000:128 --minutes 5 15 30
```

All combinations and durations:

```sh
python3 tools/test-audio-regression.py --output build/latency/regression-full
```

`--cycles 2` repeats the series. `--signals white pink` selects signals. `--plan` shows the size of the run without changing audio settings. `--seconds 10` is for a short technical check.

The full series stores about 122 GB of recorded and reference audio, plus logs. A single 30-minute run at 96 kHz uses about 1.6 GB of memory while recording. Check free disk space and memory beforehand. The analysis uses memory mapping. A compiler, libjack, the PipeWire/JACK tools and the installed Eleven Rack driver/backend are required; NumPy is not needed.

## Logs and evaluation

Each run keeps the raw float32 audio, the reference signal, callback timestamps, reported latency, and passive ALSA status/hardware parameters. `matrix.json` holds the results per profile; `regression.json` records the progress of the series. `.regression.json` holds the analysis windows and the anomalies found. A failing profile does not stop the other profiles; an error during setup/start stops the series.

The analysis checks reported recording xruns, the actual graph/ALSA settings, and restarts of the PCM streams. A scan of the signal after the first second looks for non-finite/clipped samples and runs of at least 64 near-zero or identical samples. Every 100 ms, a 512-sample window is aligned with the reference. The match is judged with a mean-removed correlation at the found delay; below 0.80 is flagged. Removing the mean matters for pink noise: the AC-coupled analog input removes its slow drift, which lowered the plain correlation of the same windows in every run and made pink noise fail without any audio fault. Delay shifts above eight samples are flagged for white and pink noise, whose delay is stable to the sample; multitone keeps a limit of 1 ms. Sine has an ambiguous delay because it is periodic, so it is not used to prove absolute delay or drift.

The warmup is six seconds because PipeWire sometimes applies its second playback configuration exactly five seconds after the start. With a five-second warmup, that reopen fell on the first moment of the recording and was reported as a PCM restart.

This first detector is a screening, not a guarantee that every short glitch is found. Analog filtering/noise can also cause a correlation failure. Review suspicious recordings before concluding that the driver has regressed. Warmup xruns remain in the log, separate from recording xruns. The test does not change the correction table and does not set new buffering in the driver.

Ctrl+C stops the series. In a `finally` block, the matrix script restores the previous hardware rate, PipeWire settings and active audio services. After kill -9, a power failure or an error during restoration, that guarantee does not hold; `matrix.json` shows `restored`. The temporary override is `~/.config/wireplumber/wireplumber.conf.d/99-eleven-matrix-rate.conf`. Keep the logs of failed or interrupted runs.

## Software checks without hardware

### White noise through the analog loopback

An analog return path changes the spectrum and phase of white noise. As a
result, the original comparison with the unprocessed reference file can fall
below the correlation threshold without any samples missing. For these
measurements there is a separate analysis that must be selected explicitly:

```sh
python3 tools/test-audio-regression.py --analog-white-noise --output build/latency/analog-white --profiles 88200:128 --minutes 1 --signals white
```

This option estimates one fixed filter response from 0.2 seconds and checks it
on other measurement windows. The filter is not re-estimated after a timing
step. Besides the alignment windows, consecutive 512-sample blocks are checked,
requiring at least 0.98 correlation and at most 10% relative RMS deviation.
The original correlations are kept. Silence, clipping, reported xruns,
observed PCM restarts and sudden delay steps of more than eight samples remain
failures. Those eight samples are a diagnostic bound; the analysis does not
prove sample-perfect transfer. Without hardware status and callback times, the
PCM-restart check is reported as unavailable. The existing analysis remains
the default; sine, pink noise and multitone are not affected by this option.

For an existing white-noise recording:

```sh
cc -shared -fPIC -O2 tools/loopback-filter.c -o build/latency/libloopback-filter.so -lm
python3 tools/analyze-white-noise-path.py PATH/RECORDING.raw
python3 tools/test-white-noise-analysis.py
```

The reference file, log file and the existing correlation library are also
needed. The output is written to `RECORDING.white-path.json`. The eight
synthetic checks cover filtering, a sample jump, silence, a short interruption
between the alignment windows, clipping, an xrun, a PCM restart and unusable
training data. A passing filter comparison
must never override a measured timing step or PCM restart.

```sh
cc -shared -fPIC -O2 tools/latency-correlation.c -o build/latency/liblatency-correlation.so -lm
python3 tools/test-regression-analysis.py
```

These four synthetic tests check a clean delayed signal, silence, an xrun and a sudden delay shift. Long physical regression runs still have to be carried out; building these tools does not yet produce a stability result.

## Automatically at night

The installed user cron job starts daily at 23:00, Europe/Brussels. `run-nightly-regression.py` works through a persistent queue: all 24 profiles, three signals and four durations. Each task is one combination/signal/duration. The next night continues with the next unfinished task. A fully completed but failed audio test is kept and the queue moves on; an incomplete task is retried the next night. Once all 288 tasks are done, the cron job runs no new audio tests.

A new task only starts if its expected run time plus two minutes of reserve fits in the window. At 03:55, a task that is still running is stopped, leaving time to restore audio before 04:00. A hung process may need to be stopped forcibly; check the restore report in that case. An open REAPER, insufficient disk space (<8 GiB) or another active nightly run prevents starting. This does not detect every other audio application.

Leave the computer awake, the user audio session available and the Eleven Rack switched on, with Main Out L → Line In L connected. Cron does not wake a sleeping computer. Disable automatic sleep beforehand for test nights. The tests interrupt normal audio use.

Progress: `build/latency/nightly-regression/queue.json`. Main log: `build/latency/nightly-regression/cron.log`; each task also has its own log and result directory.

The cron job is identified by `# eleven-rack-nightly-regression`. Remove that line with `crontab -e` to disable future nightly runs. This does not stop a run that is already active.

## Firmware SMIs and system pauses

A System Management Interrupt (SMI) makes the BIOS firmware stop all CPU cores at once. Linux, PipeWire and the driver do not notice it and cannot prevent it. To distinguish such pauses from driver faults, every regression matrix counts SMIs during the recording (`smi.csv` next to `matrix.json`). For each profile, `matrix.json` contains a `platform` block with:

- `callback_stalls`: JACK callbacks that arrived at least 5 ms later than the previous buffer allowed;
- `fault_windows`: analysis faults, with a margin back in time of the round trip of four quanta plus 50 ms;
- `classification`: `clean`, `smi_correlated` (all stalls/faults coincide with an SMI), `partly_smi`, `not_smi` or `unavailable`.

This is coincidence in time, not proof of cause, and it does not change the PASS/FAIL verdict. Xruns have no timestamp and are not attributed.

The SMI counter (Intel `MSR_SMI_COUNT`, through the perf event `msr/smi/`) requires `CAP_PERFMON`. Install the small helper once; it can only read that one counter:

```sh
cc -O2 -Wall -Wextra tools/smi-counter.c -o build/latency/smi-counter
sudo install -o root -g root -m 0755 build/latency/smi-counter /usr/local/libexec/eleven-rack-smi-counter
sudo setcap cap_perfmon=ep /usr/local/libexec/eleven-rack-smi-counter
/usr/local/libexec/eleven-rack-smi-counter spin 5 100 | tail -1   # smi_total must be a number
```

Without this helper, everything still runs, with `classification: unavailable`. Repeat `install` and `setcap` after changing `smi-counter.c`; reinstalling the file removes the capability.

`--platform-calibration SECONDS` measures, before the audio test, how long the machine is stopped while no audio runs: a busy loop records gaps without a context switch (`max_stolen_gap_ns`) and which of them coincide with an SMI (`max_smi_gap_ns`). Result: `platform-calibration.json`. The nightly run does this for 30 seconds before the first task of each night. Never run it during audio: the loop occupies a CPU.

On the test setup's Latitude 5490, the 20–30 ms stalls came from the keyboard-backlight LED (`dell::kbd_backlight`). A write to `brightness` makes `dell-laptop` issue two BIOS calls through SMBIOS/WMI (read the state, then write it); the write takes 25–30 ms in SMM. GNOME writes it when dimming after inactivity and when restoring. With `gsettings set org.gnome.settings-daemon.plugins.power idle-dim false`, 17 five-minute runs at 44.1–96 kHz on 2026-10-16 had no SMIs at all; before the change, the same 48000:128 run failed twice with 27–33 ms stalls. The nightly run should confirm this over a longer period. User documentation: [firmware pauses](system-pauses.md).

Reading `dell_smm_hwmon` sensors (fan/temperature, for example from a desktop widget or `sensors`) costs 1–3 ms in SMM per reading. That is shorter, but it can also matter with small buffers.

## USB and PipeWire transport events

A delay step without an xrun has two known transport causes: a `Ring Underrun` on the Rack's playback endpoint, after which the device plays silence and all later audio arrives later (see [USB packet capacity fix](usb-packet-capacity-fix.md)), or a PipeWire follower resync, which rewinds or inserts silence. Neither is logged by default. With `--transport-trace` (`test-audio-regression.py`, always on in the nightly run), each matrix records both:

- `xhci.log` next to `matrix.json`: xHCI completion events other than Success and Short Packet, for the whole USB bus;
- `pipewire.log` in each profile directory: PipeWire's journal for that profile. Only the PipeWire the test starts gets `PIPEWIRE_DEBUG=2,spa.alsa:3`; the previous user environment is restored straight after the start, so the restored session logs as before.

For each profile, `matrix.json` contains a `transport` block with the xHCI events and resync/recover messages during the recording, and `fault_windows` (the same windows as the SMI attribution) with a `cause`: `xhci`, `pipewire_resync`, both, `unexplained`, or `unknown` when a source was unavailable. `classification` is `clean` without faults, the single cause, `mixed`, or `unavailable`. The nightly `queue.json` keeps it as `transport`. As with SMIs, this is coincidence in time and does not change PASS/FAIL. The trace covers every device on the bus; `slot` and `endpoint` (the Rack's playback is `0x03`) tell them apart.

Tracing requires write access to tracefs. Install the small helper once; it can only create its own trace instance for `xhci_handle_event` with a fixed filter:

```sh
cc -O2 -Wall -Wextra tools/xhci-trace.c -o build/latency/xhci-trace
sudo install -o root -g root -m 0755 build/latency/xhci-trace /usr/local/libexec/eleven-rack-xhci-trace
sudo setcap cap_dac_override=ep /usr/local/libexec/eleven-rack-xhci-trace
/usr/local/libexec/eleven-rack-xhci-trace check   # must print ok
```

`--usb-flight` (also always on in the nightly run) uses the same helper as a flight recorder: a 1 MiB-per-CPU kernel ring buffer keeps the Rack's isochronous EP 3 URB submissions and completions, xHCI errors, IRQs, softirqs, scheduler switches, ksoftirqd wakeups and C-state changes. A Ring Underrun on the playback endpoint freezes the buffer; the helper appends it to `xhci-flight.log` (at most five dumps per matrix) and re-arms. `tools/analyze-usb-flight.py xhci-flight.log` reports per underrun the capture completion intervals, the delay from capture completion to the playback submission it releases, empty capture URBs, and a timeline of the last 10 ms on the CPU that handled the capture completions; `matrix.json` keeps the summary as `usb_flight`. In implicit-feedback mode each capture completion releases one playback URB, so an underrun means that for longer than the lead (2 ms) no capture completion was turned into a submission: either completions were handled late, or capture URBs carried no data.

Without this helper, the PipeWire part still runs and `xhci_trace` reads `unavailable`. Repeat `install` and `setcap` after changing `xhci-trace.c`. `python3 tools/test-transport-trace.py` checks the attribution without audio or root.

## Additional multitone test

The separately selectable `multitone` signal combines 431, 997, 1871 and 2973 Hz at equal amplitude. The sum is divided by four, so the existing maximum output level is kept. The combined pattern repeats after one second; the latency search range stays below 200 ms. The analysis uses 100 ms windows for it, to recognize the frequency combination. This gives more information than a single sine wave, but analog phase shift/filtering can still affect the peak found and the similarity.

```sh
python3 tools/test-audio-regression.py --output build/latency/regression-multitone --profiles 48000:128 --minutes 1 --signals multitone
```

Only start this separate run once the current runner has finished: `test-audio-regression.py` itself does not take the nightly lock. The existing nightly queue remains 288 tasks with sine/white/pink noise and is not changed. Two extra synthetic tests check absolute multitone delay (including >100 ms) and a delay shift. Physical multitone measurements have not been carried out yet. The multitone test has no separate per-frequency detector for phase or amplitude jumps; it uses the combined correlation and the existing signal scan.

## Existing sample-rate override and driver identity

Since 2026-10-16, the matrix runner saves an existing
`99-eleven-matrix-rate.conf` in the output directory as `original-rate-override.conf`.
The test uses the filename temporarily and then restores the original
bytes and file permissions; if the file did not exist originally, the test
file is removed. Symlinks and other non-regular files are rejected. Restoration
also applies when a measurement is interrupted. `matrix.json` records the
original file state and the verified final state of the file, the hardware
rate and the PipeWire metadata. Restore errors remain in the report and must
not let the queue continue.

An existing file that is exactly the matrix's own rule is a leftover of an aborted run, not user configuration. Restoring it would pin the Rack to that test's sample rate, so the panel could no longer change the rate. Such a file is saved as `stale-matrix-rate-override.conf` in the output directory and removed afterwards (`stale_matrix_rate_override_removed` in `matrix.json`). Any other content is preserved as described above.

The module srcversion is recorded before and after a matrix; new nightly
queue results take over the measured starting identity. Historical results
without that metadata are therefore not retroactively assigned to a driver.
The nightly runner now selects the fixed analog-response analysis for white
noise; raw screenings are kept. An old raw-correlation FAIL and a new
analog-response PASS must not be compared as a driver improvement without
re-analysis. Sine and pink-noise analysis remain the same.

Targeted checks without hardware:

```sh
python3 tools/test-matrix-rate-override.py
python3 tools/test-nightly-runner.py
python3 tools/test-pcm-restart-detection.py
```

The start/restore check on 2026-10-16 recorded ten seconds of white noise at
48 kHz / 128 frames with module `BFA8216A48C7CCD7D84B7B8`: no xruns,
waveform faults or PCM restart, and the existing override file and audio
settings were verifiably restored. Evidence: `build/latency/nightly-override-smoke-20261016/`.
This is a check of the repaired test workflow, not a replacement for the
planned thirty-minute test or long-duration driver regression.

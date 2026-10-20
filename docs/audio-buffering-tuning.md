# Automatic buffering comparison

`tools/tune-audio-buffering.py` automates a bounded comparison at 48 kHz / 128 samples. It examines the existing settings and playback `api.alsa.headroom` values of 0, 32, 64, 96, 128, 192 and 256 frames. This is real playback buffer margin in the PipeWire ALSA backend, not a change to the latency correction table or to the kernel's USB packet scheduling. Headroom is applied only temporarily, and only to the Eleven Rack output node.

Show the plan:

```sh
python3 tools/tune-audio-buffering.py --output build/latency/buffering-tuning
```

Run it physically, with Main Out L → Line In L connected and REAPER closed:

```sh
python3 tools/tune-audio-buffering.py --output build/latency/buffering-tuning --execute
```

Each candidate is first tested with one minute of each signal. Only fault-free candidates with a measured round-trip latency between 10 and 12 ms go on to two fresh-start cycles of 5, 15 and 30 minutes per signal. Candidates closer to 12 ms get priority. The result is a proposal in `tuning.json`, not an automatically installed default. Without a confirmed candidate, the defaults are kept.

The latency is determined from the median physical lag of the reliable white/pink-noise windows, not from the sine wave or from the reported latency alone. The limitations of the regression detector still apply; check suspicious audio. This bounded headroom range does not guarantee that the target is achievable. Any recommendation applies only to the tested profile and system; other profiles must be checked again afterwards.

## Screening on the test laptop (2026-10-20)

On the Dell Latitude 5490 (Ubuntu 26.04, kernel 7.0, 2 ms playback lead) a 1-minute sine, white and pink loopback per candidate gave:

| Playback headroom | Measured round trip | Fault-free |
| --- | --- | --- |
| default | 12.20 ms | yes |
| 0 | 12.19 ms | yes |
| 32 | 12.82 ms | yes |
| 64 | 13.27 ms | yes |
| 96 | 14.28 ms | yes |
| 128 | 14.65 ms | yes |

The default already behaves as headroom 0, so headroom offers no lower latency; each extra frame only adds to it. The candidates 192 and 256 were not run because they cannot reach the target. At 48 kHz / 128 samples the round trip consists of roughly 5.3 ms for one input and one output buffer, the 2 ms playback lead, and about 4–5 ms of USB transfer, implicit feedback and the Rack's converters and internal routing. Lower latency therefore needs a smaller buffer (64 samples measured about 7.7–9.3 ms) or a shorter playback lead, both at the cost of safety margin. The confirmation stage was not run.

The screening used `--analog-white-noise`, which the tool now passes for white noise too; without it every candidate failed on raw white-noise correlation.

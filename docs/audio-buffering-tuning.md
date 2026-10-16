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

Each candidate is first tested with one minute of each signal. Only fault-free candidates with a measured round-trip latency between 10 and 12 ms go on to two fresh-start cycles of 5, 15 and 30 minutes per signal. Candidates closer to 12 ms get priority. The result is a proposal in `tuning.json`, not an automatically installed default. Without a confirmed candidate, the defaults are kept. The physical tuning has not been carried out yet.

The latency is determined from the median physical lag of the reliable white/pink-noise windows, not from the sine wave or from the reported latency alone. The limitations of the regression detector still apply; check suspicious audio. This bounded headroom range does not guarantee that the target is achievable. Any recommendation applies only to the tested profile and system; other profiles must be checked again afterwards.

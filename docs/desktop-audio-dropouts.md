# Dropouts from scheduling and desktop audio

Some dropouts have nothing to do with the Eleven Rack or its driver. The audio
system itself is held up: PipeWire does not get the CPU in time, or a desktop
application such as a browser or a streaming app delivers its audio late. Both
were found on a low-power mini PC (Intel N150, 4 cores) running Ubuntu Studio.
They are most likely on small, low-power machines and with small buffers.

Open the control panel's **Monitor** window first. Its System check card shows
how PipeWire's audio thread is scheduled and warns about the first problem
below. With **Record**, the log shows xruns of every PipeWire node, not only
the Rack's.

## PipeWire runs at a low priority

**Symptoms:** xruns and short dropouts at random moments, more often while
other programs start or the system is busy. The Monitor's System check warns
that PipeWire's audio thread runs below the interrupt threads.

**Cause:** PipeWire needs permission to use real-time scheduling. It also
tries to raise its nice level. If that second step is not allowed, PipeWire
falls back to RTKit, which only grants priority 20, even when real-time
priority 95 would have been allowed. With the `threadirqs` kernel option,
which Ubuntu Studio enables, every device interrupt runs as a real-time thread
at priority 50 or higher. PipeWire at 20 then has to wait for all of them.

Check it:

```sh
ps -u $USER -L -o pid,cls,rtprio,comm | grep data-loop
```

The `data-loop.0` thread of `pipewire` should show `FF` with a priority such
as 88. `RR 20` means the RTKit fallback. `TS` without a priority means no
real-time scheduling at all: neither RTKit nor real-time permissions are
available. Other users' PipeWire, for example the login screen's (`sddm` or
`gdm`), does not matter.

**No real-time priority at all (`TS`):** on Arch, `rtkit` is only an optional
dependency of PipeWire, and a fresh installation may have neither it nor
`realtime-privileges`. The Eleven Rack package from 0.1.2 beta16 depends on
`rtkit`; for older packages install it with `sudo pacman -S rtkit` and log in
again. PipeWire then runs at `RR 20`, which is enough without `threadirqs`.

**Fix:** allow the nice level for the `audio` group and log in again. A reboot
is the surest way:

```sh
echo '@audio - nice -19' | sudo tee /etc/security/limits.d/96-audio-nice.conf
sudo reboot
```

Your user must be in the `audio` group (`id` lists it). On Arch the
real-time group is usually `realtime` (package `realtime-privileges`); use
that group name instead. Afterwards `grep -i "nice priority" /proc/$(pgrep -u
$USER -x pipewire)/limits` should show 39, and the `data-loop.0` thread `FF 88`.

## Desktop applications deliver their audio late

**Symptoms:** a browser, YouTube or a streaming app such as Tidal drops out
for a moment, for example when another program starts. The Monitor shows no
xrun on the Rack. The dropout is in the application's stream: when it delivers
its audio too late, pipewire-pulse fills the gap with silence, and that is not
counted as an xrun.

**Check:** play audio in the application and load all CPU cores for 15
seconds:

```sh
for i in $(seq $(nproc)); do timeout 15 sh -c 'while :; do :; done' & done; wait
```

If that produces the dropout, the application's buffer is too small for the
load on this machine.

**Fix:** give desktop applications a larger buffer. This only affects
applications using PulseAudio (browsers and most media players); DAWs using
PipeWire's JACK interface keep their small buffer:

```sh
mkdir -p ~/.config/pipewire/pipewire-pulse.conf.d
cat > ~/.config/pipewire/pipewire-pulse.conf.d/90-desktop-buffer.conf <<'EOF'
# Larger buffers for desktop audio (browser, streaming): survives CPU bursts.
pulse.properties = {
    pulse.min.req     = 2048/48000
    pulse.min.quantum = 2048/48000
}
EOF
systemctl --user restart pipewire-pulse
```

Restart the application afterwards. The Monitor's PipeWire card lists the
desktop streams with their buffer, for example `Firefox 57.3 ms buffer`. On
the N150, Tidal and YouTube in Firefox survived the full-load test with this
setting, and dropped out without it.

## Related

- [Clicks and shifted latency from delayed USB handling](usb-completion-delays.md)
- [Dropouts from firmware pauses (Dell laptops)](system-pauses.md)
- [Frequently asked questions](https://r11linux.eu/faq.html)

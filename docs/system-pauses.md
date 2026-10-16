# Dropouts from firmware pauses (Dell laptops)

Some laptops briefly stop the whole computer to run firmware code. On a Dell
Latitude 5490 we measured pauses of **20–30 ms**. At 48 kHz and 128 frames, one
buffer lasts 2.67 ms, so a single pause empties about ten buffers in a row. You
hear a dropout or click, PipeWire may report an xrun, and the stream can
restart.

Raising the buffer size does not help much: 512 frames is still only 10.7 ms.
The Eleven Rack driver cannot prevent these pauses either. The fix is to stop
whatever triggers them.

## Symptoms

- Occasional dropouts at irregular intervals, often a minute or more apart,
  even with a lightly loaded system and a buffer that is otherwise stable.
- The dropouts come at moments when you start typing or touch the touchpad
  after a short idle period.

## Cause

The pause is a **System Management Interrupt (SMI)**. It hands every CPU core
to the BIOS until the firmware finishes, and Linux cannot interrupt or
reschedule it.

On Dell laptops, changing the **keyboard backlight** brightness is done through
a BIOS call. Linux's `dell-laptop` driver first reads the current backlight
state, then writes the new one. On the Latitude 5490 the write took
25–30 ms in firmware.

GNOME dims the keyboard backlight when you go idle and restores it when you
type or move the pointer. Each dim or restore is one of these pauses.

On the Latitude 5490, turning off GNOME's idle dimming removed the long SMIs.
The same 5-minute loopback test (48 kHz, 128 frames) failed twice with
27–33 ms stalls before the change, and passed with no SMIs and no xruns after
it.

## Fix

**GNOME (Ubuntu's default desktop):** turn off idle dimming:

```sh
gsettings set org.gnome.settings-daemon.plugins.power idle-dim false
```

This also stops the screen dimming before it blanks. Screen blanking and
suspend are separate settings and are not affected. To undo:

```sh
gsettings set org.gnome.settings-daemon.plugins.power idle-dim true
```

**Other desktops:** look for keyboard-backlight dimming in the power-management
settings and turn it off.

**Any desktop:** set the keyboard illumination level and its timeout in the
Dell BIOS setup, and avoid desktop tools that change the backlight. The
setting names differ between models.

Fan and temperature readings from the `dell_smm_hwmon` driver are also BIOS
calls. On the Latitude 5490 each reading took 1–3 ms. That is shorter, but
enough to matter at small buffers if a sensor widget polls them frequently. If
you suspect this, close sensor widgets or test with
`sudo modprobe -r dell_smm_hwmon`.

## Check whether this affects your laptop

**Quick test (Dell laptops):** play audio through the Rack and set the keyboard
backlight a few times:

```sh
echo 1 | sudo tee /sys/class/leds/dell::kbd_backlight/brightness
echo 2 | sudo tee /sys/class/leds/dell::kbd_backlight/brightness
```

Use a value between 0 and the number in `max_brightness` in the same directory.
If each change produces a dropout, you are affected.

**Count SMIs (Intel CPUs):** run this in a terminal while audio plays:

```sh
sudo turbostat --quiet --show Time_Of_Day_Seconds,SMI --interval 1
```

`turbostat` is in the `linux-tools` package on Ubuntu and in `kernel-tools` on
Fedora. If the SMI column increases in the same second as a dropout, firmware
is the likely cause. A few SMIs without dropouts are normal; only long ones
are audible.

The project's [loopback regression tests](audio-regression-tests.md) record
SMIs automatically and mark each failure that coincides with one.

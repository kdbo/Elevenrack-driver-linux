# Clicks and shifted latency from delayed USB handling

The Eleven Rack sends and receives audio over USB in small blocks of about
1 ms. Playback only stays filled while Linux handles each finished block
quickly. If that handling is held up for more than about 1 ms, the Rack runs
out of playback audio. It plays a short silence, and everything after that is
played slightly later.

You may hear a single short click. From then on the output is about 1 ms
later than before, and stays that way until the stream restarts. Nothing
reports an xrun. In a DAW, a recording overdubbed after that moment can sit
about 1 ms late.

On the test laptop this happened about once an hour without the fix below,
and more often during heavy network traffic. A larger buffer does not prevent
it: the delay happens in the kernel, below PipeWire's buffer.

## Check whether this affects your system

Driver versions newer than 0.1.2~beta14 count these events.

- **Control panel:** click **Monitor**. The **Driver** card shows
  *Playback gaps*: how often playback ran dry, for how long in total, and how
  long ago the last one was. **Reset** counts from that moment, for example
  for one recording session.
- **Terminal:**

  ```sh
  cat /proc/asound/Rack/eleven_stats
  ```

  `playback_gaps` is the count, `gap_total_us` the total shift in
  microseconds. A second Rack is `/proc/asound/Rack_1/eleven_stats`.
- **Kernel log:** each event is also logged, limited so that the log does not
  fill up:

  ```sh
  journalctl -k | grep "playback ran dry"
  ```

The counter starts at 0 when the Rack is connected or the driver is loaded. A
count that keeps rising during normal use means your system is affected.

## Cause

Each finished USB transfer is handed to the driver in a *softirq*: kernel work
that runs after an interrupt, on the CPU that received it. Softirqs on one CPU
run one after another. Two things were found to hold up the Rack's softirq for
more than 1 ms:

1. **Network traffic on the same CPU.** The USB controller and the wifi card
   delivered their interrupts to the same CPU. Receiving wifi data runs as a
   softirq that may take up to 2 ms per pass. The Rack's softirq had to wait
   for it.
2. **Deferred softirqs waiting for the CPU.** When a softirq pass ends while
   another task wants the CPU, the kernel hands the remaining work to the
   `ksoftirqd` thread of that CPU. `ksoftirqd` normally runs at ordinary
   priority. On kernels with lazy preemption it does not interrupt a running
   desktop task straight away, and it could wait more than 1 ms.

Both are system settings, not a fault in the Rack or the driver. Many
distributions, including Ubuntu, leave every interrupt on CPU 0 and run
`ksoftirqd` at ordinary priority.

## Fix

The fix keeps the USB controller's interrupt on a CPU without network
interrupts, and lets that CPU's `ksoftirqd` run at real-time priority.

### 1. Find the USB controller's interrupt

The interrupt number belongs to the **USB host controller** the Rack is
connected to, not to the Rack or a port. It is assigned at boot, so it differs
between machines and can change after a kernel or BIOS update. Look it up each
time rather than reusing a number from another machine.

The **System check** card in the Monitor window shows it, for example:

```
USB controller  0000:00:14.0, IRQ 123 on CPU 0
```

From a terminal, the same report is available with:

```sh
python3 /usr/lib/eleven-rack/tools/eleven_rack_diagnostics.py
```

The report also warns when a network interface shares that CPU, or when
`ksoftirqd` on it runs at ordinary priority.

To see which CPUs handle network interrupts, look for your wifi or Ethernet
driver in `/proc/interrupts` (for example `iwlwifi`, `ath`, `rtw`, `e1000e`
or `r8169`). Each column is one CPU; the column whose count rises is the CPU
handling it.

### 2. Move the interrupt to another CPU

Pick a CPU that does not handle network interrupts. Using IRQ 123 and CPU 2 as
an example:

```sh
echo 2 | sudo tee /proc/irq/123/smp_affinity_list
cat /proc/irq/123/effective_affinity_list    # should print 2
```

If `irqbalance` is running, it may move the interrupt back. Stop it, or
exclude this interrupt in its configuration.

### 3. Give that CPU's ksoftirqd real-time priority

```sh
sudo chrt -f -p 51 $(pgrep -x ksoftirqd/2)
chrt -p $(pgrep -x ksoftirqd/2)               # should show SCHED_FIFO, priority 51
```

Use the CPU from step 2. Priority 51 stays below PipeWire's audio threads.

A real-time `ksoftirqd` can take that CPU over completely while there is a
lot of softirq work, for example during a network flood. That is why the
network interrupts should stay on other CPUs.

An alternative to this step is booting with the `threadirqs` kernel option
and raising the USB controller's interrupt thread with a tool such as
`rtirq`. That moves the USB handling into its own real-time thread. It still
does not stop a long network softirq on the same CPU, so keep step 2.

### These settings do not survive a reboot

Both settings are lost on a reboot, and the interrupt setting also when the
USB controller's driver is reloaded. After a reboot, look up the interrupt
again (step 1) and repeat steps 2 and 3. A startup script or systemd unit can
do this, but it has to look up the interrupt number each time.

### Result on the test laptop

On a Dell Latitude 5490 (Ubuntu, kernel 7.0), 44.1 kHz and 256 frames:

| Setting | Playback ran dry |
| --- | --- |
| Default: USB and wifi interrupts on CPU 0 | 1 in 90 minutes |
| USB interrupt on CPU 2 | 2 in 90 minutes |
| USB interrupt on CPU 2, `ksoftirqd/2` at FIFO 51 | 0 in 6 hours |

Moving the interrupt alone removed the network delays but not the
`ksoftirqd` delays; both steps together were needed.

## USB ports and controllers

Every port on one USB host controller shares the same interrupt. Moving the
Rack to another port on the same controller changes nothing, and the settings
above still apply.

Some computers have several USB controllers, for example a separate one for
USB-C or Thunderbolt ports, or an add-in card. A port on another controller
uses another interrupt. Check the Monitor window after moving the Rack; it
shows the controller the Rack is on now.

The Latitude 5490 has a single controller (`0000:00:14.0`); all its ports,
including USB-C, are on it.

## Two Racks

Two Racks on the same USB controller share its interrupt and are handled by
the same softirq on the same CPU:

- The settings above protect both Racks at once.
- One delay can make both Racks run dry at the same moment. Each Rack counts
  its own events in its own `eleven_stats` file.
- The extra load of a second Rack is small compared with the delays described
  here.

If the Racks are on different controllers, each controller has its own
interrupt. Apply steps 2 and 3 for each of them, preferably on different CPUs
that do not handle network interrupts.

The Monitor window shows one Rack at a time; choose the Rack in the control
panel's device selector. See [two connected Eleven Racks](multiple-devices.md)
for clocks and device selection.

# Original editor tuner reference capture

Analyzed 2026-10-09: `/home/koen/11R-tuning-freq.mmon`, a MIDI Monitor
binary property list containing an NSKeyedArchiver message array.
The file contains 1,000 messages over approximately 8.65 seconds,
including both "To Eleven Rack Rig" and "From Eleven Rack Rig" endpoints.
It starts during an adjustment, rather than at tuner activation.

## Confirmed traffic

The original editor sends 71 reference adjustment messages:

```text
F0 13 0B 0F 00 41 XX 00 F7
```

The Rack emits 76 corresponding broadcasts:

```text
F0 13 0B 0F 02 41 XX 00 F7
```

There are 31 distinct values in each direction. Outgoing values descend
from decimal 44 to 36, then rise to 66, finally ending at 64. The trailing
payload byte is **00**, distinguishing these messages from the previously
described 0x41 needle messages with trailing **01**. After the initial
buffered traffic, broadcasts track outgoing values. Thus MIDI/SysEx can
control the reference; the upstream claim that no reference control exists
on the MIDI surface is contradicted by this capture.

The capture also contains 377 CMD 0x42 requests and 377 replies; these
replies all contain idle note/tune `00 40`. There is no played-note
measurement here to calibrate the deviation or needle scale.

At message 899, the editor switches the tuner off using
`F0 13 0B 0F 00 40 00 F7`. The Rack then emits its full rig chain and tuner-off
state, followed by ordinary read queries for the current rig.

## Still unresolved

- Mapping of `XX` to Hz. The final outgoing value is decimal 64 (`0x40`);
  the corresponding displayed A-reference must be established independently.
- Supported range and rounding/step behavior.
- Whether `F0 13 0B 0F 01 41 F7` also returns reference state, and with
  which response direction. No such request is present in this capture.
- Whether the trailing byte is a selector or part of a wider numeric encoding.

No reference writes have been sent by our editor based on this capture.

## Second controlled capture

`/home/koen/11R-tuning-freq 2.mmon` contains 1,000 messages over 10.13 s.
It separates continuous note polling (446 outgoing CMD 0x42 requests,
445 replies) from five CMD 0x41 writes and five matching broadcasts:

| Relative time | Outgoing reference payload | Matching incoming payload |
| --- | --- | --- |
| 4.029 s | `00 41 40 00` | `02 41 40 00` |
| 4.250 s | `00 41 3F 00` | `02 41 3F 00` |
| 4.416 s | `00 41 3E 00` | `02 41 3E 00` |
| 5.375 s | `00 41 3F 00` | `02 41 3F 00` |
| 5.387 s | `00 41 40 00` | `02 41 40 00` |

The raw sequence is 64 -> 63 -> 62 -> 63 -> 64. It is not periodic note
polling. The displayed Hz sequence still needs the user's confirmation;
do not infer a linear Hz mapping from the raw values alone.

The user subsequently confirmed that the second recording went from 440 to
438 Hz and back. This establishes the local mapping `Hz = XX + 376` and a
1 Hz step. The editor now sends the captured CMD 0x41 write and displays
reference broadcasts with trailing 00 separately from needle traffic with
trailing 01. Its UI accepts the upstream documented 410–480 Hz range; only
438–440 has been confirmed by this controlled capture. No new reference
writes or reference read requests have yet been verified on Linux hardware.
If the initial read does not return reference state, the UI leaves the value
blank and lets the user explicitly enter a frequency, rather than assuming 440.

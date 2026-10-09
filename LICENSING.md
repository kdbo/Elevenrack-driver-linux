# Licensing

Copyright (c) 2026 Koen de Boevé for original contributions.

This repository contains components with different licenses:

| Component | License |
| --- | --- |
| Original Python control panel, settings tools, tests, and other original project files, except the kernel patch helper below | MIT; see [LICENSE](LICENSE) |
| Original kernel changes in `patches/*.patch` | GPL-2.0-or-later; see [GPL version 2](LICENSES/GPL-2.0.txt) |
| `packaging/prepare-driver.py`, including its embedded kernel changes | GPL-2.0-or-later; see [GPL version 2](LICENSES/GPL-2.0.txt) |
| Existing Linux/ALSA code, including patch context and downloaded kernel sources | Existing upstream licenses and copyright notices |
| Third-party dependencies and any future imported editor code | Their respective upstream licenses |
| Imported Eleven Edit UI under `editor/` | MIT, with upstream notices in `editor/LICENSE` and `editor/NOTICE` |
| Bundled fonts under `editor/src/fonts/` | SIL Open Font License; see the accompanying `OFL-*.txt` files |

GPL-2.0-or-later means our original kernel contributions may be used under
GPL version 2 or, at the recipient's option, any later version. This does
not change the license of existing kernel code. The Linux kernel as a whole
is GPL version 2 only; individual files may have other compatible licenses.
The rebuilt `snd-usb-audio` module remains governed by the applicable kernel
licenses. See the [Linux kernel licensing rules](https://www.kernel.org/doc/html/latest/process/license-rules.html).

The MIT license at the repository root applies only within the scope above;
it does not replace the GPL terms for kernel contributions or upstream terms.
Using ALSA from the separate user-space control panel does not itself make
that panel part of the kernel module.

Future Debian packages include this file, the MIT and GPL texts, and credits
under `/usr/share/doc/eleven-rack-driver/`. Preserve applicable license and
copyright notices when redistributing source or packages. Already published
release artifacts are not replaced by this documentation update.

See [CREDITS.md](CREDITS.md) for the upstream projects and protocol references.

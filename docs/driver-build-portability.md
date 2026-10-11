# Shared driver build and distribution adapters

`packaging/build-driver-common.sh` builds from explicitly supplied kernel build
files and a clean, distribution-prepared `sound/usb` source directory:

```sh
# Run from a private writable build directory.
bash /path/to/repo/packaging/build-driver-common.sh \
    KERNEL_RELEASE /path/to/kernel-build /path/to/kernel-source/sound/usb
```

Supply sources with the distribution's patches applied and headers/build files
matching the target kernel. The script copies sources to
`$PWD/kernel-source/sound/usb`, applies the Eleven Rack changes there, and builds
the module. The supplied sources remain untouched. Builds can be retried; the
generated subtree is replaced. The result is
`kernel-source/sound/usb/snd-usb-audio.ko`.

The shared script uses Python, standard shell tools, make, and a compiler;
it does not fetch sources or invoke a distribution package manager. It retains
the kernel 6.8 minimum and compiler selection from the kernel configuration.
Patching fails on unsupported source layouts. A version at or above 6.8 does
not by itself establish compatibility, especially with distribution backports.

`packaging/build-driver.sh` is the Ubuntu adapter used by the existing DKMS
configuration. It retains Ubuntu source discovery and the
`ELEVEN_SOURCE_ARCHIVE` / `ELEVEN_SOURCE_PREFIX` overrides, extracts the clean
sources into `$PWD/ubuntu-source`, and invokes the shared script. The Debian
package includes both scripts. Existing build-check and CI entry points remain
valid. Neither script installs or loads the resulting module.

The initial [Arch local recipe](arch-installation.md) supplies a pinned prepared
source tree. Future automatic Arch source retrieval and RPM adapters must supply
their own matching prepared sources
and kernel build files, then invoke the shared script. This refactoring does
not yet provide Arch/RPM packages or establish hardware support on those systems.

## Kernel scheduling and RT checks

Separate build compatibility from audio-performance checks. Building requires
matching sources, headers, configuration, and a supported source layout;
`CONFIG_PREEMPT_RT` is not a prerequisite for this driver.

The shared build prints the available preemption flags from the target build
configuration without rejecting kernels that lack full PREEMPT_RT.

For performance diagnostics, inspect the target kernel's configuration for
`CONFIG_PREEMPT_RT`, `CONFIG_PREEMPT`, and `CONFIG_PREEMPT_DYNAMIC`. Dynamic
preemption means the build-time configuration alone does not determine the
running preemption mode: boot parameters and the runtime mode also matter.
Inspect the target machine, not the build host, when cross-building.

On the running target, also check audio thread scheduling, user/service RT
limits, and locked-memory limits. A PREEMPT_RT kernel does not automatically
grant PipeWire or a DAW real-time scheduling. Conversely, audio threads can
use real-time scheduling on a kernel without full PREEMPT_RT.

See [Ubuntu Studio setup](ubuntu-studio-setup.md) for runtime checks. Physical
loopback regression tests determine stability and latency in the actual setup;
kernel flags alone do not establish either.

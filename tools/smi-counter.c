/* Firmware SMI counter and stolen-time probe for regression attribution.
 *
 * Reads the Intel MSR_SMI_COUNT through perf's msr/smi/ event. The event is
 * fixed here, so installing this binary with cap_perfmon=ep grants nothing
 * beyond the SMI count. Without that capability (or root) the counter is
 * unavailable; spin mode then still reports gaps, without SMI deltas.
 *
 *   monitor PERIOD_MS          CSV: realtime_ns,monotonic_ns,smi_count,late_ns
 *                              Printed when the count changes, the sampler
 *                              wakes >=2 ms late, or once per second.
 *   spin SECONDS THRESHOLD_US  CSV: realtime_ns,gap_ns,smi_delta,context_switches
 *                              Busy loop; every gap >= threshold. No audio
 *                              should run: this occupies one CPU.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <linux/perf_event.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

#define PERF_MSR_SMI 0x04 /* arch/x86/events/msr.c; sysfs: msr/events/smi */

static volatile sig_atomic_t stop;
static void on_signal(int sig) { (void)sig; stop = 1; }

static uint64_t now(clockid_t clock) {
    struct timespec t;
    clock_gettime(clock, &t);
    return (uint64_t)t.tv_sec * 1000000000ULL + t.tv_nsec;
}

static int open_smi(void) {
    FILE *f = fopen("/sys/bus/event_source/devices/msr/type", "r");
    int type;
    if (!f) return -1;
    if (fscanf(f, "%d", &type) != 1) { fclose(f); errno = ENODEV; return -1; }
    fclose(f);
    if (access("/sys/bus/event_source/devices/msr/events/smi", R_OK)) return -1;
    struct perf_event_attr attr;
    memset(&attr, 0, sizeof attr);
    attr.size = sizeof attr;
    attr.type = type;
    attr.config = PERF_MSR_SMI;
    /* SMIs stop every CPU; counting on CPU 0 sees all of them. */
    return syscall(SYS_perf_event_open, &attr, -1, 0, -1, 0);
}

static int read_smi(int fd, uint64_t *value) {
    return read(fd, value, sizeof *value) == sizeof *value ? 0 : -1;
}

static long context_switches(void) {
    struct rusage usage;
    getrusage(RUSAGE_THREAD, &usage);
    return usage.ru_nvcsw + usage.ru_nivcsw;
}

static int monitor(long period_ms) {
    int fd = open_smi();
    if (fd < 0) {
        fprintf(stderr, "SMI counter unavailable: %s\n", strerror(errno));
        return 3;
    }
    uint64_t period = period_ms * 1000000ULL, count, last_count = 0, last_print = 0;
    printf("realtime_ns,monotonic_ns,smi_count,late_ns\n");
    struct timespec deadline;
    clock_gettime(CLOCK_MONOTONIC, &deadline);
    for (int first = 1; !stop; first = 0) {
        uint64_t due = (uint64_t)deadline.tv_sec * 1000000000ULL + deadline.tv_nsec;
        if (clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &deadline, NULL) && !stop) continue;
        uint64_t mono = now(CLOCK_MONOTONIC);
        if (read_smi(fd, &count)) { fprintf(stderr, "SMI read failed\n"); return 1; }
        uint64_t real = now(CLOCK_REALTIME), late = mono > due ? mono - due : 0;
        if (first || stop || count != last_count || late >= 2000000ULL || mono - last_print >= 1000000000ULL) {
            printf("%llu,%llu,%llu,%llu\n", (unsigned long long)real, (unsigned long long)mono,
                   (unsigned long long)count, (unsigned long long)late);
            last_print = mono;
        }
        last_count = count;
        /* After a long stall, resume the grid from now rather than catching up. */
        uint64_t next = late > period ? mono + period : due + period;
        deadline.tv_sec = next / 1000000000ULL;
        deadline.tv_nsec = next % 1000000000ULL;
    }
    return 0;
}

static int spin(long seconds, long threshold_us) {
    int fd = open_smi();
    if (fd < 0) fprintf(stderr, "SMI counter unavailable: %s; reporting gaps only\n", strerror(errno));
    uint64_t threshold = threshold_us * 1000ULL, count = 0, previous_count = 0;
    uint64_t start = now(CLOCK_MONOTONIC_RAW), end = start + seconds * 1000000000ULL;
    uint64_t first_count = 0, previous = start;
    if (fd >= 0 && read_smi(fd, &first_count)) fd = -1;
    previous_count = first_count;
    long previous_switches = context_switches(), max_gap = 0;
    printf("realtime_ns,gap_ns,smi_delta,context_switches\n");
    while (!stop && previous < end) {
        uint64_t t = now(CLOCK_MONOTONIC_RAW);
        long switches = context_switches();
        if (fd >= 0 && read_smi(fd, &count)) fd = -1;
        if (t - previous >= threshold) {
            if (fd >= 0)
                printf("%llu,%llu,%llu,%ld\n", (unsigned long long)now(CLOCK_REALTIME),
                       (unsigned long long)(t - previous), (unsigned long long)(count - previous_count),
                       switches - previous_switches);
            else
                printf("%llu,%llu,,%ld\n", (unsigned long long)now(CLOCK_REALTIME),
                       (unsigned long long)(t - previous), switches - previous_switches);
        }
        if ((long)(t - previous) > max_gap) max_gap = t - previous;
        previous = t;
        previous_count = count;
        previous_switches = switches;
    }
    if (fd >= 0)
        printf("# duration_ns=%llu max_gap_ns=%ld smi_total=%llu\n", (unsigned long long)(previous - start),
               max_gap, (unsigned long long)(count - first_count));
    else
        printf("# duration_ns=%llu max_gap_ns=%ld smi_total=\n", (unsigned long long)(previous - start), max_gap);
    return 0;
}

int main(int argc, char **argv) {
    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);
    setvbuf(stdout, NULL, _IOLBF, 0);
    char *end;
    if (argc == 3 && !strcmp(argv[1], "monitor")) {
        long period = strtol(argv[2], &end, 10);
        if (*end || period < 1 || period > 1000) { fprintf(stderr, "Period must be 1..1000 ms\n"); return 2; }
        return monitor(period);
    }
    if (argc == 4 && !strcmp(argv[1], "spin")) {
        long seconds = strtol(argv[2], &end, 10);
        if (*end || seconds < 1 || seconds > 600) { fprintf(stderr, "Spin must be 1..600 seconds\n"); return 2; }
        long threshold = strtol(argv[3], &end, 10);
        if (*end || threshold < 10 || threshold > 1000000) { fprintf(stderr, "Threshold must be 10..1000000 us\n"); return 2; }
        return spin(seconds, threshold);
    }
    fprintf(stderr, "Usage: %s monitor PERIOD_MS | spin SECONDS THRESHOLD_US\n", argv[0]);
    return 2;
}

/* xHCI completion errors and a USB audio flight recorder for regression attribution.
 *
 * Each mode creates its own private tracefs instance with fixed events and
 * filters. Instances, events, filters and the trigger are fixed here, so
 * installing this binary with cap_dac_override=ep grants nothing beyond these
 * traces. Without it (or root) the traces are unavailable.
 *
 *   check     Create and remove both instances; prints "ok".
 *   monitor   Until SIGTERM/SIGINT, one line per xhci_handle_event with a
 *             completion code other than Success/Short Packet:
 *             REALTIME_MINUS_MONOTONIC_NS<space>TRACE_LINE
 *   flight    Until SIGTERM/SIGINT, keep a per-CPU ring buffer of isochronous
 *             EP 3 URB submissions/completions, xHCI errors, IRQs, softirqs,
 *             scheduler switches, ksoftirqd wakeups and C-state changes. A Ring
 *             Underrun on DCI 6 (EP 0x03 OUT) freezes the buffer; it is then
 *             printed between "# DUMP N offset_ns REALTIME_MINUS_MONOTONIC_NS"
 *             and "# END", cleared and re-armed, at most MAX_DUMPS times.
 *
 * The trace clock is CLOCK_MONOTONIC (seconds in each trace line).
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define INSTANCES "/sys/kernel/tracing/instances/"
#define MONITOR INSTANCES "eleven_rack_xhci"
#define FLIGHT INSTANCES "eleven_rack_flight"
#define MAX_DUMPS 5
#define FLIGHT_BUFFER_KB "1024"
/* Completion code is field2 bits 24-31: drop 1 (Success) and 13 (Short Packet). */
#define ERRORS "(field2 < 0x01000000 || field2 >= 0x02000000) && " \
               "(field2 < 0x0d000000 || field2 >= 0x0e000000)"
/* Ring Underrun (14) on endpoint ID 6 (field3 bits 16-20), any slot. */
#define UNDERRUN "field2 >= 0x0e000000 && field2 < 0x0f000000"
#define PLAYBACK_DCI "field3 & 0x20000 && field3 & 0x40000 && !(field3 & 0x190000)"

struct event { const char *name, *filter; };

static const struct event monitor_events[] = {
    {"xhci-hcd/xhci_handle_event", ERRORS},
};

static const struct event flight_events[] = {
    {"xhci-hcd/xhci_handle_event", ERRORS},
    {"xhci-hcd/xhci_urb_enqueue", "type == 1 && epnum == 3"},
    {"xhci-hcd/xhci_urb_giveback", "type == 1 && epnum == 3"},
    {"irq/irq_handler_entry", NULL},
    {"irq/irq_handler_exit", NULL},
    {"irq/softirq_entry", NULL},
    {"irq/softirq_exit", NULL},
    {"sched/sched_switch", NULL},
    {"sched/sched_wakeup", "comm ~ \"ksoftirqd*\""},
    {"power/cpu_idle", NULL},
};

static volatile sig_atomic_t stop;
static void on_signal(int sig) { (void)sig; stop = 1; }

static int64_t now(clockid_t clock) {
    struct timespec t;
    clock_gettime(clock, &t);
    return (int64_t)t.tv_sec * 1000000000LL + t.tv_nsec;
}

static int write_file(const char *path, const char *value) {
    int fd = open(path, O_WRONLY | O_TRUNC | O_CLOEXEC);
    if (fd < 0) return -1;
    ssize_t length = (ssize_t)strlen(value);
    int result = write(fd, value, length) == length ? 0 : -1;
    int saved = errno;
    close(fd);
    errno = saved;
    return result;
}

static int write_at(const char *instance, const char *name, const char *file, const char *value) {
    char path[256];
    snprintf(path, sizeof path, "%s/events/%s/%s", instance, name, file);
    return write_file(path, value);
}

static void teardown(const char *instance, const struct event *events, size_t count) {
    for (size_t i = 0; i < count; i++)
        write_at(instance, events[i].name, "enable", "0");
    write_at(instance, "xhci-hcd/xhci_handle_event", "trigger", "!traceoff");
    if (rmdir(instance) && errno != ENOENT)
        fprintf(stderr, "Cannot remove trace instance: %s\n", strerror(errno));
}

static int setup(const char *instance, const struct event *events, size_t count, const char *buffer_kb) {
    /* An existing instance is left over from a killed helper; removing it
     * fails with EBUSY while another one still reads it. */
    if (mkdir(instance, 0700) &&
        (errno != EEXIST || rmdir(instance) || mkdir(instance, 0700))) {
        fprintf(stderr, "Cannot create trace instance: %s\n", strerror(errno));
        return -1;
    }
    char path[256];
    snprintf(path, sizeof path, "%s/trace_clock", instance);
    if (write_file(path, "mono")) goto fail;
    if (buffer_kb) {
        snprintf(path, sizeof path, "%s/buffer_size_kb", instance);
        if (write_file(path, buffer_kb)) goto fail;
    }
    for (size_t i = 0; i < count; i++) {
        if (events[i].filter && write_at(instance, events[i].name, "filter", events[i].filter)) goto fail;
        if (write_at(instance, events[i].name, "enable", "1")) goto fail;
    }
    return 0;
fail:
    fprintf(stderr, "Cannot set up %s: %s\n", instance, strerror(errno));
    teardown(instance, events, count);
    return -1;
}

#define COUNT(a) (sizeof(a) / sizeof((a)[0]))

static int monitor(void) {
    if (setup(MONITOR, monitor_events, COUNT(monitor_events), NULL)) return 3;
    int fd = open(MONITOR "/trace_pipe", O_RDONLY | O_CLOEXEC);
    if (fd < 0) {
        fprintf(stderr, "Cannot open trace_pipe: %s\n", strerror(errno));
        teardown(MONITOR, monitor_events, COUNT(monitor_events));
        return 3;
    }
    printf("# xhci_handle_event, completion codes other than Success/Short Packet\n");
    fflush(stdout);
    char buffer[8192], line[1024];
    size_t used = 0;
    while (!stop) {
        ssize_t n = read(fd, buffer, sizeof buffer);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) break;
        int64_t offset = now(CLOCK_REALTIME) - now(CLOCK_MONOTONIC);
        for (ssize_t i = 0; i < n; i++) {
            if (buffer[i] != '\n') {
                if (used < sizeof line - 1) line[used++] = buffer[i];
                continue;
            }
            line[used] = 0;
            printf("%lld %s\n", (long long)offset, line);
            used = 0;
        }
        fflush(stdout);
    }
    close(fd);
    teardown(MONITOR, monitor_events, COUNT(monitor_events));
    return 0;
}

static int arm_trigger(const char **used) {
    /* Prefer the playback endpoint only; older filter parsers may reject '&'. */
    if (!write_at(FLIGHT, "xhci-hcd/xhci_handle_event", "trigger",
                  "traceoff if " UNDERRUN " && " PLAYBACK_DCI)) {
        *used = "Ring Underrun on DCI 6";
        return 0;
    }
    if (!write_at(FLIGHT, "xhci-hcd/xhci_handle_event", "trigger", "traceoff if " UNDERRUN)) {
        *used = "any Ring Underrun";
        return 0;
    }
    return -1;
}

static int dump(void) {
    int fd = open(FLIGHT "/trace", O_RDONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    char buffer[65536];
    ssize_t n;
    while ((n = read(fd, buffer, sizeof buffer)) > 0 || (n < 0 && errno == EINTR))
        if (n > 0) fwrite(buffer, 1, n, stdout);
    close(fd);
    return 0;
}

static int flight(void) {
    const char *trigger;
    if (setup(FLIGHT, flight_events, COUNT(flight_events), FLIGHT_BUFFER_KB)) return 3;
    if (arm_trigger(&trigger)) {
        fprintf(stderr, "Cannot set underrun trigger: %s\n", strerror(errno));
        teardown(FLIGHT, flight_events, COUNT(flight_events));
        return 3;
    }
    printf("# flight recorder armed; trigger: %s\n", trigger);
    fflush(stdout);
    int dumps = 0;
    while (!stop) {
        struct timespec pause = {0, 50000000};
        nanosleep(&pause, NULL);
        char on[4] = {0};
        int fd = open(FLIGHT "/tracing_on", O_RDONLY | O_CLOEXEC);
        if (fd < 0) break;
        ssize_t n = read(fd, on, sizeof on - 1);
        close(fd);
        if (n <= 0 || on[0] != '0' || dumps >= MAX_DUMPS) continue;
        printf("# DUMP %d offset_ns %lld\n", dumps++,
               (long long)(now(CLOCK_REALTIME) - now(CLOCK_MONOTONIC)));
        dump();
        printf("# END\n");
        fflush(stdout);
        if (dumps < MAX_DUMPS) {
            write_file(FLIGHT "/trace", "");   /* O_TRUNC clears the buffer */
            write_file(FLIGHT "/tracing_on", "1");
        }
    }
    teardown(FLIGHT, flight_events, COUNT(flight_events));
    return 0;
}

int main(int argc, char **argv) {
    struct sigaction action;
    memset(&action, 0, sizeof action);
    action.sa_handler = on_signal; /* no SA_RESTART: a signal ends the blocking read */
    sigaction(SIGTERM, &action, NULL);
    sigaction(SIGINT, &action, NULL);
    if (argc == 2 && !strcmp(argv[1], "monitor")) return monitor();
    if (argc == 2 && !strcmp(argv[1], "flight")) return flight();
    if (argc == 2 && !strcmp(argv[1], "check")) {
        const char *trigger;
        if (setup(MONITOR, monitor_events, COUNT(monitor_events), NULL)) return 3;
        teardown(MONITOR, monitor_events, COUNT(monitor_events));
        if (setup(FLIGHT, flight_events, COUNT(flight_events), FLIGHT_BUFFER_KB)) return 3;
        int armed = arm_trigger(&trigger);
        teardown(FLIGHT, flight_events, COUNT(flight_events));
        if (armed) {
            fprintf(stderr, "Cannot set underrun trigger: %s\n", strerror(errno));
            return 3;
        }
        printf("ok (flight trigger: %s)\n", trigger);
        return 0;
    }
    fprintf(stderr, "Usage: %s check|monitor|flight\n", argv[0]);
    return 2;
}

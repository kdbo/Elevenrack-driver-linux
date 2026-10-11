/* SPDX-License-Identifier: MIT
 * JACK loopback diagnostic. Only a test burst is output; capture is never
 * fed back. Minimal public JACK ABI declarations avoid a build-time SDK need.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <unistd.h>
#include <signal.h>
#include <string.h>
#include <time.h>
typedef uint32_t jack_nframes_t;
typedef struct _jack_client jack_client_t;
typedef struct _jack_port jack_port_t;
extern jack_client_t *jack_client_open(const char *, unsigned, unsigned *, ...);
extern int jack_client_close(jack_client_t *);
extern jack_port_t *jack_port_register(jack_client_t *, const char *, const char *, unsigned long, unsigned long);
extern void *jack_port_get_buffer(jack_port_t *, jack_nframes_t);
extern const char *jack_port_name(const jack_port_t *);
extern int jack_set_process_callback(jack_client_t *, int (*)(jack_nframes_t, void *), void *);
extern int jack_set_xrun_callback(jack_client_t *, int (*)(void *), void *);
extern int jack_activate(jack_client_t *);
extern int jack_deactivate(jack_client_t *);
extern int jack_connect(jack_client_t *, const char *, const char *);
extern jack_nframes_t jack_get_sample_rate(jack_client_t *);
extern jack_nframes_t jack_get_buffer_size(jack_client_t *);
typedef struct { jack_nframes_t min, max; } latency_range;
extern void jack_port_get_latency_range(jack_port_t *, int, latency_range *);
extern jack_port_t *jack_port_by_name(jack_client_t *, const char *);
static jack_port_t *input, *output;
static float *recording, *stimulus;
static unsigned position, total, warmup;
struct callback_stamp { unsigned frame, frames; uint64_t realtime_ns, monotonic_ns; };
static struct callback_stamp *stamps;
static unsigned stamp_count, stamp_capacity;
struct latency_stamp { uint64_t realtime_ns; latency_range capture, playback; };
static struct latency_stamp *latency_stamps;
static unsigned latency_count;
static volatile sig_atomic_t stamp_overflow;
static uint64_t ns(const struct timespec *t) {
    return (uint64_t)t->tv_sec * 1000000000ULL + t->tv_nsec;
}
static volatile sig_atomic_t done, xruns;
static volatile sig_atomic_t interrupted;
static void stop_signal(int sig) { (void)sig; interrupted=1; }
static uint32_t random_state=0x12345678;
static double noise(void) { random_state ^= random_state<<13; random_state ^= random_state>>17; random_state ^= random_state<<5; return 2.0*random_state/4294967295.0-1.0; }
static volatile sig_atomic_t warmup_xruns, post_recording_xruns;
static int xrun(void *unused) {
    (void)unused;
    if (warmup) warmup_xruns++;
    else if (position < total) xruns++;
    else post_recording_xruns++;
    return 0;
}
static int process(jack_nframes_t n, void *unused) {
    (void)unused;
    if (!warmup && position < total) {
        if (stamp_count < stamp_capacity) {
            struct timespec real, mono;
            clock_gettime(CLOCK_REALTIME, &real);
            clock_gettime(CLOCK_MONOTONIC_RAW, &mono);
            stamps[stamp_count++] = (struct callback_stamp){position, n, ns(&real), ns(&mono)};
        } else stamp_overflow = 1;
    }
    float *in = jack_port_get_buffer(input, n);
    float *out = jack_port_get_buffer(output, n);
    if (warmup) {
        memset(out, 0, n * sizeof(float));
        warmup = warmup > n ? warmup - n : 0;
        return 0;
    }
    for (unsigned i=0; i<n; ++i) {
        out[i] = position < total ? stimulus[position] : 0;
        if (position < total) recording[position++] = in[i];
    }
    if (position >= total) done = 1;
    return 0;
}
int main(int argc, char **argv) {
    if (argc != 4) { fprintf(stderr,"Usage: %s playback-terminal capture-terminal output.raw\n",argv[0]); return 2; }
    unsigned status=0;
    jack_client_t *client=jack_client_open("eleven-loopback-test",1,&status);
    if (!client) { fprintf(stderr,"JACK open failed: %u\n",status); return 1; }
    unsigned rate=jack_get_sample_rate(client), quantum=jack_get_buffer_size(client);
    /* An idle PipeWire JACK client initially advertises the default graph rate.
     * Use the explicitly forced test rate for buffer allocation and stimuli;
     * the runner verifies settled graph and both hardware streams separately. */
    const char *requested_rate = getenv("ELEVEN_TEST_RATE");
    if (requested_rate) rate = (unsigned)strtoul(requested_rate, NULL, 10);
    if (rate!=44100 && rate!=48000 && rate!=88200 && rate!=96000) { fprintf(stderr,"Unsupported sample rate\n"); jack_client_close(client); return 1; }
    unsigned warmup_seconds=3;
    const char *requested_warmup=getenv("ELEVEN_TEST_WARMUP_SECONDS");
    if (requested_warmup) {
        char *end;
        unsigned long seconds=strtoul(requested_warmup,&end,10);
        if (*end || seconds>6) { fprintf(stderr,"Warmup must be 0..6 seconds\n"); jack_client_close(client); return 1; }
        warmup_seconds=(unsigned)seconds;
    }
    warmup=rate*warmup_seconds;
    unsigned seconds=8;
    const char *signal_name=getenv("ELEVEN_TEST_SIGNAL");
    const char *duration=getenv("ELEVEN_TEST_SECONDS");
    if (duration) {
        char *end; unsigned long value=strtoul(duration,&end,10);
        if (*end || value<1 || value>1800) { fprintf(stderr,"Duration must be 1..1800 seconds\n"); return 2; }
        seconds=(unsigned)value;
    }
    if (signal_name && strcmp(signal_name,"sine") && strcmp(signal_name,"white") && strcmp(signal_name,"pink") && strcmp(signal_name,"multitone")) return 2;
    unsigned polls=(seconds+warmup_seconds+10)*10;
    latency_stamps=calloc(polls,sizeof(*latency_stamps));
    signal(SIGINT,stop_signal); signal(SIGTERM,stop_signal);
    total=rate*seconds; recording=calloc(total,sizeof(float)); stimulus=calloc(total,sizeof(float));
    stamp_capacity=total/32+1024;
    stamps=calloc(stamp_capacity,sizeof(*stamps));
    if (!recording || !stimulus || !stamps || !latency_stamps) return 1;
    if (!signal_name) {
        for (unsigned start=rate/2; start<rate*7 && start<total; start+=rate)
            for (unsigned j=0;j<rate/100 && start+j<total;j++) stimulus[start+j]=0.0316227766*sin(2*M_PI*997*j/rate)*pow(sin(M_PI*j/(rate/100)),2);
    } else {
        double b0=0,b1=0,b2=0,b3=0,b4=0,b5=0,b6=0;
        for (unsigned i=0;i<total;i++) {
            double w=noise(), value;
            if (!strcmp(signal_name,"sine")) value=sin(2*M_PI*997*i/rate);
            else if (!strcmp(signal_name,"multitone"))
                value=(sin(2*M_PI*431*i/rate)+sin(2*M_PI*997*i/rate)+
                       sin(2*M_PI*1871*i/rate)+sin(2*M_PI*2973*i/rate))*.25;
            else if (!strcmp(signal_name,"white")) value=w;
            else {
                /* Paul Kellet pink-noise filter; deterministic seed for replay. */
                b0=.99886*b0+w*.0555179; b1=.99332*b1+w*.0750759;
                b2=.969*b2+w*.153852; b3=.8665*b3+w*.3104856;
                b4=.55*b4+w*.5329522; b5=-.7616*b5-w*.016898;
                value=(b0+b1+b2+b3+b4+b5+b6+w*.5362)*.11; b6=w*.115926;
            }
            double fade=fmin(1.0,fmin((double)i/(rate*.02),(double)(total-1-i)/(rate*.02)));
            stimulus[i]=(float)(.0316227766*value*fade);
        }
    }
    input=jack_port_register(client,"in","32 bit float mono audio",1,0);
    output=jack_port_register(client,"out","32 bit float mono audio",2,0);
    if (!input || !output || jack_set_process_callback(client,process,NULL) || jack_set_xrun_callback(client,xrun,NULL) || jack_activate(client)) return 1;
    if (jack_connect(client,jack_port_name(output),argv[1]) || jack_connect(client,argv[2],jack_port_name(input))) {
        fprintf(stderr,"Cannot connect physical ports\n"); jack_deactivate(client); jack_client_close(client); return 1;
    }
    latency_range capture={0},playback={0};
    jack_port_t *p=jack_port_by_name(client,argv[1]), *c=jack_port_by_name(client,argv[2]);
    if (!p || !c) return 1;
    jack_port_get_latency_range(p,1,&playback); jack_port_get_latency_range(c,0,&capture);
    printf("rate=%u quantum=%u capture=%u..%u playback=%u..%u\n",rate,quantum,capture.min,capture.max,playback.min,playback.max);
    for (unsigned i=0;!done && !interrupted && i<polls;i++) {
        usleep(100000);
        struct timespec t;
        clock_gettime(CLOCK_REALTIME, &t);
        struct latency_stamp *entry = &latency_stamps[latency_count++];
        entry->realtime_ns = ns(&t);
        jack_port_get_latency_range(c,0,&entry->capture);
        jack_port_get_latency_range(p,1,&entry->playback);
    }
    jack_port_get_latency_range(p,1,&playback); jack_port_get_latency_range(c,0,&capture);
    printf("settled rate=%u quantum=%u capture=%u..%u playback=%u..%u\n",
           jack_get_sample_rate(client),jack_get_buffer_size(client),capture.min,capture.max,playback.min,playback.max);
    latency_range client_capture={0},client_playback={0};
    jack_port_get_latency_range(input,0,&client_capture);
    jack_port_get_latency_range(output,1,&client_playback);
    printf("client capture=%u..%u playback=%u..%u\n",
           client_capture.min,client_capture.max,client_playback.min,client_playback.max);
    jack_deactivate(client); jack_client_close(client);
    if (!done) fprintf(stderr,"Incomplete recording\n");
    printf("xruns=%d\n", (int)xruns);
    printf("warmup_xruns=%d post_recording_xruns=%d\n", (int)warmup_xruns, (int)post_recording_xruns);
    if (stamp_overflow) { fprintf(stderr,"Timestamp buffer overflow\n"); return 1; }
    if (xruns && !signal_name) { fprintf(stderr,"Xrun invalidates measurement\n"); return 1; }
    FILE *f=fopen(argv[3],"wb");
    if (!f || fwrite(recording,sizeof(float),position,f)!=position) return 1;
    fclose(f);
    if (signal_name) {
        char reference[4096];
        if (snprintf(reference,sizeof(reference),"%s.reference.raw",argv[3]) >= (int)sizeof(reference)) return 1;
        f=fopen(reference,"wb");
        if (!f || fwrite(stimulus,sizeof(float),position,f)!=position || fclose(f)) return 1;
    }
    char *name=malloc(strlen(argv[3])+32);
    if (!name) return 1;
    sprintf(name,"%s.timestamps.csv",argv[3]);
    f=fopen(name,"w");
    if (!f) return 1;
    fprintf(f,"frame,frames,realtime_ns,monotonic_raw_ns\n");
    for (unsigned i=0;i<stamp_count;i++) {
        struct callback_stamp *s=&stamps[i];
        if (fprintf(f,"%u,%u,%llu,%llu\n",s->frame,s->frames,
                    (unsigned long long)s->realtime_ns,
                    (unsigned long long)s->monotonic_ns)<0) return 1;
    }
    if (fclose(f)) return 1;
    sprintf(name,"%s.latency.csv",argv[3]);
    f=fopen(name,"w");
    if (!f) return 1;
    fprintf(f,"realtime_ns,capture_min,capture_max,playback_min,playback_max\n");
    for (unsigned i=0;i<latency_count;i++) {
        struct latency_stamp *entry=&latency_stamps[i];
        fprintf(f,"%llu,%u,%u,%u,%u\n",(unsigned long long)entry->realtime_ns,
                entry->capture.min,entry->capture.max,entry->playback.min,entry->playback.max);
    }
    if (fclose(f)) return 1;
    free(name); free(stamps); free(recording); free(stimulus); free(latency_stamps); return (!done || xruns) ? 1 : 0;
}

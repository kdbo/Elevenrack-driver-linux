/* SPDX-License-Identifier: MIT
 * Direct ALSA duplex diagnostic. No input is routed back to playback.
 */
#include <alsa/asoundlib.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <math.h>
#include <unistd.h>
#include <time.h>

static void check(int err, const char *what) {
    if (err < 0) { fprintf(stderr, "%s: %s\n", what, snd_strerror(err)); exit(1); }
}
static void configure(snd_pcm_t *pcm, unsigned channels, unsigned period) {
    snd_pcm_hw_params_t *hw;
    snd_pcm_sw_params_t *sw;
    snd_pcm_hw_params_alloca(&hw);
    snd_pcm_sw_params_alloca(&sw);
    unsigned rate = 48000;
    snd_pcm_uframes_t per = period, buffer = period * 4;
    check(snd_pcm_hw_params_any(pcm, hw), "hw params");
    check(snd_pcm_hw_params_set_access(pcm, hw, SND_PCM_ACCESS_RW_INTERLEAVED), "access");
    check(snd_pcm_hw_params_set_format(pcm, hw, SND_PCM_FORMAT_S32_LE), "format");
    check(snd_pcm_hw_params_set_channels(pcm, hw, channels), "channels");
    check(snd_pcm_hw_params_set_rate(pcm, hw, rate, 0), "rate");
    check(snd_pcm_hw_params_set_period_size_near(pcm, hw, &per, NULL), "period");
    check(snd_pcm_hw_params_set_buffer_size_near(pcm, hw, &buffer), "buffer");
    check(snd_pcm_hw_params(pcm, hw), "apply hw params");
    check(snd_pcm_sw_params_current(pcm, sw), "sw params");
    check(snd_pcm_sw_params_set_start_threshold(pcm, sw, buffer), "start threshold");
    check(snd_pcm_sw_params_set_avail_min(pcm, sw, per), "avail min");
    check(snd_pcm_sw_params(pcm, sw), "apply sw params");
    printf("%s channels=%u rate=%u period=%lu buffer=%lu\n",
           snd_pcm_stream(pcm) == SND_PCM_STREAM_PLAYBACK ? "playback" : "capture",
           channels, rate, (unsigned long)per, (unsigned long)buffer);
}
int main(int argc, char **argv) {
    if (argc != 4) { fprintf(stderr, "Usage: %s hw:CARD,0 period output.raw\n", argv[0]); return 2; }
    unsigned period = atoi(argv[2]);
    if (period != 64 && period != 128 && period != 256) return 2;
    const unsigned total = 144000;
    int32_t *out = calloc((total+4800) * 6, sizeof(int32_t));
    int32_t *in = calloc(total * 8, sizeof(int32_t));
    if (!out || !in) return 1;
    /* -30 dBFS burst, on playback channel 1 only, at 0.5, 1.5, 2.5 s. */
    for (unsigned start = 24000; start < total; start += 48000)
        for (unsigned j = 0; j < 480; ++j)
            out[(start+j)*6] = (int32_t)(67909395.0 * sin(2*M_PI*997*j/48000.0)
                                       * pow(sin(M_PI*j/480.0),2));
    snd_pcm_t *p, *c;
    check(snd_pcm_open(&p, argv[1], SND_PCM_STREAM_PLAYBACK, SND_PCM_NONBLOCK), "open playback");
    check(snd_pcm_open(&c, argv[1], SND_PCM_STREAM_CAPTURE, SND_PCM_NONBLOCK), "open capture");
    configure(p,6,period); configure(c,8,period);
    check(snd_pcm_prepare(p), "prepare playback");
    check(snd_pcm_prepare(c), "prepare capture");
    check(snd_pcm_link(p,c), "link duplex streams (required for shared start)");
    /* Prime less than the start threshold; start both explicitly. */
    snd_pcm_sframes_t primed = snd_pcm_writei(p,out,period);
    check((int)primed,"prime playback");
    check(snd_pcm_start(p), "start linked streams");
    unsigned written = primed, captured = 0;
    struct timespec begin,now;
    clock_gettime(CLOCK_MONOTONIC,&begin);
    unsigned count = 0;
    while (captured < total) {
        if (written < total+4800) {
            unsigned n = total+4800-written; if (n>period) n=period;
            snd_pcm_sframes_t got=snd_pcm_writei(p,out+written*6,n);
            if (got>=0) written+=got; else if (got != -EAGAIN) check((int)got,"playback (xrun invalidates test)");
        }
        unsigned n=total-captured; if(n>period) n=period;
        snd_pcm_sframes_t got=snd_pcm_readi(c,in+captured*8,n);
        if(got>=0) captured+=got; else if(got != -EAGAIN) check((int)got,"capture (xrun invalidates test)");
        if (++count % 200 == 0) {
            snd_pcm_sframes_t pd,cd;
            check(snd_pcm_delay(p,&pd),"playback delay");
            check(snd_pcm_delay(c,&cd),"capture delay");
            printf("delay written=%u captured=%u playback=%ld capture=%ld\n",written,captured,(long)pd,(long)cd);
        }
        clock_gettime(CLOCK_MONOTONIC,&now);
        if (now.tv_sec-begin.tv_sec > 10) { fprintf(stderr,"Test timeout\n"); return 1; }
        usleep(100);
    }
    snd_pcm_drop(p); snd_pcm_unlink(p); snd_pcm_close(c); snd_pcm_close(p);
    FILE *f=fopen(argv[3],"wb");
    if(!f) { perror("output"); return 1; }
    for(unsigned i=0;i<total;i++) if(fwrite(&in[i*8+6],sizeof(int32_t),1,f)!=1) return 1;
    fclose(f);
    printf("Captured channel 7, %u frames; stimulus starts at 24000,72000,120000\n",total);
    free(out); free(in); return 0;
}

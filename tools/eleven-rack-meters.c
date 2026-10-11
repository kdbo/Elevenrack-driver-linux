/* SPDX-License-Identifier: MIT
 * Read-only JACK peak monitor: capture ports and playback monitor ports only.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <signal.h>
#include <stdatomic.h>
#include <math.h>
typedef uint32_t jack_nframes_t;
typedef struct _jack_client jack_client_t;
typedef struct _jack_port jack_port_t;
extern jack_client_t *jack_client_open(const char *,unsigned,unsigned *,...);
extern int jack_client_close(jack_client_t *);
extern jack_port_t *jack_port_register(jack_client_t *,const char *,const char *,unsigned long,unsigned long);
extern void *jack_port_get_buffer(jack_port_t *,jack_nframes_t);
extern const char *jack_port_name(const jack_port_t *);
extern int jack_set_process_callback(jack_client_t *,int (*)(jack_nframes_t,void *),void *);
extern int jack_activate(jack_client_t *);
extern int jack_connect(jack_client_t *,const char *,const char *);
extern int jack_port_connected(const jack_port_t *);
static jack_port_t *ports[14];
static _Atomic float peaks[14];
static volatile sig_atomic_t stopping;
static void stop(int sig) { (void)sig; stopping=1; }
static int process(jack_nframes_t frames,void *unused) {
    (void)unused;
    for (int c=0;c<14;c++) {
        const float *audio=jack_port_get_buffer(ports[c],frames);
        float peak=0;
        for (jack_nframes_t i=0;i<frames;i++) if (isfinite(audio[i]) && fabsf(audio[i])>peak) peak=fabsf(audio[i]);
        float old=atomic_load_explicit(&peaks[c],memory_order_relaxed);
        while (peak>old && !atomic_compare_exchange_weak_explicit(&peaks[c],&old,peak,memory_order_relaxed,memory_order_relaxed)) {}
    }
    return 0;
}
int main(void) {
    const char *sources[14]={
        "Eleven Rack Inputs:Guitar In","Eleven Rack Inputs:Mic In",
        "Eleven Rack Inputs:Eleven Rig L","Eleven Rack Inputs:Eleven Rig R",
        "Eleven Rack Inputs:Digital In L","Eleven Rack Inputs:Digital In R",
        "Eleven Rack Inputs:Line In L","Eleven Rack Inputs:Line In R",
        "Eleven Rack Outputs:monitor_Main Out L","Eleven Rack Outputs:monitor_Main Out R",
        "Eleven Rack Outputs:monitor_Re-Amp L","Eleven Rack Outputs:monitor_Re-Amp R",
        "Eleven Rack Outputs:monitor_Digital Out L","Eleven Rack Outputs:monitor_Digital Out R"};
    unsigned status=0;
    if (!atomic_is_lock_free(&peaks[0])) return 1;
    jack_client_t *client=jack_client_open("eleven-control-meters",1,&status);
    if (!client) { fprintf(stderr,"JACK unavailable: %u\n",status);return 1; }
    for (int c=0;c<14;c++) {
        char name[32];snprintf(name,sizeof(name),"meter_%d",c);
        ports[c]=jack_port_register(client,name,"32 bit float mono audio",1,0);
        if (!ports[c]) { jack_client_close(client);return 1; }
    }
    if (jack_set_process_callback(client,process,NULL) || jack_activate(client)) {jack_client_close(client);return 1;}
    signal(SIGTERM,stop);signal(SIGINT,stop);
    setvbuf(stdout,NULL,_IOLBF,0);
    unsigned tick=0;
    while (!stopping) {
        for (int c=0;c<14;c++) {
            if (tick%5==0 && !jack_port_connected(ports[c])) jack_connect(client,sources[c],jack_port_name(ports[c]));
            float peak=atomic_exchange_explicit(&peaks[c],0,memory_order_relaxed);
            printf("%s%.6g",c?" ":"",jack_port_connected(ports[c])?peak:-1.0f);
        }
        puts("");usleep(200000);tick++;
    }
    jack_client_close(client);return 0;
}

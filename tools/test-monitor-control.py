#!/usr/bin/env python3
"""Exercise the actual kernel monitor callbacks with injected USB failures."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
STUBS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
typedef uint8_t u8; typedef uint16_t u16; typedef uint32_t __le32;
#define le32_to_cpu(x) (x)
#define SNDRV_CTL_ELEM_TYPE_INTEGER 1
#define SNDRV_CTL_ELEM_ACCESS_READ 1
#define ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define USB_DIR_OUT 0
#define USB_DIR_IN 0x80
#define USB_TYPE_CLASS 0x20
#define USB_RECIP_INTERFACE 1
#define SNDRV_CTL_EVENT_MASK_VALUE 1
#define SNDRV_CTL_ELEM_IFACE_MIXER 2
#define GFP_KERNEL 0
struct mutex { int held; };
static void mutex_init(struct mutex *m) { m->held=0; }
static void mutex_lock(struct mutex *m) { assert(!m->held); m->held=1; }
static void mutex_unlock(struct mutex *m) { assert(m->held); m->held=0; }
struct snd_usb_audio { void *dev, *card; };
struct snd_kcontrol { void *private_data; int id; void (*private_free)(struct snd_kcontrol *); };
struct usb_mixer_interface { struct snd_usb_audio *chip; struct { struct { int bInterfaceNumber; } desc; } *hostif; };
struct usb_mixer_elem_list { struct usb_mixer_interface *mixer; int id; struct snd_kcontrol *kctl; int (*resume)(struct usb_mixer_elem_list *); };
struct snd_ctl_elem_info { int type,count; struct { struct { long min,max,step; } integer; } value; };
struct snd_ctl_elem_value { struct { struct { unsigned int item[1]; } enumerated; struct { long value[1]; } integer; } value; };
struct snd_kcontrol_new { int iface,access; const char *name;
 int (*info)(struct snd_kcontrol *,struct snd_ctl_elem_info *);
 int (*get)(struct snd_kcontrol *,struct snd_ctl_elem_value *);
 int (*put)(struct snd_kcontrol *,struct snd_ctl_elem_value *); };
static void *snd_kcontrol_chip(struct snd_kcontrol *k) { return k->private_data; }
static int snd_ctl_enum_info(struct snd_ctl_elem_info *i,int n,int count,const char *const *names) { return 0; }
static int snd_usb_lock_shutdown(struct snd_usb_audio *c) { return 0; }
static void snd_usb_unlock_shutdown(struct snd_usb_audio *c) {}
static void snd_ctl_notify(void *c,int mask,int *id) {}
static unsigned int usb_sndctrlpipe(void *dev,int ep) { return 0; }
static unsigned int usb_rcvctrlpipe(void *dev,int ep) { return 1; }
static void *kzalloc(size_t n,int f) { return calloc(1,n); }
static void kfree(void *p) { free(p); }
static void snd_usb_mixer_elem_free(struct snd_kcontrol *k) { free(k->private_data); }
static struct snd_kcontrol *snd_ctl_new1(const struct snd_kcontrol_new *c,void *p) {
 struct snd_kcontrol *k=calloc(1,sizeof(*k)); k->private_data=p; return k; }
static struct snd_kcontrol *created;
static int snd_usb_mixer_add_list(struct usb_mixer_elem_list *l,struct snd_kcontrol *k,bool standard) {
 assert(!standard && (l->id==0x20 || l->id==0x80));
 if(created) { created->private_free(created); free(created); } l->kctl=k; created=k; return 0; }
struct transfer { u16 value,index,size; u8 bytes[4]; };
static struct transfer transfers[20];
static int count, fail_at=-1, rollback_fails, short_at=-1;
static int read_count, read_fail=-1, read_short=-1, gate_override=-1;
static u8 hardware_gate=2, hardware_gains[8][4], clock_source=1;
static __le32 clock_rate=48000;
static int snd_usb_ctl_msg(void *dev,unsigned int pipe,u8 request,u8 type,u16 value,u16 index,void *data,u16 size) {
 if(request==1) {
  assert(type==0xa1 && value==0x0100);
  int pos=read_count++;
  if(pos==read_fail) return -EPIPE;
  if(index==0x8001) { assert(size==1); *(u8 *)data=clock_source; }
  else { assert(index==((0x80+clock_source)<<8|1) && size==4); *(__le32 *)data=clock_rate; }
  return pos==read_short ? size-1 : size;
 }
 assert(request==3 && size<=4);
 if(type==0xa1) {
  int pos=read_count++;
  if(pos==read_fail) return -EPIPE;
  if(index==0x2001) {
   assert(value==0 && size==1);
   *(u8 *)data=gate_override<0 ? hardware_gate : gate_override;
  } else {
   int input=(value-0x27)/6;
   assert(index==0x4001 && size==4 && input>=0 && input<8 && value==0x27+6*input);
   memcpy(data,hardware_gains[input],4);
  }
  return pos==read_short ? size-1 : size;
 }
 int pos=count++;
 assert(request==3 && type==0x21 && size<=4 && pos<20);
 transfers[pos]=(struct transfer){.value=value,.index=index,.size=size};
 memcpy(transfers[pos].bytes,data,size);
 if(pos==fail_at || (rollback_fails && pos==fail_at+1)) return -EPIPE;
 if(pos==short_at) return size-1;
 if(index==0x2001) hardware_gate=*(u8 *)data;
 else memcpy(hardware_gains[(value-0x27)/6],data,4);
 return size;
}
'''
TESTS = r'''
int main(void) {
 struct snd_usb_audio chip={0};
 struct usb_mixer_interface mixer={.chip=&chip};
 typeof(*mixer.hostif) iface={.desc={.bInterfaceNumber=1}};
 mixer.hostif=&iface;
 assert(snd_eleven_monitor_create(&mixer)==0 && created && count==0);
 created->private_free(created); free(created); created=NULL;
 iface.desc.bInterfaceNumber=2;
 assert(snd_eleven_monitor_create(&mixer)==0 && !created && count==0);
 struct eleven_monitor monitor={.head={.mixer=&mixer}};
 struct snd_kcontrol k={.private_data=&monitor};
 struct snd_ctl_elem_value v={0};
 monitor.head.kctl=&k;
 assert(eleven_monitor_get(&k,&v)==0 && v.value.enumerated.item[0]==1 && read_count==1);
 v.value.enumerated.item[0]=0;
 assert(eleven_monitor_put(&k,&v)==-EINVAL && count==0);
 v.value.enumerated.item[0]=2;
 assert(eleven_monitor_put(&k,&v)==1 && count==9 && monitor.mode==2);
 assert(transfers[0].value==0 && transfers[0].index==0x2001 && transfers[0].bytes[0]==1);
 for(int i=0;i<8;i++) {
  assert(transfers[i+1].value==0x27+6*i && transfers[i+1].index==0x4001 && transfers[i+1].size==4);
  assert(memcmp(transfers[i+1].bytes,"\x00\x80\x00\x80",4)==0);
 }
 count=0; v.value.enumerated.item[0]=1;
 assert(eleven_monitor_put(&k,&v)==1 && count==1 && transfers[0].bytes[0]==2);
 for(int i=0;i<9;i++) {
  count=0; fail_at=i; monitor.mode=2; v.value.enumerated.item[0]=2;
  assert(eleven_monitor_put(&k,&v)==-EPIPE && count==i+2 && monitor.mode==1);
  assert(transfers[count-1].index==0x2001 && transfers[count-1].bytes[0]==2);
 }
 count=0; fail_at=3; rollback_fails=1;
 assert(eleven_monitor_put(&k,&v)==-EPIPE && monitor.mode==0);
 count=0; fail_at=-1; rollback_fails=0; short_at=2;
 assert(eleven_monitor_put(&k,&v)==-EIO && monitor.mode==1);
 monitor.mode=2; assert(eleven_monitor_resume(&monitor.head)==0 && monitor.mode==0);
 fail_at=short_at=read_fail=read_short=-1; rollback_fails=0; count=read_count=0;
 hardware_gate=2; monitor.mode=2;
 assert(eleven_monitor_get(&k,&v)==0 && v.value.enumerated.item[0]==1 && read_count==1);
 hardware_gate=1; read_count=0;
 for(int i=0;i<8;i++) memcpy(hardware_gains[i],"\x00\x80\x00\x80",4);
 assert(eleven_monitor_get(&k,&v)==0 && v.value.enumerated.item[0]==2 && read_count==9);
 hardware_gains[3][2]=1; read_count=0;
 assert(eleven_monitor_get(&k,&v)==0 && v.value.enumerated.item[0]==3 && read_count==5);
 hardware_gains[3][2]=0;
 for(int i=0;i<9;i++) {
  read_count=0; read_fail=i; monitor.mode=2;
  assert(eleven_monitor_get(&k,&v)==-EPIPE && monitor.mode==0);
 }
 read_count=0; read_fail=-1; read_short=8;
 assert(eleven_monitor_get(&k,&v)==-EIO && monitor.mode==0);
 read_short=-1; hardware_gate=7; read_count=0;
 assert(eleven_monitor_get(&k,&v)==0 && v.value.enumerated.item[0]==0 && read_count==1);
 hardware_gate=2; count=read_count=0; gate_override=2; v.value.enumerated.item[0]=2;
 assert(eleven_monitor_put(&k,&v)==-EIO && monitor.mode==1 && hardware_gate==2);
 gate_override=-1;
 for(int i=0;i<9;i++) {
  count=read_count=0; read_fail=i; v.value.enumerated.item[0]=2;
  assert(eleven_monitor_put(&k,&v)==-EPIPE && count==10 && hardware_gate==2 && monitor.mode==1);
 }
 read_fail=read_short=-1; read_count=0;
 struct usb_mixer_elem_list rate_head={.mixer=&mixer};
 struct snd_kcontrol rate_k={.private_data=&rate_head};
 assert(eleven_rate_get(&rate_k,&v)==0 && v.value.integer.value[0]==48000);
 for(clock_source=1;clock_source<=3;clock_source++) {
  clock_rate=44100; assert(eleven_rate_get(&rate_k,&v)==0 && v.value.integer.value[0]==44100);
 }
 clock_source=0; assert(eleven_rate_get(&rate_k,&v)==-EINVAL);
 clock_source=1; clock_rate=0; assert(eleven_rate_get(&rate_k,&v)==-ENODATA);
 clock_rate=48000;
 for(int i=0;i<2;i++) {
  read_count=0; read_fail=i; assert(eleven_rate_get(&rate_k,&v)==-EPIPE);
  read_fail=-1; read_count=0; read_short=i; assert(eleven_rate_get(&rate_k,&v)==-EIO);
  read_short=-1;
 }
 return 0;
}
'''

with tempfile.TemporaryDirectory(prefix='eleven-monitor-test-') as tmp:
    source = Path(tmp, 'test.c')
    header = (ROOT / 'packaging/mixer-eleven-rack.h').read_text().replace('#include <linux/mutex.h>', '')
    source.write_text(STUBS + header + TESTS)
    binary = Path(tmp, 'test')
    subprocess.run(['gcc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                    '-Wno-unused-parameter', '-Wno-unused-function', str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print('Monitoring writes, real readback, custom mixes, read failures, rollback and resume: PASS')

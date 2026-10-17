#include <math.h>
#include <stdlib.h>
/* Offline least-squares estimate; never used in the live audio path. */
int noise_fit(const float *x,const float *y,int start,int count,int lag,int half,double *h) {
 int m=2*half+1; double *a=calloc((size_t)m*(m+1),sizeof(double)); if(!a)return -1;
 for(int n=start;n<start+count;n++) for(int i=0;i<m;i++) {
  double xi=x[n+i-half];a[i*(m+1)+m]+=xi*y[n+lag];
  for(int j=0;j<m;j++) a[i*(m+1)+j]+=xi*x[n+j-half];
 }
 double trace=0;for(int i=0;i<m;i++)trace+=a[i*(m+1)+i];
 for(int i=0;i<m;i++)a[i*(m+1)+i]+=trace/m*1e-10;
 for(int k=0;k<m;k++) {
  int pivot=k;for(int i=k+1;i<m;i++)if(fabs(a[i*(m+1)+k])>fabs(a[pivot*(m+1)+k]))pivot=i;
  if(fabs(a[pivot*(m+1)+k])<1e-20){free(a);return -2;}
  for(int j=k;j<=m;j++){double t=a[k*(m+1)+j];a[k*(m+1)+j]=a[pivot*(m+1)+j];a[pivot*(m+1)+j]=t;}
  double d=a[k*(m+1)+k];for(int j=k;j<=m;j++)a[k*(m+1)+j]/=d;
  for(int i=0;i<m;i++)if(i!=k){double t=a[i*(m+1)+k];for(int j=k;j<=m;j++)a[i*(m+1)+j]-=t*a[k*(m+1)+j];}
 }
 for(int i=0;i<m;i++) { h[i]=a[i*(m+1)+m]; }
 free(a);return 0;
}
void noise_score(const float*x,const float*y,int start,int count,int lag,int half,const double*h,double*out){
 double dot=0,xx=0,yy=0,err=0,peak=0;
 for(int n=start;n<start+count;n++){
  double pred=0;for(int k=-half;k<=half;k++)pred+=h[k+half]*x[n+k];
  double actual=y[n+lag],e=actual-pred;dot+=pred*actual;xx+=pred*pred;yy+=actual*actual;err+=e*e;if(fabs(e)>peak)peak=fabs(e);
 }
 out[0]=xx>0&&yy>0?dot/sqrt(xx*yy):0;out[1]=yy>0?sqrt(err/yy):0;out[2]=peak;
}

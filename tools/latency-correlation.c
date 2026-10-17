#include <math.h>
#include <stddef.h>
/* Same normalized correlation as analyze-jack-loopback.py, for test analysis. */
int latency_peak(const float *samples, const double *reference, int width,
                 int search, double *score_out)
{
    double energy = 0, best = -1, signed_best = 0;
    int peak = -1;
    for (int j = 0; j < width; j++) energy += reference[j] * reference[j];
    for (int lag = 0; lag < search; lag++) {
        double norm = 0, dot = 0;
        for (int j = 0; j < width; j++) {
            double value = samples[lag+j];
            norm += value*value;
            dot += value*reference[j];
        }
        double score = norm ? dot / sqrt(energy*norm) : 0;
        if (fabs(score) > best) {best = fabs(score); signed_best = score; peak = lag;}
    }
    *score_out = signed_best;
    return peak;
}

/* Mean-removed correlation at a fixed alignment. Unlike latency_peak's score,
 * it ignores the DC/very-low-frequency drift that the AC-coupled analog input
 * removes, which otherwise lowers the score of pink-noise windows. */
double centered_correlation(const float *samples, const double *reference, int width)
{
    double sample_mean = 0, reference_mean = 0, sxy = 0, sxx = 0, syy = 0;
    for (int j = 0; j < width; j++) {sample_mean += samples[j]; reference_mean += reference[j];}
    sample_mean /= width;
    reference_mean /= width;
    for (int j = 0; j < width; j++) {
        double a = samples[j] - sample_mean, b = reference[j] - reference_mean;
        sxy += a*b; sxx += a*a; syy += b*b;
    }
    return sxx && syy ? sxy / sqrt(sxx*syy) : 0;
}

/* Full-stream screening complements sparse correlation windows. */
int regression_scan(const float *samples, int count)
{
    int flags=0, silent=0, repeated=0;
    for (int i=0; i<count; i++) {
        float value=samples[i];
        if (!isfinite(value)) flags|=1;
        if (fabs(value)>=.999) flags|=2;
        silent=fabs(value)<1e-8 ? silent+1 : 0;
        if (silent>=64) flags|=4;
        repeated=i && value==samples[i-1] ? repeated+1 : 0;
        if (repeated>=64) flags|=8;
    }
    return flags;
}

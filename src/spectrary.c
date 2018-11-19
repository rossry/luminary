#include <errno.h>
#include <string.h>

#include "spectrary.h"

struct timeval start;

double sum_avg_val;

FILE *fp;
int spectrary_n_lines = 0;

// double spectrary_time; // promoted to spectrary.h
double freq;
double val;

int spectrary_usec_elapsed() {
    struct timeval now;
    gettimeofday(&now, NULL);
    return (now.tv_usec - start.tv_usec) + (now.tv_sec - start.tv_sec)*1000*1000;// + 60*1000*1000;
}

void spectrary_delay() {
    int usec_elapsed = spectrary_usec_elapsed();
    
    if (spectrary_time*1000*1000 > usec_elapsed) {
        usleep(spectrary_time*1000*1000 - usec_elapsed);
    }
    
    #ifdef SPECTRARY_VERBOSE
        printf("%.3f sec (frame)\n", spectrary_time);
        printf("%.3f sec (elapsed)\n", spectrary_usec_elapsed()/1000000.0);
    #endif /* SPECTRARY_VERBOSE */
}

int spectrary_scanf() {
    spectrary_n_lines += 1;
    return fscanf(fp, "%lf\t%lf\t%lf", &spectrary_time, &freq, &val);
}

void spectrary_advance() {
    if (freq > SPECTRARY_BASE_FREQ) {
        while (freq > SPECTRARY_BASE_FREQ) {
            spectrary_scanf();
        }
    }
    while (freq < SPECTRARY_BASE_FREQ) {
        spectrary_scanf();
    }
}

void spectrary_init(char* filename) {
    gettimeofday(&start, NULL);
    
    fp = fopen(filename, "r"); // read mode
    if (fp == NULL) {
        fprintf(stderr, "%s: %s\n", strerror(errno), filename);
        exit(EXIT_FAILURE);
    }
    
    spectrary_avg_level = 0.0;
    freq = 0.0;
    
    spectrary_advance();
    
    /*
    while (spectrary_time*1000*1000 < spectrary_usec_elapsed()) {
        spectrary_scanf();
    }
    */
}

void spectrary_destroy() {
    fclose(fp);
}

void spectrary_update() {
    if (spectrary_time*1000*1000 > spectrary_usec_elapsed()) {
        return;
    }
    
    double freq_ubound;
    int n_val;
    double sum_val;
    
    freq_ubound = SPECTRARY_BASE_FREQ;
    
    sum_avg_val = 0.0;
    
    for (int freq_i=0; freq_i<SPECTRARY_FREQS; ++freq_i) {
        freq_ubound *= SPECTRARY_FREQ_WIDTH;
        
        n_val = 0;
        sum_val = 0.0;
        while (freq < freq_ubound && freq > 0.0) {
            n_val += 1;
            sum_val += val;
            spectrary_scanf();
        }
        
        spectrary_level[freq_i] = sum_val + spectrary_level[freq_i]*0.8;
        
        sum_avg_val += spectrary_level[freq_i];
    }
    
    spectrary_advance();
    
    spectrary_avg_level = sum_avg_val / SPECTRARY_FREQS;
}
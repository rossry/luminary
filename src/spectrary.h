#ifndef SPECTRARY_H
#define SPECTRARY_H

#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/time.h>

#define SPECTRARY_VERBOSE 0

#define SPECTRARY_FREQS         19
#define SPECTRARY_BASE_FREQ   27.0
#define SPECTRARY_FREQ_WIDTH  1.44

double spectrary_time; // the beginning of the next available FFT window
double spectrary_level[SPECTRARY_FREQS];
double spectrary_avg_level; // average value of spectrary_level

void spectrary_init(char* filename);
void spectrary_destroy();

// idempotent; iff time elapsed since _init has passed spectrary_time, then
// update spectrary_level from next FFT window and advance spectrary_time
void spectrary_update();

// sleep until time elapsed will equal spectrary_time
void spectrary_delay();

#endif /* SPECTRARY_H */

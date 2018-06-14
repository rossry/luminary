#include <unistd.h>
#include <stdlib.h>
#include <sys/time.h>

#include "constants.h"
#include "cellular.h"
#include "display.h"

double usec_time_elapsed(struct timeval *from, struct timeval *to) {
    return (double)(to->tv_usec - from->tv_usec) + (double)(to->tv_sec - from->tv_sec) * MILLION;
}

int main(int argc, char *argv[]) {
    display_init();
    
    int epoch = 0;
    
    int scratch[ROWS * COLS];
    
    int control_directive_0[ROWS * COLS];
    int control_directive_0_next[ROWS * COLS];
    int control_directive_1[ROWS * COLS];
    int control_directive_1_next[ROWS * COLS];
    int control_orth[ROWS * COLS];
    int control_orth_next[ROWS * COLS];
    int control_diag[ROWS * COLS];
    int control_diag_next[ROWS * COLS];
    
    int rainbow_0[ROWS * COLS];
    int rainbow_0_next[ROWS * COLS];
    int impatience_0[ROWS * COLS];
    
    int rainbow_1[ROWS * COLS];
    int rainbow_1_next[ROWS * COLS];
    int impatience_1[ROWS * COLS];
    
    int pressure_self[ROWS * COLS];
    int pressure_orth[ROWS * COLS];
    int pressure_orth_next[ROWS * COLS];
    int pressure_diag[ROWS * COLS];
    int pressure_diag_next[ROWS * COLS];
    
    // hand-tuned to radiate from a center 84 cells above the midpoint of the top side
    int waves_base[] = WAVES_BASE_ARRAY;
    
    int waves_base_z_orig = 0;
    int waves_orth[ROWS * COLS];
    int waves_orth_next[ROWS * COLS];
    int waves_diag[ROWS * COLS];
    int waves_diag_next[ROWS * COLS];
    
    int in_chr;
    
    for (int xy = 0; xy < ROWS * COLS; ++xy) {
        scratch[xy] = 0;
        
        control_directive_0[xy] = 0;
        control_directive_1[xy] = 0;
        control_orth[xy] = 0;
        control_diag[xy] = 0;
        
        rainbow_0[xy] = RAND_COLOR;
        impatience_0[xy] = 0;
        rainbow_1[xy] = RAND_COLOR;
        impatience_1[xy] = 0;
        
        pressure_self[xy] = 0;
        pressure_orth[xy] = 0;
        pressure_diag[xy] = 0;
        
        waves_orth[xy] = 0;
        waves_diag[xy] = 0;
    }
    
    struct timeval start, computed, drawn, refreshed, handled, slept, stop;
    double compute_avg, draw_avg, refresh_avg, wait_avg, sleep_avg, total_avg;
    compute_avg = draw_avg = refresh_avg = wait_avg = sleep_avg = total_avg = 0;
    
    gettimeofday(&start, NULL);
    
    while (1) {
        ++epoch;
        
        for (int xy = 0; xy < ROWS * COLS; ++xy) {
            // evolve control_directive_(1|2), control_(orth|diag)
            if (xy == COLS*(ROWS-1) + COLS/2 // CR rrheingans-yoo for ntarleton: this should instead be pressure_switch_depressed(xy)
                && ((epoch + 3000) / 6000) % 2 == 0 // CR rrheingans-yoo for ntarleton: remove me
                && epoch > INITIALIZATION_EPOCHS // CR rrheingans-yoo for ntarleton: remove me
            ) {
                if (control_orth[xy] == 0) {
                    control_directive_0[xy] = PATTERN_FULL_RAINBOW;
                    control_directive_1[xy] = PATTERN_RAINBOW_SPOTLIGHTS;
                    control_orth[xy] = HIBERNATION_TICKS + TRANSITION_TICKS;
                } else if (control_orth[xy] < HIBERNATION_TICKS) {
                    control_orth[xy] = HIBERNATION_TICKS;
                }
            }
            if (control_orth[xy] < HIBERNATION_TICKS
                && control_directive_0[xy] != control_directive_1[xy]
                && RAND_SECONDARY_TRANSITION
            ) {
                control_directive_0[xy] = control_directive_1[xy];
                control_orth[xy] = HIBERNATION_TICKS + SECONDARY_TRANSITION_TICKS;
            }
            if (control_orth[xy] == 0
                && control_directive_0[xy] != PATTERN_BASE
                && RAND_SECONDARY_TRANSITION
            ) {
                control_directive_0[xy] = control_directive_1[xy] = PATTERN_BASE;
                control_orth[xy] = SECONDARY_TRANSITION_TICKS;
            }
            compute_decay(
                control_orth, control_diag,
                control_orth_next, control_diag_next,
                control_directive_0, control_directive_1,
                control_directive_0_next, control_directive_1_next,
                xy
            );
            
            if (epoch % WILDFIRE_SPEEDUP == 0) {
                // evolve rainbow_0
                rainbow_0_next[xy] = compute_cyclic(rainbow_0, impatience_0, xy);
                
                // evolve rainbow_1
                if (pressure_orth[xy] > 17) {
                    rainbow_1_next[xy] = -1;
                } else {
                    rainbow_1_next[xy] = compute_cyclic(rainbow_1, impatience_1, xy);
                }
                
                // evolve pressure_(orth|diag)
                compute_decay(
                    pressure_orth, pressure_diag,
                    pressure_orth_next, pressure_diag_next,
                    scratch, scratch, scratch, scratch,
                    xy
                );
                if (rand() % (ROWS * COLS) == 0) { // CR rrheingans-yoo for ntarleton: this should instead be pressure_switch_depressed(xy)
                    pressure_self[xy] = PRESSURE_DELAY_EPOCHS;
                }
                if (pressure_self[xy] > 0) {
                    pressure_self[xy] -= 1;
                    pressure_orth_next[xy] = pressure_diag_next[xy] = PRESSURE_RADIUS_TICKS;
                }
            }
            
            // evolve waves_(orth|diag)
            compute_decay(
                waves_orth, waves_diag,
                waves_orth_next, waves_diag_next,
                scratch, scratch, scratch, scratch,
            xy);
        }
        
        // drive waves_(orth|diag)'s top row
        waves_base_z_orig += 17;
        for (int x = 0; x < COLS; ++x) {
            waves_orth_next[x] = waves_diag_next[x] = waves_base[x+WAVES_BASE_X_ORIG] + waves_base_z_orig;
        }
        
        gettimeofday(&computed, NULL);
        
        int zz;
        for (int xy = 0; xy < ROWS * COLS; ++xy) {
            if (epoch > INITIALIZATION_EPOCHS) {
                switch (control_directive_0_next[xy]) {
                
                case PATTERN_RAINBOW_SPOTLIGHTS:
                    if (rainbow_1_next[xy] == -1) {
                        display_color(xy, rainbow_0_next[xy]);
                    } else {
                        display_color(xy, rainbow_1_next[xy] + MAKE_GREY);
                    }
                    break;
                
                case PATTERN_FULL_RAINBOW:
                    display_color(xy, rainbow_0_next[xy]);
                    break;
                
                case PATTERN_BASE:
                    zz = (waves_orth_next[xy] / 17) % 480;
                    zz = min(zz, COLORS-zz);
                    
                    display_color(xy,
                        max(6,
                            min(rainbow_1_next[xy],
                                COLORS - rainbow_1_next[xy]
                            ) + zz
                        ) + MAKE_GREY
                    );
                }
            }
            
            // increment all states
            control_directive_0[xy] = control_directive_0_next[xy];
            control_directive_1[xy] = control_directive_1_next[xy];
            control_orth[xy] = control_orth_next[xy];
            control_diag[xy] = control_diag_next[xy];
            
            rainbow_0[xy] = rainbow_0_next[xy];
            rainbow_1[xy] = rainbow_1_next[xy];
            
            pressure_orth[xy] = pressure_orth_next[xy];
            pressure_diag[xy] = pressure_diag_next[xy];
            
            waves_orth[xy] = waves_orth_next[xy];
            waves_diag[xy] = waves_diag_next[xy];
        }
        
        gettimeofday(&drawn, NULL);
        
        if (epoch > INITIALIZATION_EPOCHS) {
            display_flush();
            
            gettimeofday(&refreshed, NULL);
            
            if (usec_time_elapsed(&start, &refreshed) < USABLE_USEC_PER_EPOCH) {
                timeout(USABLE_MSEC_PER_EPOCH - usec_time_elapsed(&start, &handled) / THOUSAND);
                in_chr = getch();
            }
            
            if (in_chr > 0 && in_chr < 256) {
                mvprintw(ROWS+0, 0, "input: %c", in_chr);
                // CR rrheingans-yoo: do something!
            }
            
            gettimeofday(&handled, NULL);
            
            if (usec_time_elapsed(&start, &handled) < USEC_PER_EPOCH) {
                usleep(USEC_PER_EPOCH - usec_time_elapsed(&start, &handled));
            }
        } else {
            if (epoch % 10 == 0) {
                mvprintw(0, 0, "initializing (%.0f%%)", 100.0 * epoch / INITIALIZATION_EPOCHS);
                refresh();
            }
            gettimeofday(&refreshed, NULL);
            gettimeofday(&handled, NULL);
        }
        
        gettimeofday(&slept, NULL);
        
        gettimeofday(&stop, NULL);
        
        // diagnostic printouts
        compute_avg = 0.99*compute_avg + 0.01*usec_time_elapsed(&start, &computed);
        draw_avg = 0.99*draw_avg + 0.01*usec_time_elapsed(&computed, &drawn);
        refresh_avg = 0.99*refresh_avg + 0.01*usec_time_elapsed(&drawn, &refreshed);
        wait_avg = 0.99*wait_avg + 0.01*usec_time_elapsed(&refreshed, &handled);
        sleep_avg = 0.99*sleep_avg + 0.01*usec_time_elapsed(&handled, &slept);
        total_avg = 0.99*total_avg + 0.01*usec_time_elapsed(&start, &stop);
        mvprintw(ROWS+0, 2*COLS-15, "compute:%5.1fms", compute_avg / THOUSAND);
        mvprintw(ROWS+1, 2*COLS-15, "draw:   %5.1fms", draw_avg / THOUSAND);
        mvprintw(ROWS+2, 2*COLS-15, "refresh:%5.1fms", refresh_avg / THOUSAND);
        mvprintw(ROWS+3, 2*COLS-15, "wait:   %5.1fms", wait_avg / THOUSAND);
        mvprintw(ROWS+4, 2*COLS-15, "sleep:  %5.1fms", sleep_avg / THOUSAND);
        mvprintw(ROWS+0, 2*COLS-37, "epoch: %7d", epoch);
        mvprintw(ROWS+1, 2*COLS-37, "Hz:    %7.1f", 1 / (total_avg / MILLION));
        mvprintw(ROWS+1, 1, "control_orth[0] = %7d", control_orth[0]);
        
        start = stop;
    }
    
    endwin();
    
    return 0;
}
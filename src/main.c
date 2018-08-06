#include <unistd.h>
#include <stdlib.h>
#include <sys/time.h>

#include "constants.h"
#include "cellular.h"
#include "display.h"

int sinusoid[] = { 6, 6, 6, 6, 6, 7, 7, 8, 8, 8, 9, 10, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 26, 27, 28, 29, 31, 32, 33, 35, 36, 37, 38, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 54, 55, 56, 56, 56, 57, 57, 58, 58, 58, 58, 58, 58, 58, 58, 58, 57, 57, 56, 56, 56, 55, 54, 54, 53, 52, 51, 50, 49, 48, 47, 46, 45, 44, 43, 42, 41, 40, 38, 37, 36, 35, 33, 32, 31, 29, 28, 27, 26, 24, 23, 22, 21, 20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 10, 9, 8, 8, 8, 7, 7, 6, 6, 6, 6};
#define BOUNCE_ROWS(y) (sinusoid[(y) % 128])
/*#define BOUNCE_ROWS_X(y) (((y) / ROWS) % 2 ? ROWS - (y) % ROWS : (y) % ROWS)*/

double usec_time_elapsed(struct timeval *from, struct timeval *to) {
    return (double)(to->tv_usec - from->tv_usec) + (double)(to->tv_sec - from->tv_sec) * MILLION;
}

int main(int argc, char *argv[]) {
    display_init();
    
    srand(5);
    
    int epoch = -1;
    
    int scratch[ROWS * COLS];
    
    int control_directive_0[ROWS * COLS];
    int control_directive_0_next[ROWS * COLS];
    int control_directive_1[ROWS * COLS];
    int control_directive_1_next[ROWS * COLS];
    int control_orth[ROWS * COLS];
    int control_orth_next[ROWS * COLS];
    int control_diag[ROWS * COLS];
    int control_diag_next[ROWS * COLS];
    
    int rainbow_tone[ROWS * COLS];
    
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
    //int waves_base[] = WAVES_BASE_ARRAY;
    
    int waves_base_z_orig = 0;
    int waves_orth[ROWS * COLS];
    int waves_orth_next[ROWS * COLS];
    int waves_diag[ROWS * COLS];
    int waves_diag_next[ROWS * COLS];
    
    hanabi_cell hanabi[ROWS * COLS];
    hanabi_cell hanabi_next[ROWS * COLS];
    int hanabi_seed_color[ROWS * COLS];
    
    //int in_chr = 0;
    
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
        
        rainbow_tone[xy] = 0;
        
        pressure_self[xy] = 0;
        pressure_orth[xy] = 0;
        pressure_diag[xy] = 0;
        
        waves_orth[xy] = 0;
        waves_diag[xy] = 0;
        
        hanabi[xy].color = 0;
        hanabi[xy].orth = 0;
        hanabi[xy].diag = 0;
        hanabi_seed_color[xy] = RAND_COLOR;
    }
    
    struct timeval start, computed, drawn, refreshed, handled, slept, stop;
    double compute_avg, draw_avg, refresh_avg, wait_avg, sleep_avg, total_avg;
    compute_avg = draw_avg = refresh_avg = wait_avg = sleep_avg = total_avg = 0;
    
    gettimeofday(&start, NULL);
    
    while (1) {
        ++epoch;
        
        for (int xy = 0; xy < ROWS * COLS; ++xy) {
            int x = xy % COLS;
            int y = xy / COLS;
            //if (y < PETAL_ROWS || x < FLOOR_COLS) {
            //if ((y >= 21 && y < ROWS - 21) || (x >= 21 && x < COLS - 21)) {
            if ((1
                    && x + y > BEVEL_RADIUS-2
                    && (COLS-1-x + y > BEVEL_RADIUS-2)
                    && (x + ROWS-1-y > BEVEL_RADIUS-2)
                    && (COLS-1-x + ROWS-1-y > BEVEL_RADIUS-2)
                )
                || x == BEVEL_RADIUS-2 || ROWS-1-x == BEVEL_RADIUS-2
                || y == BEVEL_RADIUS-2 || ROWS-1-y == BEVEL_RADIUS-2
            ) {
                // evolve control_directive_(1|2), control_(orth|diag)
                // CR rrheingans-yoo: move these overrides to the post-processing segment below
                /*
                if (xy == COLS*(ROWS-1) + FLOOR_COLS/2 // CR rrheingans-yoo for ntarleton: this should instead be pressure_switch_depressed(xy)
                    && ((epoch + 5000) / 6000) % 2 == 0 // CR rrheingans-yoo for ntarleton: remove me
                    && epoch > INITIALIZATION_EPOCHS + 1 // CR rrheingans-yoo for ntarleton: remove me
                ) {
                    if (control_orth[xy] == 0) {
                        control_directive_0[xy] = PATTERN_FULL_RAINBOW;
                        control_directive_1[xy] = TWO_TONES;
                        control_orth[xy] = HIBERNATION_TICKS + TRANSITION_TICKS;
                    } else if (control_orth[xy] < HIBERNATION_TICKS) {
                        control_orth[xy] = HIBERNATION_TICKS;
                    }
                }
                */
                compute_decay(
                    control_orth, control_diag,
                    control_orth_next, control_diag_next,
                    control_directive_0, control_directive_1,
                    control_directive_0_next, control_directive_1_next,
                    xy
                );
                
                /*
                // revert to control_directive_1
                if (control_orth_next[xy] < HIBERNATION_TICKS
                    && control_orth_next[xy] < control_orth[xy]
                    && control_directive_0_next[xy] != control_directive_1_next[xy]
                    && RAND_SECONDARY_TRANSITION
                ) {
                    control_directive_0_next[xy] = control_directive_1_next[xy];
                    control_orth_next[xy] = HIBERNATION_TICKS + SECONDARY_TRANSITION_TICKS;
                }
                
                // revert to hibernation
                if (control_orth_next[xy] == 0
                    && control_directive_0_next[xy] != PATTERN_BASE
                    && RAND_SECONDARY_TRANSITION
                ) {
                    control_directive_0_next[xy] = control_directive_1_next[xy] = PATTERN_BASE;
                    control_orth_next[xy] = SECONDARY_TRANSITION_TICKS;
                }
                */
                
                // evolve waves_(orth|diag)
                compute_decay(
                    waves_orth, waves_diag,
                    waves_orth_next, waves_diag_next,
                    scratch, scratch, scratch, scratch,
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
                    
                    if (pressure_self[xy] > 0) {
                        pressure_self[xy] -= 1;
                        pressure_orth_next[xy] = pressure_diag_next[xy] = PRESSURE_RADIUS_TICKS;
                    }
                    
                    compute_hanabi(hanabi, hanabi_next, xy);
                    if ((waves_orth_next[xy] / 17) % 480 < 12) {
                        hanabi_next[xy].orth = hanabi_next[xy].diag = 0;
                    }
                } else if (
                    rand() % PRESSURE_RADIUS_TICKS < pressure_orth[xy]
                    && rand() % PRESSURE_RADIUS_TICKS < pressure_orth[xy]
                ) {
                    // evolve rainbow_0
                    rainbow_0_next[xy] = compute_cyclic(rainbow_0, impatience_0, xy);
                }
            }
        }
        
        if (epoch % WILDFIRE_SPEEDUP == 0) {
            // drive waves_(orth|diag)'s top row
            waves_base_z_orig += 17;
            /*
            for (int x = 0; x < FLOOR_COLS; ++x) {
                waves_orth_next[x+COLS*PETAL_ROWS] = waves_diag_next[x+COLS*PETAL_ROWS] = waves_base[x+WAVES_BASE_X_ORIG] + waves_base_z_orig;
            }
            */
            waves_orth_next[COLS*(ROWS/2) + (epoch*2/3) % COLS] =
                waves_base_z_orig;
            
            pressure_self[COLS*BOUNCE_ROWS(epoch/3) + ((epoch/3+0) % COLS)] = PRESSURE_DELAY_EPOCHS;
            pressure_self[COLS*BOUNCE_ROWS(epoch/3) + ((epoch/3+256) % COLS)] = PRESSURE_DELAY_EPOCHS;
            pressure_self[COLS*BOUNCE_ROWS(epoch/3) + ((epoch/3+512) % COLS)] = PRESSURE_DELAY_EPOCHS;
            pressure_self[COLS*BOUNCE_ROWS(epoch/3) + ((epoch/3+128) % COLS)] = PRESSURE_DELAY_EPOCHS;
            pressure_self[COLS*BOUNCE_ROWS(epoch/3) + ((epoch/3+384) % COLS)] = PRESSURE_DELAY_EPOCHS;
            pressure_self[COLS*BOUNCE_ROWS(epoch/3) + ((epoch/3+640) % COLS)] = PRESSURE_DELAY_EPOCHS;
            
            pressure_self[COLS*(ROWS-BOUNCE_ROWS(epoch/3)) + ((2*COLS-epoch/3-128) % COLS)] = PRESSURE_DELAY_EPOCHS;
            pressure_self[COLS*(ROWS-BOUNCE_ROWS(epoch/3)) + ((2*COLS-epoch/3-128-256) % COLS)] = PRESSURE_DELAY_EPOCHS;
            pressure_self[COLS*(ROWS-BOUNCE_ROWS(epoch/3)) + ((2*COLS-epoch/3-128-512) % COLS)] = PRESSURE_DELAY_EPOCHS;
            pressure_self[COLS*(ROWS-BOUNCE_ROWS(epoch/3)) + ((2*COLS-epoch/3-128-128) % COLS)] = PRESSURE_DELAY_EPOCHS;
            pressure_self[COLS*(ROWS-BOUNCE_ROWS(epoch/3)) + ((2*COLS-epoch/3-128-384) % COLS)] = PRESSURE_DELAY_EPOCHS;
            pressure_self[COLS*(ROWS-BOUNCE_ROWS(epoch/3)) + ((2*COLS-epoch/3-128-640) % COLS)] = PRESSURE_DELAY_EPOCHS;
        }
        
        for (int xy = 0; xy < ROWS * COLS; ++xy) {
            /*
            int x = xy % COLS;
            int y = xy / COLS;
            if ((y > PETAL_ROWS && x < FLOOR_COLS) // CR rrheingans-yoo for ntarleton: this should instead be pressure_switch_depressed(xy)
                && rand() % (FLOOR_ROWS * FLOOR_COLS * 15) == 0 // CR rrheingans-yoo for ntarleton: remove me
            ) { 
                if (pressure_self[xy] < PRESSURE_DELAY_EPOCHS) {
                    run_hanabi_spark(hanabi_next, xy, hanabi_seed_color[xy]);
                }
                pressure_self[xy] = PRESSURE_DELAY_EPOCHS;
            }
            */
            
            if (rainbow_0_next[xy] != rainbow_0[xy]) {
                rainbow_tone[xy] = ((waves_orth_next[xy] / 17) / 120) % COLORS;
            }
        }

        gettimeofday(&computed, NULL);
        
        int zz;
        for (int xy = 0; xy < ROWS * COLS; ++xy) {
            int x = xy % COLS;
            int y = xy / COLS;
            if (epoch > INITIALIZATION_EPOCHS) {
                switch (control_directive_0_next[xy]) {
                
                case PATTERN_RAINBOW_SPOTLIGHTS_ON_GREY:
                    if (rainbow_1_next[xy] == -1) {
                        display_color(xy, rainbow_0_next[xy]);
                    } else {
                        display_color(xy, rainbow_1_next[xy] + MAKE_GREY);
                    }
                    break;
                
                case PATTERN_RAINBOW_SPOTLIGHTS_ON_TWO_TONES:
                    if (rainbow_1_next[xy] == -1) {
                        display_color(xy, rainbow_0_next[xy]);
                        break;
                    }
                    // fall through to TWO_TONES
                case TWO_TONES:
                case PATTERN_BASE:
                    if (0
                        || x + y < BEVEL_RADIUS-1
                        || (COLS-1-x + y < BEVEL_RADIUS-1)
                        || (x + ROWS-1-y < BEVEL_RADIUS-1)
                        || (COLS-1-x + ROWS-1-y < BEVEL_RADIUS-1)
                    ) {
                        display_color(xy, COLOR_CLEAR);
                        break;
                    }
                    
                    switch ((rainbow_0_next[xy] - rainbow_tone[xy] + COLORS) % COLORS) {
                    case -1 + COLORS:
                        display_color(xy, ((rainbow_0_next[xy] + 1) % COLORS) + MAKE_DARKER);
                        break;
                    case 0:
                    case 1:
                        display_color(xy, rainbow_0_next[xy]);
                        break;
                    case 2:
                        display_color(xy, ((rainbow_0_next[xy] - 1 + COLORS) % COLORS) + MAKE_DARKER);
                        break;
                    default:
                        display_color(xy, -1 + MAKE_GREY + MAKE_DARKER);
                    }
                    break;
                
                case PATTERN_FULL_RAINBOW:
                    display_color(xy, rainbow_0_next[xy]);
                    break;

                case PATTERN_HANABI:
                    zz = (waves_orth_next[xy] / 17) % 480;
                    zz = min(zz, COLORS-zz);
                    
                    display_color(xy,
                        max(6,
                            min(rainbow_1_next[xy],
                                COLORS - rainbow_1_next[xy]
                            ) + zz
                        ) + MAKE_GREY + MAKE_DARKER
                    );
                    
                    if (hanabi_next[xy].orth > 0) {
                        display_color(xy, hanabi_next[xy].color);
                    }

                    default:
                        display_color(xy, xy % COLORS);
                }
                /*
                if (pressure_self[xy] > 0) {
                    display_color(xy, 6);
                }
                */
                if (rand() % 270 < (epoch - 10244 - pressure_orth[xy]/2)) {
                    if (rand() % 30 == 0) {
                        rainbow_0_next[xy] = RAND_COLOR;
                    }
                    display_color(xy, -1 + MAKE_GREY + MAKE_DARKER);
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
            
            hanabi[xy].orth = hanabi_next[xy].orth;
            hanabi[xy].diag = hanabi_next[xy].diag;
            hanabi[xy].color = hanabi_next[xy].color;
        }
        
        gettimeofday(&drawn, NULL);
        
        if (epoch > INITIALIZATION_EPOCHS) {
            display_flush(epoch);
            
            gettimeofday(&refreshed, NULL);
            
            if (usec_time_elapsed(&start, &refreshed) < USABLE_USEC_PER_EPOCH) {
                timeout(USABLE_MSEC_PER_EPOCH - usec_time_elapsed(&start, &refreshed) / THOUSAND);
                mvprintw(DIAGNOSTIC_ROWS+1, 2*DIAGNOSTIC_COLS-57, "usable:%7.1f", USABLE_MSEC_PER_EPOCH);
                mvprintw(DIAGNOSTIC_ROWS+2, 2*DIAGNOSTIC_COLS-57, "used:  %7.1f", usec_time_elapsed(&start, &refreshed) / THOUSAND);
                mvprintw(DIAGNOSTIC_ROWS+2, 2*DIAGNOSTIC_COLS-37, "target:%7.1f", USABLE_MSEC_PER_EPOCH - usec_time_elapsed(&start, &refreshed) / THOUSAND);
                //in_chr = getch();
            }
            
            /*
            if (in_chr > 0 && in_chr < 256) {
                mvprintw(ROWS+0, 0, "input: %c", in_chr);
                // CR rrheingans-yoo: do something!
                int xy = COLS*(ROWS-1) + FLOOR_COLS/2;
                control_directive_0[xy] = PATTERN_FULL_RAINBOW;
                control_directive_1[xy] = TWO_TONES;
                control_orth[xy] = HIBERNATION_TICKS + TRANSITION_TICKS;
            }
            */

            
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
        mvprintw(DIAGNOSTIC_ROWS+0, 2*DIAGNOSTIC_COLS-15, "compute:%5.1fms", compute_avg / THOUSAND);
        mvprintw(DIAGNOSTIC_ROWS+1, 2*DIAGNOSTIC_COLS-15, "draw:   %5.1fms", draw_avg / THOUSAND);
        mvprintw(DIAGNOSTIC_ROWS+2, 2*DIAGNOSTIC_COLS-15, "refresh:%5.1fms", refresh_avg / THOUSAND);
        mvprintw(DIAGNOSTIC_ROWS+3, 2*DIAGNOSTIC_COLS-15, "wait:   %5.1fms", wait_avg / THOUSAND);
        mvprintw(DIAGNOSTIC_ROWS+4, 2*DIAGNOSTIC_COLS-15, "sleep:  %5.1fms", sleep_avg / THOUSAND);
        mvprintw(DIAGNOSTIC_ROWS+0, 2*DIAGNOSTIC_COLS-37, "epoch: %7d", epoch);
        mvprintw(DIAGNOSTIC_ROWS+1, 2*DIAGNOSTIC_COLS-37, "Hz:    %7.1f", 1 / (total_avg / MILLION));
        if (DIAGNOSTIC_SAMPLING_RATE != 1) {
            mvprintw(DIAGNOSTIC_ROWS+4, 2*DIAGNOSTIC_COLS-37, "downsampling: %d", DIAGNOSTIC_SAMPLING_RATE);
            mvprintw(DIAGNOSTIC_ROWS+3, 2*DIAGNOSTIC_COLS-37, "terminal_display_");
        }
        mvprintw(DIAGNOSTIC_ROWS+1, 1, "control_orth[0] = %7d", control_orth[0]);
        mvprintw(DIAGNOSTIC_ROWS+2, 1, "control_directive_0[0] = %2d", control_directive_0[0]);
        mvprintw(DIAGNOSTIC_ROWS+3, 1, "control_directive_1[0] = %2d", control_directive_1[0]);
        
        start = stop;
    }
    
    endwin();
    
    return 0;
}

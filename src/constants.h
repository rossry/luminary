#ifndef CONSTANTS_H
#define CONSTANTS_H

// for warning "_BSD_SOURCE and _SVID_SOURCE are deprecated, use _DEFAULT_SOURCE"
#define _DEFAULT_SOURCE 1

// this has to go here because I want to #define COLS, and that can't happen
// before I #include <ncurses.h>
#include <ncurses.h>

#define THOUSAND 1000
#define MILLION  1000000
#define RAND_DOUBLE ((double)rand() / (double)(RAND_MAX))

// input, output, control
//#define SACN_SERVER
#ifdef SACN_SERVER
    //#define SACN_TEST_CLIENT // use some keyboard actions to send test-client messages to the server
#endif /* SACN_SERVER */

//#define SACN_CLIENT

//#define PP_SERVER

//#define SPECTRARY

//#define UMBRARY

// physical dimensions
//  #define PETALS_ACTIVE

#define FLOOR_COLS 48
#define FLOOR_ROWS 48

#define FLOOR_COLS_SHOWN FLOOR_COLS
#define FLOOR_ROWS_SHOWN FLOOR_ROWS

#ifdef PETALS_ACTIVE
    #define PETAL_COLS 18 // per petal
    #define PETAL_ROWS 32
    #define PETAL_ROWS_CONNECTED 7
    #define PETAL_ROWS_SEPARATED (PETAL_ROWS - PETAL_ROWS_CONNECTED)
    
    #define COLS (5 * PETAL_COLS)
    #define ROWS (FLOOR_ROWS + PETAL_ROWS)
    
    #define PETAL_OF(xy) (((xy)%COLS) / PETAL_COLS)
    
    #define DIAGNOSTIC_SAMPLING_RATE 1
    #define DISPLAY_PETALS_MODE
    //#define DISPLAY_FLOOR_ALSO
#else /*PETALS_ACTIVE*/
    #define PETAL_COLS 32 // per petal
    #define PETAL_ROWS 0
    #define PETAL_ROWS_CONNECTED 0
    #define PETAL_ROWS_SEPARATED (PETAL_ROWS - PETAL_ROWS_CONNECTED)
    
    #define COLS FLOOR_COLS
    #define ROWS (FLOOR_ROWS + PETAL_ROWS)
    
    #define PETAL_OF(xy) 0
    
    #define DIAGNOSTIC_SAMPLING_RATE 1
#endif /*PETALS_ACTIVE*/


#ifdef DISPLAY_PETALS_MODE
    #ifdef DISPLAY_FLOOR_ALSO
        //#define DIAGNOSTIC_COLS_SUGGESTED (COLS / DIAGNOSTIC_SAMPLING_RATE + 12)
        #define DIAGNOSTIC_ROWS ((PETAL_ROWS + FLOOR_ROWS_SHOWN / 2) / DIAGNOSTIC_SAMPLING_RATE + 5)
    #else /* DISPLAY_FLOOR_ALSO */
        //#define DIAGNOSTIC_COLS_SUGGESTED (PETAL_COLS / DIAGNOSTIC_SAMPLING_RATE * 3 + 6)
        #define DIAGNOSTIC_ROWS ((PETAL_ROWS / DIAGNOSTIC_SAMPLING_RATE)*2 + 3)
    #endif /* DISPLAY_FLOOR_ALSO */
#else /* DISPLAY_PETALS_MODE */
    //#define DIAGNOSTIC_COLS_SUGGESTED (COLS / DIAGNOSTIC_SAMPLING_RATE)
    #define DIAGNOSTIC_ROWS (((FLOOR_ROWS_SHOWN-1) / DIAGNOSTIC_SAMPLING_RATE) + 1)
#endif /* DISPLAY_PETALS_MODE */

#define DIAGNOSTIC_COLS 72 //80

// colors (for ncurses)
#define RAINBOW_00  61
#define RAINBOW_01 133
#define RAINBOW_02 204
#define RAINBOW_03 203
#define RAINBOW_04 209
#define RAINBOW_05 179
#define RAINBOW_06 155
#define RAINBOW_07  83
#define RAINBOW_08  42
#define RAINBOW_09  43
#define RAINBOW_10  32
#define RAINBOW_11  62
#define RAINBOW_40  54
#define RAINBOW_41  53
#define RAINBOW_42  89
#define RAINBOW_43  95
#define RAINBOW_44  94
#define RAINBOW_45  58
#define RAINBOW_46  64
#define RAINBOW_47  28
#define RAINBOW_48  29
#define RAINBOW_49  23
#define RAINBOW_50  59
#define RAINBOW_51  60
#define GREY_0 242
#define GREY_1 243
#define GREY_2 244
#define GREY_3 245
#define GREY_4 246
#define GREY_5 247
#define GREY_6 248
#define GREY_40 232
#define GREY_41 235
#define GREY_42 248
#define GREY_43 241
#define GREY_44 244
#define GREY_45 247
#define GREY_46 250

// speeds, times, distances
#define BASE_HZ                    14
#define WILDFIRE_SPEEDUP           3// wildfire effects propagate at this multiple of BASE_HZ
#define DISPLAY_FLUSH_EPOCHS       1 // flush display every # epochs

//#define THROTTLE_LOOP
#ifdef THROTTLE_LOOP
    #define THROTTLE_LOOP_N 100
    #define THROTTLE_LOOP_USEC 350
#endif /* THROTTLE_LOOP*/

#define TRANSITION_TICKS           400
#define SECONDARY_TRANSITION_TICKS 300
#define RAND_SECONDARY_TRANSITION  ( rand() % (ROWS * COLS) == 0 )
#define HIBERNATION_TICKS          70000 // 70000 ticks ~ 103 seconds
#define INITIALIZATION_EPOCHS      ( 1 * WILDFIRE_SPEEDUP ) // run this many epochs on startup
#define PRESSURE_DELAY_EPOCHS      30
#define PRESSURE_RADIUS_TICKS      150//76
#define RAINBOW_TONE_EPOCHS        1200

// evolution parameters
// #define DECAY_SQUARE // make decay/waves effects square rather than round
#define TURING_DIFFUSION_PASSES    3
#define RA2T_I                     0.765 // 0.35

//#define OUTPUT_NCURSES

// gif output
//#define OUTPUT_GIF
#ifdef OUTPUT_GIF
    #define GIF_BLUR
    #define GIF_BLUR_WIDTH 4
    #define GIF_ZOOM 15
    #define GIF_EPOCHS 3100
#endif /* OUTPUT_GIF */

// cairo output
#define OUTPUT_CAIRO
#ifdef OUTPUT_CAIRO
    //#define OUTPUT_CAIRO_FULLSCREEN
    #define OUTPUT_CAIRO_VIDEO_FRAMES
    #ifdef OUTPUT_NCURSES
    #else /* OUTPUT_NCURSES */
        #define CAIRO_PRINT_VERBOSE
    #endif /* OUTPUT_NCURSES */
    #define CAIRO_SNAPSHOT_EPOCH 1323
    
    #define CAIRO_BLUR
    #define CAIRO_PAINT_ALPHA 0.1
    
    //#define CAIRO_CELL_LABELS
    #ifdef CAIRO_CELL_LABELS
        #define CAIRO_ZOOM 15
    #else /* CAIRO_CELL_LABELS */
        #define CAIRO_ZOOM 7
    #endif /* CAIRO_CELL_LABELS */
    
    #if CAIRO_ZOOM == 15
        #define CAIRO_BLUR_WIDTH 4
    #elif CAIRO_ZOOM == 7 /* CAIRO_ZOOM == ? */
        #define CAIRO_BLUR_WIDTH 2
    #elif CAIRO_ZOOM == 5 /* CAIRO_ZOOM == ? */
        #define CAIRO_BLUR_WIDTH 1
    #elif CAIRO_ZOOM == 3 /* CAIRO_ZOOM == ? */
        #define CAIRO_BLUR_WIDTH 1
    #else /* CAIRO_ZOOM == ? */
        #define CAIRO_BLUR_WIDTH 0
    #endif /* CAIRO_ZOOM == ? */
    
    #ifdef CAIRO_CELL_LABELS
        #undef CAIRO_BLUR_WIDTH
        #define CAIRO_BLUR_WIDTH 0
    #endif /* CAIRO_CELL_LABELS */
#endif /* OUTPUT_CAIRO */

// other constants (probably don't mess with these)
#define COLORS       12
#define RAND_COLOR   ( rand() % COLORS )
#define MAKE_GREY    20
#define MAKE_DARKER  40
#define EXTRA_COLOR  80
#define EXTRA_COLORS 36
#define BLACK        15

#define DECAYABLE_INCREMENT 17

// array is 97 elements long
#define WAVES_BASE_ARRAY  {-331,-319,-307,-295,-283,-271,-260,-249,-237,-226,-215,-205,-194,-184,-173,-163,-154,-144,-135,-125,-116,-108,-99,-91,-83,-75,-68,-61,-54,-47,-41,-35,-29,-24,-18,-14,-9,-5,-1,2,4,6,6,7,8,8,9,9,9,9,9,8,8,7,6,6,4,2,-1,-5,-9,-14,-18,-24,-29,-35,-41,-47,-54,-61,-68,-75,-83,-91,-99,-108,-116,-125,-135,-144,-154,-163,-173,-184,-194,-205,-215,-226,-237,-249,-260,-271,-283,-295,-307,-319,-331}
#define WAVES_BASE_X_ORIG ( 48 - FLOOR_COLS/2 )
#define WAVES_INCREMENT   DECAYABLE_INCREMENT

#define PETAL_PIXEL_PATTERN 3

#if PETAL_PIXEL_PATTERN == 1
    #define PETAL_MAPPING { \
             	         	         	         	         	         	         	 7, 8, 1,	         	 9, 8, 1,	         	         	         	         	         	         	         	\
             	         	         	         	         	         	         	         	         	         	         	         	         	         	         	         	         	\
             	         	         	         	         	         	 6, 10, 1,	         	         	         	10, 10, 1,	         	         	         	         	         	         	\
             	         	         	         	 4, 11, 1,	         	         	         	 8, 11, 1,	         	         	         	12, 11, 1,	         	         	         	         	\
             	         	         	         	         	         	         	         	         	         	         	         	         	         	         	         	         	\
             	         	         	         	 4, 13, 1,	         	         	         	 8, 13, 1,	         	         	         	12, 13, 1,	         	         	         	         	\
             	         	         	         	         	         	 6, 14, 1,	         	         	         	10, 14, 1,	         	         	         	         	         	         	\
             	         	         	 3, 15, 1,	         	         	         	         	         	         	         	         	         	13, 15, 1,	         	         	         	\
             	         	         	         	         	         	 6, 16, 1,	         	         	         	10, 16, 1,	         	         	         	         	         	         	\
             	         	         	         	 4, 17, 1,	         	         	         	 8, 17, 1,	         	         	         	12, 17, 1,	         	         	         	         	\
             	         	         	         	         	         	         	         	         	         	         	         	         	         	         	         	         	\
             	         	         	         	 4, 19, 1,	         	         	         	 8, 19, 1,	         	         	         	12, 19, 1,	         	         	         	         	\
             	         	         	         	         	         	 6, 20, 1,	         	         	         	10, 20, 1,	         	         	         	         	         	         	\
    }
    #define PETAL_MAPPING_PIXELS 24
#elif PETAL_PIXEL_PATTERN == 3
    #define PETAL_MAPPING { \
             	         	         	         	         	         	         	 7, 0, 1,	         	 9, 0, 1,	         	         	         	         	         	         	         	\
             	         	         	         	         	         	         	         	         	         	         	         	         	         	         	         	         	\
             	         	         	         	         	 5, 2, 1,	         	 7, 2, 1,	         	 9, 2, 1,	         	11, 2, 1,	         	         	         	         	         	\
             	         	         	         	         	         	         	         	         	         	         	         	         	         	         	         	         	\
             	         	         	         	 4, 4, 1,	         	 6, 4, 1,	         	         	         	10, 4, 1,	         	12, 4, 1,	         	         	         	         	\
             	         	 2, 5, 1,	         	         	         	         	         	 8, 5, 1,	         	         	         	         	         	14, 5, 1,	         	         	\
             	         	         	         	         	 5, 6, 1,	         	         	         	         	         	11, 6, 1,	         	         	         	         	         	\
             	 1, 7, 1,	         	 3, 7, 1,	         	         	         	 7, 7, 1,	         	 9, 7, 1,	         	         	         	13, 7, 1,	         	15, 7, 1,	         	\
             	         	         	         	         	         	         	         	         	         	         	         	         	         	         	         	         	\
             	 1, 9, 1,	         	 3, 9, 1,	         	         	         	 7, 9, 1,	         	 9, 9, 1,	         	         	         	13, 9, 1,	         	15, 9, 1,	         	\
             	         	         	         	         	 5,10, 1,	         	         	         	         	         	11,10, 1,	         	         	         	         	         	\
     0,11, 1,	         	 2,11, 1,	         	         	         	         	         	 8,11, 1,	         	         	         	         	         	14,11, 1,	         	16,11, 1,	\
             	         	         	         	 4,12, 1,	         	 6,12, 1,	         	         	         	10,12, 1,	         	12,12, 1,	         	         	         	         	\
             	 1,13, 1,	         	         	         	         	         	         	         	         	         	         	         	         	         	15,13, 1,	         	\
             	         	         	         	 4,14, 1,	         	 6,14, 1,	         	         	         	10,14, 1,	         	12,14, 1,	         	         	         	         	\
     0,15, 1,	         	 2,15, 1,	         	         	         	         	         	 8,15, 1,	         	         	         	         	         	14,15, 1,	         	16,15, 1,	\
             	         	         	         	         	 5,16, 1,	         	         	         	         	         	11,16, 1,	         	         	         	         	         	\
             	 1,17, 1,	         	 3,17, 1,	         	         	         	 7,17, 1,	         	 9,17, 1,	         	         	         	13,17, 1,	         	15,17, 1,	         	\
             	         	         	         	         	         	         	         	         	         	         	         	         	         	         	         	         	\
             	 1,19, 1,	         	 3,19, 1,	         	         	         	 7,19, 1,	         	 9,19, 1,	         	         	         	13,19, 1,	         	15,19, 1,	         	\
             	         	         	         	         	 5,20, 1,	         	         	         	         	         	11,20, 1,	         	         	         	         	         	\
             	         	 2,21, 1,	         	         	         	         	         	 8,21, 1,	         	         	         	         	         	14,21, 1,	         	         	\
             	         	         	         	 4,22, 1,	         	 6,22, 1,	         	         	         	10,22, 1,	         	12,22, 1,	         	         	         	         	\
    }
    #define PETAL_MAPPING_PIXELS 72
#elif PETAL_PIXEL_PATTERN == 10
    #define PETAL_MAPPING { \
             	         	         	         	         	         	         	 7, 0, 1,	 8, 0, 1,	 9, 0, 1,	         	         	         	         	         	         	         	\
             	         	         	         	         	         	 6, 1, 1,	         	         	         	10, 1, 1,	         	         	         	         	         	         	\
             	         	         	         	         	 5, 2, 1,	         	         	         	         	         	11, 2, 1,	         	         	         	         	         	\
             	         	         	         	 4, 3, 1,	         	         	         	         	         	         	         	12, 3, 1,	         	         	         	         	\
             	         	         	 3, 4, 1,	         	         	         	         	         	         	         	         	         	13, 4, 1,	         	         	         	\
             	         	 2, 5, 1,	         	         	         	         	         	 8, 5, 1,	         	         	         	         	         	14, 5, 1,	         	         	\
             	         	 2, 6, 1,	         	         	         	         	 7, 6, 1,	         	 9, 6, 1,	         	         	         	         	14, 6, 1,	         	         	\
             	 1, 7, 1,	         	         	         	         	 6, 7, 1,	         	         	         	10, 7, 1,	         	         	         	         	15, 7, 1,	         	\
             	 1, 8, 1,	         	         	         	 5, 8, 1,	         	         	         	         	         	11, 8, 1,	         	         	         	15, 8, 1,	         	\
             	 1, 9, 1,	         	         	         	 5, 9, 1,	         	         	         	         	         	11, 9, 1,	         	         	         	15, 9, 1,	         	\
     0, 10, 1,	         	         	         	 4, 10, 1,	         	         	         	         	         	         	         	12, 10, 1,	         	         	         	16, 10, 1,	\
     0, 11, 1,	         	         	         	 4, 11, 1,	         	         	         	         	         	         	         	12, 11, 1,	         	         	         	16, 11, 1,	\
     0, 12, 1,	         	         	         	 4, 12, 1,	         	         	         	         	         	         	         	12, 12, 1,	         	         	         	16, 12, 1,	\
     0, 13, 1,	         	         	         	 4, 13, 1,	         	         	         	         	         	         	         	12, 13, 1,	         	         	         	16, 13, 1,	\
     0, 14, 1,	         	         	         	 4, 14, 1,	         	         	         	         	         	         	         	12, 14, 1,	         	         	         	16, 14, 1,	\
     0, 15, 1,	         	         	         	 4, 15, 1,	         	         	         	         	         	         	         	12, 15, 1,	         	         	         	16, 15, 1,	\
             	 1, 16, 1,	         	         	 4, 16, 1,	         	         	         	         	         	         	         	12, 16, 1,	         	         	15, 16, 1,	         	\
             	 1, 17, 1,	         	         	         	 5, 17, 1,	         	         	         	         	         	11, 17, 1,	         	         	         	15, 17, 1,	         	\
             	 1, 18, 1,	         	         	         	 5, 18, 1,	         	         	         	         	         	11, 18, 1,	         	         	         	15, 18, 1,	         	\
             	         	 2, 19, 1,	         	         	         	 6, 19, 1,	         	         	         	10, 19, 1,	         	         	         	14, 19, 1,	         	         	\
             	         	 2, 20, 1,	         	         	         	         	 7, 20, 1,	         	 9, 20, 1,	         	         	         	         	14, 20, 1,	         	         	\
             	         	         	 3, 21, 1,	         	         	         	         	 8, 21, 1,	         	         	         	         	13, 21, 1,	         	         	         	\
             	         	         	         	 4, 22, 1,	         	         	         	         	         	         	         	12, 22, 1,	         	         	         	         	\
    }
    #define PETAL_MAPPING_PIXELS 79
#elif PETAL_PIXEL_PATTERN == 11
    #define PETAL_MAPPING { \
             	         	         	         	         	         	         	 7, 0, 1,	 8, 0, 1,	 9, 0, 1,	         	         	         	         	         	         	         	\
             	         	         	         	         	         	 6, 1, 1,	         	         	         	10, 1, 1,	         	         	         	         	         	         	\
             	         	         	         	         	 5, 2, 1,	         	         	         	         	         	11, 2, 1,	         	         	         	         	         	\
             	         	         	         	 4, 3, 1,	 5, 3, 1,	         	         	         	         	         	11, 3, 1,	12, 3, 1,	         	         	         	         	\
             	         	         	 3, 4, 1,	         	 5, 4, 1,	         	         	         	         	         	11, 4, 1,	         	13, 4, 1,	         	         	         	\
             	         	 2, 5, 1,	         	         	         	 6, 5, 1,	         	         	         	10, 5, 1,	         	         	         	14, 5, 1,	         	         	\
             	         	 2, 6, 1,	         	         	         	 6, 6, 1,	         	         	         	10, 6, 1,	         	         	         	14, 6, 1,	         	         	\
             	 1, 7, 1,	         	         	         	         	 6, 7, 1,	         	         	         	10, 7, 1,	         	         	         	         	15, 7, 1,	         	\
             	 1, 8, 1,	         	         	         	         	         	 7, 8, 1,	         	 9, 8, 1,	         	         	         	         	         	15, 8, 1,	         	\
             	 1, 9, 1,	         	         	         	         	         	 7, 9, 1,	         	 9, 9, 1,	         	         	         	         	         	15, 9, 1,	         	\
     0, 10, 1,	         	         	         	         	         	         	 7, 10, 1,	         	 9, 10, 1,	         	         	         	         	         	         	16, 10, 1,	\
     0, 11, 1,	         	         	         	         	         	         	         	 8, 11, 1,	         	         	         	         	         	         	         	16, 11, 1,	\
     0, 12, 1,	         	         	         	         	         	         	         	 8, 12, 1,	         	         	         	         	         	         	         	16, 12, 1,	\
     0, 13, 1,	         	         	         	         	         	         	         	 8, 13, 1,	         	         	         	         	         	         	         	16, 13, 1,	\
     0, 14, 1,	         	         	         	         	         	         	 7, 14, 1,	         	 9, 14, 1,	         	         	         	         	         	         	16, 14, 1,	\
     0, 15, 1,	         	         	         	         	         	         	 7, 15, 1,	         	 9, 15, 1,	         	         	         	         	         	         	16, 15, 1,	\
             	 1, 16, 1,	         	         	         	         	         	 7, 16, 1,	         	 9, 16, 1,	         	         	         	         	         	15, 16, 1,	         	\
             	 1, 17, 1,	         	         	         	         	 6, 17, 1,	         	         	         	10, 17, 1,	         	         	         	         	15, 17, 1,	         	\
             	 1, 18, 1,	         	         	         	         	 6, 18, 1,	         	         	         	10, 18, 1,	         	         	         	         	15, 18, 1,	         	\
             	         	 2, 19, 1,	         	         	         	 6, 19, 1,	         	         	         	10, 19, 1,	         	         	         	14, 19, 1,	         	         	\
             	         	 2, 20, 1,	         	         	 5, 20, 1,	         	         	         	         	         	11, 20, 1,	         	         	14, 20, 1,	         	         	\
             	         	         	 3, 21, 1,	         	 5, 21, 1,	         	         	         	         	         	11, 21, 1,	         	13, 21, 1,	         	         	         	\
             	         	         	         	 4, 22, 1,	         	         	         	         	         	         	         	12, 22, 1,	         	         	         	         	\
    }
    #define PETAL_MAPPING_PIXELS 82
#elif PETAL_PIXEL_PATTERN == 21
    #define PETAL_MAPPING { \
             	         	         	         	         	         	         	         	         	         	         	13, 0, 1,	14, 0, 1,	15, 0, 1,	16, 0, 1,	17, 0, 1,	         	         	         	         	         	         	         	         	         	         	         	\
             	         	         	         	         	         	         	         	10, 1, 1,	11, 1, 1,	12, 1, 1,	         	         	         	         	         	18, 1, 1,	19, 1, 1,	20, 1, 1,	         	         	         	         	         	         	         	         	\
             	         	         	         	         	         	 8, 2, 1,	 9, 2, 1,	         	         	         	         	         	         	         	         	         	         	         	21, 2, 1,	22, 2, 1,	         	         	         	         	         	         	\
             	         	         	         	         	 7, 3, 1,	         	         	         	         	         	         	         	         	         	         	         	         	         	         	         	23, 3, 1,	         	         	         	         	         	\
             	         	         	         	 6, 4, 1,	         	         	         	         	         	         	         	         	         	         	         	         	         	         	         	         	         	24, 4, 1,	         	         	         	         	\
             	         	         	 5, 5, 1,	         	 7, 5, 1,	         	         	         	         	         	         	         	         	         	         	         	         	         	         	         	23, 5, 1,	         	25, 5, 1,	         	         	         	\
             	         	 4, 6, 1,	         	         	         	 8, 6, 1,	         	         	         	         	         	         	         	         	         	         	         	         	         	22, 6, 1,	         	         	         	26, 6, 1,	         	         	\
             	         	 4, 7, 1,	         	         	         	         	 9, 7, 1,	         	         	         	         	         	         	         	         	         	         	         	21, 7, 1,	         	         	         	         	26, 7, 1,	         	         	\
             	 3, 8, 1,	         	         	         	         	         	         	10, 8, 1,	         	         	         	         	         	         	         	         	         	20, 8, 1,	         	         	         	         	         	         	27, 8, 1,	         	\
             	 3, 9, 1,	         	         	         	         	         	         	         	11, 9, 1,	         	         	         	         	         	         	         	19, 9, 1,	         	         	         	         	         	         	         	27, 9, 1,	         	\
             	 3, 10, 1,	         	         	         	         	         	         	         	         	12, 10, 1,	         	         	         	         	         	18, 10, 1,	         	         	         	         	         	         	         	         	27, 10, 1,	         	\
     2, 11, 1,	         	         	         	         	         	         	         	         	         	         	13, 11, 1,	         	         	         	17, 11, 1,	         	         	         	         	         	         	         	         	         	         	28, 11, 1,	\
     2, 12, 1,	         	         	         	         	         	         	         	         	         	         	         	14, 12, 1,	         	16, 12, 1,	         	         	         	         	         	         	         	         	         	         	         	28, 12, 1,	\
     2, 13, 1,	         	         	         	         	         	         	         	         	         	         	         	         	15, 13, 1,	         	         	         	         	         	         	         	         	         	         	         	         	28, 13, 1,	\
     2, 14, 1,	         	         	         	         	         	         	         	         	         	         	         	14, 14, 1,	         	16, 14, 1,	         	         	         	         	         	         	         	         	         	         	         	28, 14, 1,	\
     2, 15, 1,	         	         	         	         	         	         	         	         	         	         	13, 15, 1,	         	         	         	17, 15, 1,	         	         	         	         	         	         	         	         	         	         	28, 15, 1,	\
             	 3, 16, 1,	         	         	         	         	         	         	         	         	12, 16, 1,	         	         	         	         	         	18, 16, 1,	         	         	         	         	         	         	         	         	27, 16, 1,	         	\
             	 3, 17, 1,	         	         	         	         	         	         	         	11, 17, 1,	         	         	         	         	         	         	         	19, 17, 1,	         	         	         	         	         	         	         	27, 17, 1,	         	\
             	 3, 18, 1,	         	         	         	         	         	         	10, 18, 1,	         	         	         	         	         	         	         	         	         	20, 18, 1,	         	         	         	         	         	         	27, 18, 1,	         	\
             	         	 4, 19, 1,	         	         	         	         	 9, 19, 1,	         	         	         	         	         	         	         	         	         	         	         	21, 19, 1,	         	         	         	         	26, 19, 1,	         	         	\
             	         	 4, 20, 1,	         	         	         	 8, 20, 1,	         	         	         	         	         	         	         	         	         	         	         	         	         	22, 20, 1,	         	         	         	26, 20, 1,	         	         	\
             	         	         	 5, 21, 1,	         	 7, 21, 1,	         	         	         	         	         	         	         	         	         	         	         	         	         	         	         	23, 21, 1,	         	25, 21, 1,	         	         	         	\
             	         	         	         	 6, 22, 1,	         	         	         	         	         	         	         	         	         	         	         	         	         	         	         	         	         	24, 22, 1,	         	         	         	         	\
    }
    #define PETAL_MAPPING_PIXELS 88
#else /* PETAL_PIXEL_PATTERN == ? */
    #define PETAL_MAPPING {}
    #define PETAL_MAPPING_PIXELS 0
#endif /* PETAL_PIXEL_PATTERN == ? */

// derived constants
#define USEC_PER_EPOCH        ( MILLION / BASE_HZ / WILDFIRE_SPEEDUP )
// When blocking for input, aim to block until USABLE_USEC_PER_EPOCH usec have
// passed this epoch. You'll miss, which is why this is < USEC_PER_EPOCH.
//
// Take up the ratio if you don't have enough "wait" time in the diagnostic, 
// and can tolerate more stutter.
#define USABLE_USEC_PER_EPOCH ( 0.6 * USEC_PER_EPOCH )
#define USABLE_MSEC_PER_EPOCH ( USABLE_USEC_PER_EPOCH / THOUSAND )

// pattern names
#define PATTERN_ERR            0
#define PATTERN_BASE           1
#define PATTERN_RAINBOW_SPOTLIGHTS_ON_GREY      2
#define PATTERN_RAINBOW_SPOTLIGHTS_ON_TWO_TONES 3
#define PATTERN_TWO_TONES      4
#define PATTERN_OPPOSED_TONES  5
#define PATTERN_TRIAD_TONES    6
#define PATTERN_UNUSED         7
#define PATTERN_HANABI         8
#define PATTERN_Q2             9
#define PATTERN_FULL_RAINBOW  10
#define PATTERN_SOLID         20
#define PATTERN_N_TONES       30
#define PATTERN_RAND_N_TONES (PATTERN_N_TONES+2+(rand()%3))
#define AGGRESSIVE_REVERSION 100

#define PATTERN_SACN_COLOR         2048 // range from here to 13x here
#define PATTERN_SACN_TEXTURE        256
#define PATTERN_SACN_INTENSITY        1
#define PATTERN_SACN_INTENSE        255

#define PATTERN_SACN(color,texture,intensity) \
    ((1+color)*PATTERN_SACN_COLOR \
        + texture*PATTERN_SACN_TEXTURE \
        + intensity*PATTERN_SACN_INTENSITY \
    )

#define PATTERN_IS_SACN(pattern)            ((pattern) >= PATTERN_SACN_COLOR)
#define PATTERN_SACN_GET_COLOR(pattern)     ((pattern)/PATTERN_SACN_COLOR - 1)
#define PATTERN_SACN_GET_TEXTURE(pattern)   (((pattern)%PATTERN_SACN_COLOR) / PATTERN_SACN_TEXTURE)
#define PATTERN_SACN_GET_INTENSITY(pattern) ((pattern) % PATTERN_SACN_TEXTURE)

#define SCENE_BASE 0
#define SCENE_NO_HIBERNATION 1
#define SCENE_CIRCLING_RAINBOWS 10
#define SCENE_Q2 50

#define MENU_ACTIONS 1000
#define MENU_SCENES  2000

#define max(a,b) \
    ({ __typeof__ (a) _a = (a); \
        __typeof__ (b) _b = (b); \
        _a > _b ? _a : _b; })
#define min(a,b) \
    ({ __typeof__ (a) _a = (a); \
        __typeof__ (b) _b = (b); \
        _a < _b ? _a : _b; })

#endif /* CONSTANTS_H */

#ifndef CONSTANTS_H
#define CONSTANTS_H

// this has to go here because I want to #define COLS, and that can't happen
// before I #include <ncurses.h>
#include <ncurses.h>

#define THOUSAND 1000
#define MILLION  1000000

// physical dimensions
#define PETALS_ACTIVE

#define FLOOR_COLS 85
#define FLOOR_ROWS 43

#ifdef PETALS_ACTIVE
    #define PETAL_COLS 17 // per petal
    #define PETAL_ROWS 23
    #define PETAL_ROWS_CONNECTED 6
    #define PETAL_ROWS_SEPARATED (PETAL_ROWS - PETAL_ROWS_CONNECTED)
    
    #define COLS (5 * PETAL_COLS)
    #define ROWS (FLOOR_ROWS + PETAL_ROWS)
    
    #define DIAGNOSTIC_SAMPLING_RATE 1
    #define DISPLAY_PETALS_MODE
    #define DISPLAY_FLOOR_ALSO
#else /*PETALS_ACTIVE*/
    #define PETAL_COLS 32 // per petal
    #define PETAL_ROWS 0
    #define PETAL_ROWS_CONNECTED 0
    #define PETAL_ROWS_SEPARATED (PETAL_ROWS - PETAL_ROWS_CONNECTED)
    
    #define COLS FLOOR_COLS
    #define ROWS (FLOOR_ROWS + PETAL_ROWS)
    
    #define DIAGNOSTIC_SAMPLING_RATE 1
#endif /*PETALS_ACTIVE*/


#ifdef DISPLAY_PETALS_MODE
    #define DIAGNOSTIC_COLS (COLS / DIAGNOSTIC_SAMPLING_RATE + 12)
    #ifdef DISPLAY_FLOOR_ALSO
        #define DIAGNOSTIC_ROWS ((PETAL_ROWS + FLOOR_ROWS / 2) / DIAGNOSTIC_SAMPLING_RATE + 5)
    #else /* DISPLAY_FLOOR_ALSO */
        #define DIAGNOSTIC_ROWS (PETAL_ROWS / DIAGNOSTIC_SAMPLING_RATE)
    #endif /* DISPLAY_FLOOR_ALSO */
#else /* DISPLAY_PETALS_MODE */
    #define DIAGNOSTIC_COLS (COLS / DIAGNOSTIC_SAMPLING_RATE)
    #define DIAGNOSTIC_ROWS (ROWS / DIAGNOSTIC_SAMPLING_RATE)
#endif /* DISPLAY_PETALS_MODE */

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
#define BASE_HZ                    10
#define WILDFIRE_SPEEDUP           4 // wildfire effects propagate at this multiple of BASE_HZ
#define TRANSITION_TICKS           400
#define SECONDARY_TRANSITION_TICKS 300
#define RAND_SECONDARY_TRANSITION  ( rand() % (ROWS * COLS) == 0 )
#define HIBERNATION_TICKS          70000 // 70000 ticks ~ 103 seconds
#define INITIALIZATION_EPOCHS      ( 200 * WILDFIRE_SPEEDUP ) // run this many epochs on startup
#define PRESSURE_DELAY_EPOCHS      30
#define PRESSURE_RADIUS_TICKS      150//76

// gif output
//#define OUTPUT_GIF
#define GIF_BLUR
#define GIF_BLUR_WIDTH 4
#define GIF_ZOOM 15
#define GIF_EPOCHS 1200 * WILDFIRE_SPEEDUP

// cairo output
//#define OUTPUT_CAIRO
//#define OUTPUT_CAIRO_FULLSCREEN
#define CAIRO_BLUR
#define CAIRO_BLUR
#define CAIRO_BLUR_WIDTH 4
#define CAIRO_ZOOM 15
#define CAIRO_SNAPSHOT_EPOCH 850

// other constants (probably don't mess with these)
#define COLORS      12
#define RAND_COLOR  ( rand() % COLORS )
#define MAKE_GREY   20
#define MAKE_DARKER 40

#define WAVES_BASE_ARRAY  {-331,-319,-307,-295,-283,-271,-260,-249,-237,-226,-215,-205,-194,-184,-173,-163,-154,-144,-135,-125,-116,-108,-99,-91,-83,-75,-68,-61,-54,-47,-41,-35,-29,-24,-18,-14,-9,-5,-1,2,4,6,6,7,8,8,9,9,9,9,9,8,8,7,6,6,4,2,-1,-5,-9,-14,-18,-24,-29,-35,-41,-47,-54,-61,-68,-75,-83,-91,-99,-108,-116,-125,-135,-144,-154,-163,-173,-184,-194,-205,-215,-226,-237,-249,-260,-271,-283,-295,-307,-319,-331}
#define WAVES_BASE_X_ORIG 16

#define PETAL_MAPPING { \
          	      	      	      	      	      	      	 7, 0,	      	 9, 0,	      	      	      	      	      	      	      	\
          	      	      	      	      	      	      	      	      	      	      	      	      	      	      	      	      	\
          	      	      	      	      	 5, 2,	      	 7, 2,	      	 9, 2,	      	11, 2,	      	      	      	      	      	\
          	      	      	      	      	      	      	      	      	      	      	      	      	      	      	      	      	\
          	      	      	      	 4, 4,	      	 6, 4,	      	      	      	10, 4,	      	12, 4,	      	      	      	      	\
          	      	 2, 5,	      	      	      	      	      	 8, 5,	      	      	      	      	      	14, 5,	      	      	\
          	      	      	      	      	 5, 6,	      	      	      	      	      	11, 6,	      	      	      	      	      	\
          	 1, 7,	      	 3, 7,	      	      	      	 7, 7,	      	 9, 7,	      	      	      	13, 7,	      	15, 7,	      	\
          	      	      	      	      	      	      	      	      	      	      	      	      	      	      	      	      	\
          	 1, 9,	      	 3, 9,	      	      	      	 7, 9,	      	 9, 9,	      	      	      	13, 9,	      	15, 9,	      	\
          	      	      	      	      	 5,10,	      	      	      	      	      	11,10,	      	      	      	      	      	\
     0,11,	      	 2,11,	      	      	      	      	      	 8,11,	      	      	      	      	      	14,11,	      	16,11,	\
          	      	      	      	 4,12,	      	 6,12,	      	      	      	10,12,	      	12,12,	      	      	      	      	\
          	 1,13,	      	      	      	      	      	      	      	      	      	      	      	      	      	15,13,	      	\
          	      	      	      	 4,14,	      	 6,14,	      	      	      	10,14,	      	12,14,	      	      	      	      	\
     0,15,	      	 2,15,	      	      	      	      	      	 8,15,	      	      	      	      	      	14,15,	      	16,15,	\
          	      	      	      	      	 5,16,	      	      	      	      	      	11,16,	      	      	      	      	      	\
          	 1,17,	      	 3,17,	      	      	      	 7,17,	      	 9,17,	      	      	      	13,17,	      	15,17,	      	\
          	      	      	      	      	      	      	      	      	      	      	      	      	      	      	      	      	\
          	 1,19,	      	 3,19,	      	      	      	 7,19,	      	 9,19,	      	      	      	13,19,	      	15,19,	      	\
          	      	      	      	      	 5,20,	      	      	      	      	      	11,20,	      	      	      	      	      	\
          	      	 2,21,	      	      	      	      	      	 8,21,	      	      	      	      	      	14,21,	      	      	\
          	      	      	      	 4,22,	      	 6,22,	      	      	      	10,22,	      	12,22,	      	      	      	      	\
}
#define PETAL_MAPPING_PIXELS 72

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
#define PATTERN_BASE 0
#define PATTERN_RAINBOW_SPOTLIGHTS_ON_GREY 1
#define PATTERN_RAINBOW_SPOTLIGHTS_ON_TWO_TONES 2
#define TWO_TONES 3
#define PATTERN_HANABI 4
#define PATTERN_FULL_RAINBOW 10

#define max(a,b) \
    ({ __typeof__ (a) _a = (a); \
        __typeof__ (b) _b = (b); \
        _a > _b ? _a : _b; })
#define min(a,b) \
    ({ __typeof__ (a) _a = (a); \
        __typeof__ (b) _b = (b); \
        _a < _b ? _a : _b; })

#endif /* CONSTANTS_H */

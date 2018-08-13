#include "pattern.h"

#include "constants.h"

int color_from_pattern(int control_directive, int xy, int tone, int val_a, int val_b) {
    int pattern;
    int texture;
    int height;
    int color_offset;
    
    if (PATTERN_IS_SACN(control_directive)) {
        texture = PATTERN_SACN_GET_TEXTURE(control_directive);
        switch(texture) {
        case 0:
            pattern = PATTERN_SOLID;
            break;
        case 1: case 2: case 3: case 4:
            pattern = PATTERN_N_TONES + texture;
            break;
        case 5:
            pattern = PATTERN_OPPOSED_TONES;
            break;
        case 6:
            pattern = PATTERN_TRIAD_TONES;
            break;
        case 7:
            pattern = PATTERN_Q2;
            break;
        default:
            pattern = PATTERN_ERR;
        }
    } else {
        pattern = control_directive % AGGRESSIVE_REVERSION;
    }
    
    switch (pattern) {
    
    case PATTERN_SOLID:
        return (tone+1)%COLORS;
        break;
    
    case PATTERN_FULL_RAINBOW:
        return val_a;
        break;
    
    case PATTERN_RAINBOW_SPOTLIGHTS_ON_GREY:
        if (val_b == -1) {
            return val_a;
        } else {
            return val_b + MAKE_GREY;
        }
        break;
    
    case PATTERN_RAINBOW_SPOTLIGHTS_ON_TWO_TONES:
        if (val_b == -1) {
            return val_a;
            break;
        }
        // fall through to TWO_TONES
    case PATTERN_TWO_TONES:
        switch ((val_a - tone + COLORS) % COLORS) {
        case -1 + COLORS:
            return tone + MAKE_DARKER;
            break;
        case 0:
        case 1:
            return val_a;
            break;
        case 2:
            return ((val_a - 1 + COLORS) % COLORS) + MAKE_DARKER;
            break;
        default:
            return -1 + MAKE_GREY + MAKE_DARKER;
        }
        break;
    
    case PATTERN_N_TONES+1: case PATTERN_N_TONES+2: case PATTERN_N_TONES+3: case PATTERN_N_TONES+4:
        height = color_offset = (val_a - tone + COLORS) % COLORS;
        
        switch (pattern-PATTERN_N_TONES) {
        case 1:
            if (height > 1) { color_offset -= 1; }
        case 2:
            if (height > 2) { color_offset -= 2; } else if (height > 0) { color_offset -= 1; }
            break;
        case 3:
            if (height > 1) { color_offset -= 1; }
            break;
        // default: pass
        }
        
        switch (height) {
        case -1 + COLORS:
            return tone + MAKE_DARKER;
            break;
        case 0: case 1: case 2: case 3:
            return (tone + color_offset) % COLORS;
            break;
        case 4:
            return ((tone + color_offset - 1) % COLORS) + MAKE_DARKER;
            break;
        default:
            return -1 + MAKE_GREY + MAKE_DARKER;
        }
        break;
    
    case PATTERN_OPPOSED_TONES:
        switch ((val_a - tone + COLORS) % COLORS) {
        case -1 + COLORS:
            return tone + MAKE_DARKER;
            break;
        case 0:
            return tone;
            break;
        case 1:
            return (tone+1)%COLORS;
            break;
        case 5:
            return (tone+6)%COLORS + MAKE_DARKER;
            break;
        case 6:
            return (tone+6)%COLORS;
            break;
        case 7:
            return (tone+7)%COLORS;
            break;
        default:
            return -1 + MAKE_GREY + MAKE_DARKER;
        }
        break;
    
    case PATTERN_TRIAD_TONES:
        switch ((val_a - tone + COLORS) % COLORS) {
        case -1 + COLORS:
            return tone + MAKE_DARKER;
            break;
        case 0:
            return tone;
            break;
        case 1:
            return tone + MAKE_DARKER;
            break;
        case 3:
            return (tone+4)%COLORS + MAKE_DARKER;
            break;
        case 4:
            return (tone+4)%COLORS;
            break;
        case 5:
            return (tone+4)%COLORS + MAKE_DARKER;
            break;
        case 7:
            return (tone+8)%COLORS + MAKE_DARKER;
            break;
        case 8:
            return (tone+8)%COLORS;
            break;
        case 9:
            return (tone+8)%COLORS + MAKE_DARKER;
            break;
        default:
            return -1 + MAKE_GREY + MAKE_DARKER;
        }
        break;
        
    case PATTERN_BASE:
    case PATTERN_N_TONES:
        switch ((val_a - tone + COLORS) % COLORS) {
        case -1 + COLORS:
        case 0:
            return tone + MAKE_DARKER;
            break;
        default:
            return -1 + MAKE_GREY + MAKE_DARKER;
        }
        break;
        
    case PATTERN_Q2:
        if (val_b < 4) {
            return val_a;
        } else if (val_b < 6 || val_b > 9) {
            return val_a + MAKE_DARKER;
        } else {
            return -1 + MAKE_GREY + MAKE_DARKER;
        }
        break;
    
    /*
    case PATTERN_HANABI:
        height = (waves_orth_next[xy] / 17) % 480;
        height = min(height, COLORS-height);
        
        return
            max(6,
                min(val_b,
                    COLORS - val_b
                ) + height
            ) + MAKE_GREY + MAKE_DARKER
        ;
        
        if (hanabi_next[xy].orth > 0) {
            return hanabi_next[xy].color;
        }
    */
        
    case PATTERN_ERR:
    default:
        return xy % COLORS;
    }
    
    return xy % COLORS;
}
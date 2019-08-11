#include "constants.h"

#include <stdlib.h>
#include <unistd.h>
#include <math.h>
#include <assert.h>

#include "cellular.h"

#ifdef CAIRO_PAINT_BETWEEN_TURING_DIFFUSION_PASSES
    #include "display.h"
#endif /* CAIRO_PAINT_BETWEEN_TURING_DIFFUSION_PASSES */

// shared neighbors logic

int y_zero[] = {0, -1, -1+COLS, 0, 0, COLS, 0, 1, 1+COLS};
int y_wrap_x_zero[] = {-1, -1+COLS, -1+2*COLS, -COLS, 0, COLS, 1-COLS, 1, 1+COLS};
int y_wrap_x_cols_minus_one[] = {-1-COLS, -1, -1+COLS, -COLS, 0, COLS, 1-2*COLS, 1-COLS, 1};
int y_rows_minus_one[] = {-1-COLS, -1, 0, -COLS, 0, 0, 1-COLS, 1, 0};
int y_else[] = {-1-COLS, -1, -1+COLS, -COLS, 0, COLS, 1-COLS, 1, 1+COLS};

int y_upper_left[] = {0, PETAL_COLS-1, PETAL_COLS-2, 0, 0, 1, 0, COLS, COLS+1};
int y_upper_right[] = {2-PETAL_COLS, 1-PETAL_COLS, 0, -1, 0, 0, COLS-1, COLS, 0};

int y_upper_join_defined = 0;
int y_upper_join[PETAL_COLS*9];

int* get_offset_array(int x, int y) {
    if (!y_upper_join_defined) {
        int ii;

        ii = 0;
        y_upper_join[ii*9 + 0] = 0;
        y_upper_join[ii*9 + 1] = 0;
        y_upper_join[ii*9 + 2] = 0;
        y_upper_join[ii*9 + 3] = PETAL_COLS-1;
        y_upper_join[ii*9 + 4] = 0;
        y_upper_join[ii*9 + 5] = COLS;
        y_upper_join[ii*9 + 6] = PETAL_COLS-2;
        y_upper_join[ii*9 + 7] = 1;
        y_upper_join[ii*9 + 8] = 1+COLS;

        for (int ii = 1; ii < PETAL_COLS; ++ii) {
            y_upper_join[ii*9 + 0] = PETAL_COLS+2-ii*2;
            y_upper_join[ii*9 + 1] = -1;
            y_upper_join[ii*9 + 2] = -1+COLS;
            y_upper_join[ii*9 + 3] = PETAL_COLS+1-ii*2;
            y_upper_join[ii*9 + 4] = 0;
            y_upper_join[ii*9 + 5] = COLS;
            y_upper_join[ii*9 + 6] = PETAL_COLS-ii*2;
            y_upper_join[ii*9 + 7] = 1;
            y_upper_join[ii*9 + 8] = 1+COLS;
        }

        ii = PETAL_COLS-1;
        y_upper_join[ii*9 + 0] = 2-PETAL_COLS;
        y_upper_join[ii*9 + 1] = -1;
        y_upper_join[ii*9 + 2] = -1+COLS;
        y_upper_join[ii*9 + 3] = 1-PETAL_COLS;
        y_upper_join[ii*9 + 4] = 0;
        y_upper_join[ii*9 + 5] = COLS;
        y_upper_join[ii*9 + 6] = 0;
        y_upper_join[ii*9 + 7] = 0;
        y_upper_join[ii*9 + 8] = 0;

        y_upper_join_defined = 1;
    }

    switch (y) {
    case 0 : 
        #ifdef PETALS_ACTIVE
            // CR rrheingans-yoo: use y_upper_join
            switch (x % PETAL_COLS) {
            case 0 :
                return y_upper_left;
            case PETAL_COLS-1 :
                return y_upper_right;
            }
        #endif /* PETALS_ACTIVE */
        return y_zero;
    case ROWS-1 : 
        return y_rows_minus_one;
    default :
        if (y < PETAL_ROWS && y > PETAL_ROWS_SEPARATED) {
            if (x == 0) {
                return y_wrap_x_zero;
            } else if (x == COLS - 1) {
                return y_wrap_x_cols_minus_one;
            }
        } else if (y == PETAL_ROWS -1 && x > FLOOR_COLS) {
            return y_rows_minus_one;
        }
        return y_else;
    }
}

#define X_INIT(x,y) \
    (((y) < PETAL_ROWS && (y) > PETAL_ROWS_SEPARATED) \
        || ((x) > 0 && ((y) > PETAL_ROWS_SEPARATED || (x) % PETAL_COLS > 0)) \
        ? 0 : \
    3)
#define X_CONTINUE(x,y,i) \
    ((i) < (\
        (((y) < PETAL_ROWS && (y) > PETAL_ROWS_SEPARATED) \
            || ((x) < COLS-1 && ((y) > PETAL_ROWS_SEPARATED || (x) % PETAL_COLS < PETAL_COLS-1))) ? 9 : \
        6))

// cross-CA conversions

void extra_color_to_turing(int xy, int c, turing_vector_t* turing_u, turing_vector_t* turing_v) {
    switch(c) {
    case  0:
        turing_u[xy].state =  0.5;
        turing_v[xy].state = -0.866025;
        break;
    case  1:
        turing_u[xy].state =  0.342020;
        turing_v[xy].state = -0.939693;
        break;
    case  2:
        turing_u[xy].state =  0.173648;
        turing_v[xy].state = -0.984808;
        break;
    case  3:
        turing_u[xy].state =  0.0;
        turing_v[xy].state = -1.0;
        break;
    case  4:
        turing_u[xy].state = -0.173648;
        turing_v[xy].state = -0.984808;
        break;
    case  5:
        turing_u[xy].state = -0.342020;
        turing_v[xy].state = -0.939693;
        break;
    case  6:
        turing_u[xy].state = -0.5;
        turing_v[xy].state = -0.866025;
        break;
    case  7:
        turing_u[xy].state = -0.642788;
        turing_v[xy].state = -0.766044;
        break;
    case  8:
        turing_u[xy].state = -0.766044;
        turing_v[xy].state = -0.642788;
        break;
    case  9:
        turing_u[xy].state = -0.866025;
        turing_v[xy].state = -0.5;
        break;
    case 10:
        turing_u[xy].state = -0.939693;
        turing_v[xy].state = -0.342020;
        break;
    case 11:
        turing_u[xy].state = -0.984808;
        turing_v[xy].state = -0.173648;
        break;
    case 12:
        turing_u[xy].state = -1.0;
        turing_v[xy].state =  0.0;
        break;
    case 13:
        turing_u[xy].state = -0.984808;
        turing_v[xy].state =  0.173648;
        break;
    case 14:
        turing_u[xy].state = -0.939693;
        turing_v[xy].state =  0.342020;
        break;
    case 15:
        turing_u[xy].state = -0.866025;
        turing_v[xy].state =  0.5;
        break;
    case 16:
        turing_u[xy].state = -0.766044;
        turing_v[xy].state =  0.642788;
        break;
    case 17:
        turing_u[xy].state = -0.642788;
        turing_v[xy].state =  0.766044;
        break;
    case 18:
        turing_u[xy].state = -0.5;
        turing_v[xy].state =  0.866025;
        break;
    case 19:
        turing_u[xy].state = -0.342020;
        turing_v[xy].state =  0.939693;
        break;
    case 20:
        turing_u[xy].state = -0.173648;
        turing_v[xy].state =  0.984808;
        break;
    case 21:
        turing_u[xy].state =  0.0;
        turing_v[xy].state =  1.0;
        break;
    case 22:
        turing_u[xy].state =  0.173648;
        turing_v[xy].state =  0.984808;
        break;
    case 23:
        turing_u[xy].state =  0.342020;
        turing_v[xy].state =  0.939693;
        break;
    case 24:
        turing_u[xy].state =  0.5;
        turing_v[xy].state =  0.866025;
        break;
    case 25:
        turing_u[xy].state =  0.642788;
        turing_v[xy].state =  0.766044;
        break;
    case 26:
        turing_u[xy].state =  0.766044;
        turing_v[xy].state =  0.642788;
        break;
    case 27:
        turing_u[xy].state =  0.866025;
        turing_v[xy].state =  0.5;
        break;
    case 28:
        turing_u[xy].state =  0.939693;
        turing_v[xy].state =  0.342020;
        break;
    case 29:
        turing_u[xy].state =  0.984808;
        turing_v[xy].state =  0.173648;
        break;
    case 30:
        turing_u[xy].state =  1.0;
        turing_v[xy].state =  0.0;
        break;
    case 31:
        turing_u[xy].state =  0.984808;
        turing_v[xy].state = -0.173648;
        break;
    case 32:
        turing_u[xy].state =  0.939693;
        turing_v[xy].state = -0.342020;
        break;
    case 33:
        turing_u[xy].state =  0.866025;
        turing_v[xy].state = -0.5;
        break;
    case 34:
        turing_u[xy].state =  0.766044;
        turing_v[xy].state = -0.642788;
        break;
    case 35: case -1:
        turing_u[xy].state =  0.642788;
        turing_v[xy].state = -0.766044;
        break;
    }
}

void rainbow_to_turing(int xy, int* rainbow, turing_vector_t* turing_u, turing_vector_t* turing_v, int substate) {
    extra_color_to_turing(xy, (3*rainbow[xy] + substate), turing_u, turing_v);
}

void rainbow_add_to_turing(int xy, int* rainbow, turing_vector_t* turing_u, turing_vector_t* turing_v) {
    switch(3*rainbow[xy]+0) {
    case  0:
        turing_u[xy].state +=  0.5      * RA2T_I;
        turing_v[xy].state += -0.866025 * RA2T_I;
        break;
    case  1:
        turing_u[xy].state +=  0.342020 * RA2T_I;
        turing_v[xy].state += -0.939693 * RA2T_I;
        break;
    case  2:
        turing_u[xy].state +=  0.173648 * RA2T_I;
        turing_v[xy].state += -0.984808 * RA2T_I;
        break;
    case  3:
        turing_u[xy].state +=  0.0      * RA2T_I;
        turing_v[xy].state += -1.0      * RA2T_I;
        break;
    case  4:
        turing_u[xy].state += -0.173648 * RA2T_I;
        turing_v[xy].state += -0.984808 * RA2T_I;
        break;
    case  5:
        turing_u[xy].state += -0.342020 * RA2T_I;
        turing_v[xy].state += -0.939693 * RA2T_I;
        break;
    case  6:
        turing_u[xy].state += -0.5      * RA2T_I;
        turing_v[xy].state += -0.866025 * RA2T_I;
        break;
    case  7:
        turing_u[xy].state += -0.642788 * RA2T_I;
        turing_v[xy].state += -0.766044 * RA2T_I;
        break;
    case  8:
        turing_u[xy].state += -0.766044 * RA2T_I;
        turing_v[xy].state += -0.642788 * RA2T_I;
        break;
    case  9:
        turing_u[xy].state += -0.866025 * RA2T_I;
        turing_v[xy].state += -0.5      * RA2T_I;
        break;
    case 10:
        turing_u[xy].state += -0.939693 * RA2T_I;
        turing_v[xy].state += -0.342020 * RA2T_I;
        break;
    case 11:
        turing_u[xy].state += -0.984808 * RA2T_I;
        turing_v[xy].state += -0.173648 * RA2T_I;
        break;
    case 12:
        turing_u[xy].state += -1.0      * RA2T_I;
        turing_v[xy].state +=  0.0      * RA2T_I;
        break;
    case 13:
        turing_u[xy].state += -0.984808 * RA2T_I;
        turing_v[xy].state +=  0.173648 * RA2T_I;
        break;
    case 14:
        turing_u[xy].state += -0.939693 * RA2T_I;
        turing_v[xy].state +=  0.342020 * RA2T_I;
        break;
    case 15:
        turing_u[xy].state += -0.866025 * RA2T_I;
        turing_v[xy].state +=  0.5      * RA2T_I;
        break;
    case 16:
        turing_u[xy].state += -0.766044 * RA2T_I;
        turing_v[xy].state +=  0.642788 * RA2T_I;
        break;
    case 17:
        turing_u[xy].state += -0.642788 * RA2T_I;
        turing_v[xy].state +=  0.766044 * RA2T_I;
        break;
    case 18:
        turing_u[xy].state += -0.5      * RA2T_I;
        turing_v[xy].state +=  0.866025 * RA2T_I;
        break;
    case 19:
        turing_u[xy].state += -0.342020 * RA2T_I;
        turing_v[xy].state +=  0.939693 * RA2T_I;
        break;
    case 20:
        turing_u[xy].state += -0.173648 * RA2T_I;
        turing_v[xy].state +=  0.984808 * RA2T_I;
        break;
    case 21:
        turing_u[xy].state +=  0.0      * RA2T_I;
        turing_v[xy].state +=  1.0      * RA2T_I;
        break;
    case 22:
        turing_u[xy].state +=  0.173648 * RA2T_I;
        turing_v[xy].state +=  0.984808 * RA2T_I;
        break;
    case 23:
        turing_u[xy].state +=  0.342020 * RA2T_I;
        turing_v[xy].state +=  0.939693 * RA2T_I;
        break;
    case 24:
        turing_u[xy].state +=  0.5      * RA2T_I;
        turing_v[xy].state +=  0.866025 * RA2T_I;
        break;
    case 25:
        turing_u[xy].state +=  0.642788 * RA2T_I;
        turing_v[xy].state +=  0.766044 * RA2T_I;
        break;
    case 26:
        turing_u[xy].state +=  0.766044 * RA2T_I;
        turing_v[xy].state +=  0.642788 * RA2T_I;
        break;
    case 27:
        turing_u[xy].state +=  0.866025 * RA2T_I;
        turing_v[xy].state +=  0.5      * RA2T_I;
        break;
    case 28:
        turing_u[xy].state +=  0.939693 * RA2T_I;
        turing_v[xy].state +=  0.342020 * RA2T_I;
        break;
    case 29:
        turing_u[xy].state +=  0.984808 * RA2T_I;
        turing_v[xy].state +=  0.173648 * RA2T_I;
        break;
    case 30:
        turing_u[xy].state +=  1.0      * RA2T_I;
        turing_v[xy].state +=  0.0      * RA2T_I;
        break;
    case 31:
        turing_u[xy].state +=  0.984808 * RA2T_I;
        turing_v[xy].state += -0.173648 * RA2T_I;
        break;
    case 32:
        turing_u[xy].state +=  0.939693 * RA2T_I;
        turing_v[xy].state += -0.342020 * RA2T_I;
        break;
    case 33:
        turing_u[xy].state +=  0.866025 * RA2T_I;
        turing_v[xy].state += -0.5      * RA2T_I;
        break;
    case 34:
        turing_u[xy].state +=  0.766044 * RA2T_I;
        turing_v[xy].state += -0.642788 * RA2T_I;
        break;
    case 35: case -1:
        turing_u[xy].state +=  0.642788 * RA2T_I;
        turing_v[xy].state += -0.766044 * RA2T_I;
        break;
    }
}

int color_of_turing(int xy, turing_vector_t* turing_u, turing_vector_t* turing_v) {
    int z;
    
    if (turing_u[xy].state > 0.965926) {
        z = 6;
    } else if (turing_u[xy].state >  0.707107) {
        z = 5;
    } else if (turing_u[xy].state >  0.258819) {
        z = 4;
    } else if (turing_u[xy].state > -0.258819) {
        z = 3;
    } else if (turing_u[xy].state > -0.707107) {
        z = 2;
    } else if (turing_u[xy].state > -0.965926) {
        z = 1;
    } else {
        z = 0;
    }
    
    if (turing_v[xy].state < 0) {
        z *= -1;
    }
    
    z = (16+z) % COLORS;
    
    return z;
}

int extra_color_of_turing(int xy, turing_vector_t* turing_u, turing_vector_t* turing_v) {
    int z;
    
    if (turing_u[xy].state > 0.996195) {
        z = 18;
    } else if (turing_u[xy].state >  0.965926) {
        z = 17;
    } else if (turing_u[xy].state >  0.906308) {
        z = 16;
    } else if (turing_u[xy].state >  0.819152) {
        z = 15;
    } else if (turing_u[xy].state >  0.707107) {
        z = 14;
    } else if (turing_u[xy].state >  0.573576) {
        z = 13;
    } else if (turing_u[xy].state >  0.422618) {
        z = 12;
    } else if (turing_u[xy].state >  0.258819) {
        z = 11;
    } else if (turing_u[xy].state >  0.087156) {
        z = 10;
    } else if (turing_u[xy].state > -0.087156) {
        z =  9;
    } else if (turing_u[xy].state > -0.258819) {
        z =  8;
    } else if (turing_u[xy].state > -0.422618) {
        z =  7;
    } else if (turing_u[xy].state > -0.573576) {
        z =  6;
    } else if (turing_u[xy].state > -0.707107) {
        z =  5;
    } else if (turing_u[xy].state > -0.819152) {
        z =  4;
    } else if (turing_u[xy].state > -0.906308) {
        z =  3;
    } else if (turing_u[xy].state > -0.965926) {
        z =  2;
    } else if (turing_u[xy].state > -0.996195) {
        z =  1;
    } else {
        z =  0;
    }
    
    if (turing_v[xy].state < 0) {
        z *= -1;
    }
    
    z = (48+z) % EXTRA_COLORS;
    
    return EXTRA_COLOR + z;
}

// cyclic CA logic

void min_equals1_f(double* x, double y, int* t0, int s0) {
    if (y < *x) {
        *x = y;
        *t0 = s0;
    }
}

void max_equals(int* x, int y, int* t0, int s0, int* t1, int s1) {
    if (y > *x) {
        *x = y;
        *t0 = s0;
        *t1 = s1;
    }
}

void max_equals1(int* x, int y, int* t0, int s0) {
    if (y > *x) {
        *x = y;
        *t0 = s0;
    }
}

void max_equals2(int* x, int y, int* t0, int s0, int* t1, int s1) {
    if (y > *x) {
        *x = y;
        *t0 = s0;
        *t1 = s1;
    }
}

void max_equals3(int* x, int y, int* t0, int s0, int* t1, int s1, int* t2, int s2) {
    if (y > *x) {
        *x = y;
        *t0 = s0;
        *t1 = s1;
        *t2 = s2;
    }
}

int maybe_increment(int* grid, int xy, int target, int inc, int neighbors[COLORS], int* n_neighbors, int* impatience) {
    *n_neighbors += 1;
    
    if (grid[target] < 0) {
        return inc;
    }
    
    neighbors[grid[target]] += 1;
    
    if (inc == 2 || rand() < (impatience[xy] < 10 ? 0.15*RAND_MAX : 0.05*RAND_MAX)) {
        return inc;
    }
    if (grid[target] == (grid[xy] + 2) % COLORS && rand() < 0.25*RAND_MAX) { // CR-someday rrheingans-yoo: was 0.2; 0.25 is a lot
        return 2;
    }
    if (grid[target] == (grid[xy] + 1) % COLORS) {
        return 1;
    }
    return inc;
}

// hand-tuned to make rounded, unstable, cyclic-CA spirals with just enough 
// reshuffle to avoid getting stuck for too long
int compute_cyclic(int* grid, int* impatience, int xy) {
    impatience[xy] += 1;
    
    int n_neighbors;
    n_neighbors = 0;
    int neighbors[COLORS];
    for (int ii = 0; ii < COLORS; ++ii) {
        neighbors[ii] = 0;
    }
    
    int inc;
    inc = 0;
    
    int x = xy % COLS;
    int y = xy / COLS;
    int* offset = get_offset_array(x,y);
    
    for (int i = X_INIT(x,y); X_CONTINUE(x,y,i); ++i) {
        if (offset[i] != 0) {
            if (i % 2) { // orthogonal neighbor
                inc = maybe_increment(grid, xy, xy+offset[i], inc, neighbors, &n_neighbors, impatience);
            } else if (rand() < 0.5*RAND_MAX) { // was 0.6 // diagonal neighbor (maybe)
                inc = maybe_increment(grid, xy, xy+offset[i], inc, neighbors, &n_neighbors, impatience);
            }
        }
    }
    
    /* conformity for outliers */
    if (1) { // conform
        for(int ii = 0; ii < COLORS; ++ii){
            if (grid[xy] != ii) {
                if (
                    ( neighbors[ii] > 0.79 * n_neighbors && impatience[xy] > 5 )
                    || ( neighbors[ii] > 0.62 * n_neighbors && impatience[xy] > 30 )
                ) {
                    return ii;
                }
            }
        }
    }
    
    if (1) { // reshuffle
        /* propagate re-shuffle */
        if (inc) {
            impatience[xy] /= 2;
            if (impatience[xy] > 60) {
                return RAND_COLOR;
            }
        }
        
        /* precipitate re-shuffle */
        if (impatience[xy] > 100) {
            impatience[xy] = 0;
            return RAND_COLOR;
        }
    }
    
    return (grid[xy] + inc) % COLORS;
}

// Euclidean-distance decay

// hand-tuned to decay mostly like Euclidean distance
void compute_decay(
    int* orth, int* diag,
    int* orth_next, int* diag_next,
    int* directive_0, int* directive_1,
    int* directive_0_next, int* directive_1_next,
    int xy
) {
    int x = xy % COLS;
    int y = xy / COLS;
    int* offset = get_offset_array(x,y);
    
    int z_for_orth;
    int z_for_diag;
    int max_increment_orth;
    int max_increment_diag;
    
    orth_next[xy] = 0;
    diag_next[xy] = 0;
    
    for (int i = X_INIT(x,y); X_CONTINUE(x,y,i); ++i) {
        if (offset[i] != 0) {
            if (i % 2) { // orthogonal neighbor
                z_for_orth = orth[xy+offset[i]] - 17 + DECAYABLE_INCREMENT;
                z_for_diag = orth[xy+offset[i]] - 17 + DECAYABLE_INCREMENT;
                max_increment_orth = z_for_orth; // unbounded increment
                max_increment_diag = z_for_diag; // unbounded increment
            } else { // diagonal neighbor
                
                z_for_orth = diag[xy+offset[i]] - 21 + DECAYABLE_INCREMENT;
                z_for_diag = diag[xy+offset[i]] - 24 + DECAYABLE_INCREMENT;
                #ifdef DECAY_SQUARE
                    max_increment_orth = z_for_orth; // unbounded increment
                    max_increment_diag = z_for_diag; // unbounded increment
                #else /* DECAY_SQUARE */
                    max_increment_orth = 150;
                    max_increment_diag = 55;
                #endif /* DECAY_SQUARE */
            }
            
            max_equals(
                &orth_next[xy], min(orth[xy]+max_increment_orth,z_for_orth),
                &directive_0_next[xy], directive_0[xy+offset[i]],
                &directive_1_next[xy], directive_1[xy+offset[i]]
            );
            max_equals(
                &diag_next[xy], min(diag[xy]+max_increment_diag,z_for_diag),
                &directive_0_next[xy], directive_0[xy+offset[i]],
                &directive_1_next[xy], directive_1[xy+offset[i]]
            );
        }
    }
    
    if (orth_next[xy] <= 17) {
        directive_0_next[xy] = directive_0[xy];
        directive_1_next[xy] = directive_1[xy];
    }
}

// multiscale turing patterns logic

void diffuse_turing_reagent_horiz(
    turing_vector_t* vv, int radius,
    double* reagent, int* n_neighbors
) {
    int accum_neighbors = 0;
    
    *(
        (&vv[-1 + ROWS*COLS].scale[0].activ_tmp - &vv[0].scale[0].activ)
        + reagent
    ) = 0.0;
    
    for (int x_i = -radius; x_i<=radius; ++x_i) {
        accum_neighbors += *(
            (&vv[((0) + (x_i-1) + ROWS*COLS) % (ROWS*COLS)].scale[0].n_activ - &vv[0].scale[0].n_activ)
            + n_neighbors
        );
        *(
            (&vv[-1 + ROWS*COLS].scale[0].activ_tmp - &vv[0].scale[0].activ)
            + reagent
        ) += *(
            (&vv[((0) + (x_i-1) + ROWS*COLS) % (ROWS*COLS)].scale[0].activ - &vv[0].scale[0].activ)
            + reagent
        );
    }
    
    for (int xy=0; xy<ROWS*COLS; ++xy) {
        #ifdef THROTTLE_LOOP
        if (xy % THROTTLE_LOOP_N == 0) {
            usleep(THROTTLE_LOOP_USEC);
        }
        #endif /* THROTTLE_LOOP */
        *(
            (&vv[xy].scale[0].n_activ_tmp - &vv[0].scale[0].n_activ)
            + n_neighbors
        ) = accum_neighbors;
        
        
        *(
            (&vv[xy].scale[0].activ_tmp - &vv[0].scale[0].activ)
            + reagent
        ) = *(
            (&vv[(xy - 1 + ROWS*COLS) % (ROWS*COLS)].scale[0].activ_tmp - &vv[0].scale[0].activ)
            + reagent
        ) + *(
            (&vv[(xy + radius + ROWS*COLS) % (ROWS*COLS)].scale[0].activ - &vv[0].scale[0].activ)
            + reagent
        ) - *(
            (&vv[(xy + (-radius-1) + ROWS*COLS) % (ROWS*COLS)].scale[0].activ - &vv[0].scale[0].activ)
            + reagent
        );
   }
}

void diffuse_turing_reagent_vert(
    turing_vector_t* vv, int radius,
    double* reagent, int* n_neighbors
) {
    int accum_neighbors = 0;
    
    for (int y_i = -radius; y_i<=radius; ++y_i) {
        accum_neighbors += *(
            (&vv[((0) + (y_i*COLS) + (-1) + ROWS*COLS) % (ROWS*COLS)].scale[0].n_activ_tmp - &vv[0].scale[0].n_activ)
            + n_neighbors
        );
    }
    
    for (int xy=0; xy<COLS; ++xy) {
        *(
            (&vv[xy - COLS + ROWS*COLS].scale[0].activ - &vv[0].scale[0].activ)
            + reagent
        ) = 0.0;
        for (int y_i = -radius; y_i<=radius; ++y_i) {
            *(
                (&vv[xy - COLS + ROWS*COLS].scale[0].activ - &vv[0].scale[0].activ)
                + reagent
            ) += *(
                (&vv[(xy + ((y_i-1)*COLS) + ROWS*COLS) % (ROWS*COLS)].scale[0].activ_tmp - &vv[0].scale[0].activ)
                + reagent
            );
        }
    }
    
    for (int xy=0; xy<ROWS*COLS; ++xy) {
        #ifdef THROTTLE_LOOP
        if (xy % THROTTLE_LOOP_N == 0) {
            usleep(THROTTLE_LOOP_USEC);
        }
        #endif /* THROTTLE_LOOP */
        *(
            (&vv[xy].scale[0].n_activ - &vv[0].scale[0].n_activ)
            + n_neighbors
        ) = accum_neighbors;
        
        *(
            (&vv[xy].scale[0].activ - &vv[0].scale[0].activ)
            + reagent
        ) = *(
            (&vv[(xy - COLS + ROWS*COLS) % (ROWS*COLS)].scale[0].activ - &vv[0].scale[0].activ)
            + reagent
        ) + *(
            (&vv[(xy + radius*COLS) % (ROWS*COLS)].scale[0].activ_tmp - &vv[0].scale[0].activ)
            + reagent
        ) - *(
            (&vv[(xy + (-radius-1)*COLS + ROWS*COLS) % (ROWS*COLS)].scale[0].activ_tmp - &vv[0].scale[0].activ)
            + reagent
        );
    }
}

void diffuse_turing_reagents(turing_vector_t* vv) {
    diffuse_turing_reagent_horiz(vv,  2, &vv[0].scale[0].activ, &vv[0].scale[0].n_activ);
    diffuse_turing_reagent_horiz(vv,  4, &vv[0].scale[0].inhib, &vv[0].scale[0].n_inhib);
    
    diffuse_turing_reagent_horiz(vv,  4, &vv[0].scale[1].activ, &vv[0].scale[1].n_activ);
    diffuse_turing_reagent_horiz(vv,  8, &vv[0].scale[1].inhib, &vv[0].scale[1].n_inhib);
    
    diffuse_turing_reagent_horiz(vv,  8, &vv[0].scale[2].activ, &vv[0].scale[2].n_activ);
    diffuse_turing_reagent_horiz(vv, 16, &vv[0].scale[2].inhib, &vv[0].scale[2].n_inhib);
    
    diffuse_turing_reagent_horiz(vv, 16, &vv[0].scale[3].activ, &vv[0].scale[3].n_activ);
    diffuse_turing_reagent_horiz(vv, 32, &vv[0].scale[3].inhib, &vv[0].scale[3].n_inhib);
    
    diffuse_turing_reagent_horiz(vv, 32, &vv[0].scale[4].activ, &vv[0].scale[4].n_activ);
    diffuse_turing_reagent_horiz(vv, 64, &vv[0].scale[4].inhib, &vv[0].scale[4].n_inhib);
    
    diffuse_turing_reagent_vert(vv,  2, &vv[0].scale[0].activ, &vv[0].scale[0].n_activ);
    diffuse_turing_reagent_vert(vv,  4, &vv[0].scale[0].inhib, &vv[0].scale[0].n_inhib);
    
    diffuse_turing_reagent_vert(vv,  4, &vv[0].scale[1].activ, &vv[0].scale[1].n_activ);
    diffuse_turing_reagent_vert(vv,  8, &vv[0].scale[1].inhib, &vv[0].scale[1].n_inhib);
    
    diffuse_turing_reagent_vert(vv,  8, &vv[0].scale[2].activ, &vv[0].scale[2].n_activ);
    diffuse_turing_reagent_vert(vv, 16, &vv[0].scale[2].inhib, &vv[0].scale[2].n_inhib);
    
    diffuse_turing_reagent_vert(vv, 16, &vv[0].scale[3].activ, &vv[0].scale[3].n_activ);
    diffuse_turing_reagent_vert(vv, 32, &vv[0].scale[3].inhib, &vv[0].scale[3].n_inhib);
    
    diffuse_turing_reagent_vert(vv, 32, &vv[0].scale[4].activ, &vv[0].scale[4].n_activ);
    diffuse_turing_reagent_vert(vv, 64, &vv[0].scale[4].inhib, &vv[0].scale[4].n_inhib);
}

void compute_turing_all(turing_vector_t* uu, turing_vector_t* vv) {
    // initialize reagent arrays
    for (int xy=0; xy<ROWS*COLS; ++xy) {
        #ifdef THROTTLE_LOOP
        if (xy % THROTTLE_LOOP_N == 0) {
            usleep(THROTTLE_LOOP_USEC);
        }
        #endif /* THROTTLE_LOOP */
        
        for (int scl=0; scl<uu[xy].n_scales; ++scl) {
            uu[xy].scale[scl].n_activ = 1;
            uu[xy].scale[scl].activ = uu[xy].state;
            
            uu[xy].scale[scl].n_inhib = 1;
            uu[xy].scale[scl].inhib = uu[xy].state;
        }
        
        for (int scl=0; scl<vv[xy].n_scales; ++scl) {
            vv[xy].scale[scl].n_activ = 1;
            vv[xy].scale[scl].activ = vv[xy].state;
            
            vv[xy].scale[scl].n_inhib = 1;
            vv[xy].scale[scl].inhib = vv[xy].state;
        }
    }
    
    // diffuse reagents -- N-pass box blur
    for (int ii=0; ii<TURING_DIFFUSION_PASSES; ++ii) {
        #ifdef CAIRO_PAINT_BETWEEN_TURING_DIFFUSION_PASSES
            if (ii) {
                display_flush();
            }
        #endif /* CAIRO_PAINT_BETWEEN_TURING_DIFFUSION_PASSES */
        diffuse_turing_reagents(uu);
        diffuse_turing_reagents(vv);
    }
    
    // normalize reagents
    for (int xy=0; xy<ROWS*COLS; ++xy) {
        #ifdef THROTTLE_LOOP
        if (xy % THROTTLE_LOOP_N == 0) {
            usleep(THROTTLE_LOOP_USEC);
        }
        #endif /* THROTTLE_LOOP */
        for (int scl=0; scl<uu[xy].n_scales; ++scl) {
            uu[xy].scale[scl].activ /= uu[xy].scale[scl].n_activ;
            uu[xy].scale[scl].inhib /= uu[xy].scale[scl].n_inhib;
        }
        //uu[xy].scale[2].activ = 0.0;
        //uu[xy].scale[2].inhib = 0.0;
        //uu[xy].scale[1].activ = 0.0;
        //uu[xy].scale[1].inhib = 0.0;
        //uu[xy].scale[0].activ = 0.0;
        //uu[xy].scale[0].inhib = 0.9;
        
        for (int scl=0; scl<vv[xy].n_scales; ++scl) {
            vv[xy].scale[scl].activ /= vv[xy].scale[scl].n_activ;
            vv[xy].scale[scl].inhib /= vv[xy].scale[scl].n_inhib;
        }
        //vv[xy].scale[2].activ = 0.0;
        //vv[xy].scale[2].inhib = 0.0;
        //vv[xy].scale[1].activ = 0.0;
        //vv[xy].scale[1].inhib = 0.0;
        //vv[xy].scale[0].activ = 0.0;
        //vv[xy].scale[0].inhib = 0.0;
    }
}

int turing_min_var(turing_vector_t* vec, double custom_factor) {
    int arg_min_var = 0;
    double min_var = 1.0;
    
    for (int ii=0; ii<vec->n_scales; ++ii) {
        if (vec->scale[ii].activ == 0 && vec->scale[ii].inhib == 0) {
            // pass
        } else {
            double tt;
            /*
            tt = tt - (int)tt;
            tt = tt - 0.5;
            tt = fabs(tt);
            tt = tt + 0.03;
            */
            //tt = (double)(ii)/(double)(vec->n_scales) - custom_factor + 1.0;
            tt = 1.0;
            min_equals1_f(
                &min_var,
                (0.0 + fabs(vec->scale[ii].activ - vec->scale[ii].inhib)) * tt,
                &arg_min_var,
                ii
            );
        }
    }
    
    return arg_min_var;
}

void apply_turing(
    turing_vector_t* uu,
    turing_vector_t* vv,
    int xy,
    double annealing_factor,
    double custom_factor
) {
    int scl;
    
    scl = turing_min_var(&uu[xy], custom_factor);
    if (uu[xy].scale[scl].activ > uu[xy].scale[scl].inhib) {
        uu[xy].state += uu[xy].increment[scl] * annealing_factor;
    } else {
        uu[xy].state -= uu[xy].increment[scl] * annealing_factor;
    }
    uu[xy].debug = scl;
    
    scl = turing_min_var(&vv[xy], custom_factor);
    if (vv[xy].scale[scl].activ > vv[xy].scale[scl].inhib) {
        vv[xy].state += vv[xy].increment[scl] * annealing_factor;
    } else {
        vv[xy].state -= vv[xy].increment[scl] * annealing_factor;
    }
    vv[xy].debug = scl;
    
    double r;
    r = sqrt(uu[xy].state*uu[xy].state + vv[xy].state*vv[xy].state);
    uu[xy].state /= r;
    vv[xy].state /= r;
}

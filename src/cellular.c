#include <stdlib.h>

#include "cellular.h"

#include "constants.h"

int y_zero[] = {0, -1, -1+COLS, 0, 0, COLS, 0, 1, 1+COLS};
int y_wrap_x_zero[] = {-1, -1+COLS, -1+2*COLS, -COLS, 0, COLS, 1-COLS, 1, 1+COLS};
int y_wrap_x_cols_minus_one[] = {-1-COLS, -1, -1+COLS, -COLS, 0, COLS, 1-2*COLS, 1-COLS, 1};
int y_rows_minus_one[] = {-1-COLS, -1, 0, -COLS, 0, 0, 1-COLS, 1, 0};
int y_else[] = {-1-COLS, -1, -1+COLS, -COLS, 0, COLS, 1-COLS, 1, 1+COLS};

int y_northeast[] = {-1-COLS, -1, -COLS, -1+COLS, 0, 1-COLS, COLS, 1, 1+COLS};
//int y_northwest[] = {-1-COLS, -1, -1+COLS, -COLS, 0, COLS, 1-COLS, 1, 1+COLS};
int y_northwest[] = {1-COLS, 1, -COLS, 1+COLS, 0, -1-COLS, COLS, -1, -1+COLS};

int* get_offset_array(int x, int y) {
    switch (y) {
    case 0 :
        return y_zero;
    case ROWS-1 : 
        return y_rows_minus_one;
    default :
        
        if ((x == 0 || x == COLS-1)){
            if (y == BEVEL_RADIUS-2) {
                return y_zero;
            }
            if (COLS-1-y == BEVEL_RADIUS-2) {
                return y_rows_minus_one;
            }
            return y_else;
        }
        
        if (0
            || x + y == BEVEL_RADIUS-1
            || x + y == BEVEL_RADIUS
            || COLS-1-x + ROWS-1-y == BEVEL_RADIUS-1
            || COLS-1-x + ROWS-1-y == BEVEL_RADIUS
        ) {
            return y_northeast;
        }
        if (0
            || COLS-1-x + y == BEVEL_RADIUS-1
            || COLS-1-x + y == BEVEL_RADIUS
            || x + ROWS-1-y == BEVEL_RADIUS-1
            || x + ROWS-1-y == BEVEL_RADIUS
        ) {
            return y_northwest;
        }
        
        
        return y_else;
    }
}

#define X_INIT(x,y) \
    ((x) == 0 ? 3 : ( \
    (x) == COLS-1 ? 0 : ( \
    (y) == 0 || (y) == ROWS-1 ? ((x) == BEVEL_RADIUS-2 ? 3 : 0) : ( \
    (x) + (y) == BEVEL_RADIUS || COLS-1-(x) + (y) == BEVEL_RADIUS ? 1 : ( \
    (x) + (y) == BEVEL_RADIUS-1 || COLS-1-(x) + (y) == BEVEL_RADIUS-1 ? 3 : \
    0)))))

#define X_CONTINUE(x,y,i) \
    ((i) < ( \
    (x) == 0 ? 9 : ( \
    (x) == COLS-1 ? 6 : (\
    (y) == 0 || (y) == ROWS-1 ? (COLS-1-(x) == BEVEL_RADIUS-2 ? 6 : 9) : ( \
    x + ROWS-1-(y) == BEVEL_RADIUS || COLS-1-(x) + ROWS-1-(y) == BEVEL_RADIUS ? 8 : ( \
    x + ROWS-1-(y) == BEVEL_RADIUS-1 || COLS-1-(x) + ROWS-1-(y) == BEVEL_RADIUS-1 ? 6 : \
    9))))))


void max_equals(int* x, int y, int* t0, int s0, int* t1, int s1) {
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

int maybe_increment(int* grid, int xy, int target, int inc, int neighbors[COLORS], int* n_neighbors) {
    *n_neighbors += 1;
    
    if (grid[target] < 0) {
        return inc;
    }
    
    neighbors[grid[target]] += 1;
    
    if (inc == 2) {
        return inc;
    }
    if (grid[target] == (grid[xy] + 2) % COLORS && rand() < 0.22*RAND_MAX) {
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
                inc = maybe_increment(grid, xy, xy+offset[i], inc, neighbors, &n_neighbors);
            } else if (rand() < 0.6*RAND_MAX) { // diagonal neighbor (maybe)
                inc = maybe_increment(grid, xy, xy+offset[i], inc, neighbors, &n_neighbors);
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
            if (impatience[xy] > 35) {
                return RAND_COLOR;
            }
        }
        
        /* precipitate re-shuffle */
        //if (impatience[xy] > 100) {
        if (impatience[xy] > 200) {
            return RAND_COLOR;
        }
    }
    
    return (grid[xy] + inc) % COLORS;
}


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
                z_for_orth = orth[xy+offset[i]] - 17;
                z_for_diag = orth[xy+offset[i]] - 17;
                max_increment_orth = z_for_orth; // unbounded increment
                max_increment_diag = z_for_diag; // unbounded increment
            } else { // diagonal neighbor
                z_for_orth = diag[xy+offset[i]] - 21;
                z_for_diag = diag[xy+offset[i]] - 24;
                max_increment_orth = 150;
                max_increment_diag = 55;
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

void compute_hanabi(hanabi_cell* grid, hanabi_cell* grid_next, int xy) {
    int x = xy % COLS;
    int y = xy / COLS;
    int* offset = get_offset_array(x,y);
    
    int scratch;
    int z_for_orth;
    int z_for_diag;
    int live_neighbors = 0;
    
    /*
    if (grid[xy].orth > 0) {
        grid_next[xy].orth *= -1;
    } else if (grid[xy].orth < 0) {
        grid_next[xy].orth = 0;
    */
    if (grid[xy].orth > 0) {
        grid_next[xy].orth = 0;
        grid_next[xy].diag = 0;
    } else {
        grid_next[xy].orth = 0;
        grid_next[xy].diag = 0;
        
        for (int i = X_INIT(x,y); X_CONTINUE(x,y,i); ++i) {
            if (offset[i] != 0) {
                if (grid[xy+offset[i]].orth > 17) {
                    if (i % 2) { // orthogonal neighbor
                        z_for_orth = grid[xy+offset[i]].orth - 17;
                        z_for_diag = grid[xy+offset[i]].orth - 17;
                    } else { // diagonal neighbor
                        z_for_orth = grid[xy+offset[i]].diag - 21;
                        z_for_diag = grid[xy+offset[i]].diag - 24;
                    }
                    max_equals(
                        &grid_next[xy].orth, z_for_orth,
                        &grid_next[xy].color, grid[xy+offset[i]].color,
                        &scratch, scratch
                    );
                    max_equals(
                        &grid_next[xy].diag, z_for_diag,
                        &grid_next[xy].color, grid[xy+offset[i]].color,
                        &scratch, scratch
                    );
                    ++live_neighbors;
                }
            }
        }
        
        if (live_neighbors != 2) {
            grid_next[xy].orth = 0;
            grid_next[xy].diag = 0;
        }
    }
}

void run_hanabi_spark(hanabi_cell* grid, int xy, int color) {
    int x = xy % COLS;
    int y = xy / COLS;
    int* offset = get_offset_array(x,y);
    
    for (int i = X_INIT(x,y); X_CONTINUE(x,y,i); ++i) {
        grid[xy+offset[i]].orth = grid[xy+offset[i]].diag = 170 * (rand() % 3 ? 1 : 0); // CR rrheingans-yoo: tune this
        grid[xy+offset[i]].color = color;
    }
}

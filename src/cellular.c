#include <stdlib.h>

#include "cellular.h"

#include "constants.h"

void max_equals(int* x, int y, int* t0, int* t1, int s0, int s1) {
    if (y > *x) {
        *x = y;
        *t0 = s0;
        *t1 = s1;
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
    if ((rand() < 0.2*RAND_MAX) && grid[target] == (grid[xy] + 2) % COLORS) {
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
    
    if (x > 0) {
        inc = maybe_increment(grid, xy, xy-1, inc, neighbors, &n_neighbors);
    }
    if (x < COLS-1) {
        inc = maybe_increment(grid, xy, xy+1, inc, neighbors, &n_neighbors);
    }
    if (y > 0) {
        inc = maybe_increment(grid, xy, xy-COLS, inc, neighbors, &n_neighbors);
        if (rand() < 0.6*RAND_MAX) {
            if (x > 0) {
                inc = maybe_increment(grid, xy, xy-COLS-1, inc, neighbors, &n_neighbors);
            }
        }
        if (rand() < 0.6*RAND_MAX) {
            if (x < COLS-1) {
                inc = maybe_increment(grid, xy, xy-COLS+1, inc, neighbors, &n_neighbors);
            }
        }
    }
    if (y < ROWS-1) {
        inc = maybe_increment(grid, xy, xy+COLS, inc, neighbors, &n_neighbors);
        if (rand() < 0.6*RAND_MAX) {
            if (x > 0) {
                inc = maybe_increment(grid, xy, xy+COLS-1, inc, neighbors, &n_neighbors);
            }
        }
        if (rand() < 0.6*RAND_MAX) {
            if (x < COLS-1) {
                inc = maybe_increment(grid, xy, xy+COLS+1, inc, neighbors, &n_neighbors);
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
        if (impatience[xy] > 100) {
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
    orth_next[xy] = 0;
    diag_next[xy] = 0;
    
    int x = xy % COLS;
    int y = xy / COLS;
    
    // CR-someday rrheingans-yoo: it's probably possible to factor this 
    // boilerplate out into a function that uses global **s for the arrays.
    if (x > 0) {
        max_equals(
            &orth_next[xy], orth[xy-1]-17,
            &directive_0_next[xy], &directive_1_next[xy],
            directive_0[xy-1], directive_1[xy-1]
        );
        max_equals(
            &diag_next[xy], orth[xy-1]-17,
            &directive_0_next[xy], &directive_1_next[xy],
            directive_0[xy-1], directive_1[xy-1]
        );
    }
    if (x < COLS-1) {
        max_equals(
            &orth_next[xy], orth[xy+1]-17,
            &directive_0_next[xy], &directive_1_next[xy],
            directive_0[xy+1], directive_1[xy+1]
        );
        max_equals(
            &diag_next[xy], orth[xy+1]-17,
            &directive_0_next[xy], &directive_1_next[xy],
            directive_0[xy+1], directive_1[xy+1]
        );
    }
    if (y > 0) {
        max_equals(
            &orth_next[xy], orth[xy-COLS]-17,
            &directive_0_next[xy], &directive_1_next[xy],
            directive_0[xy-COLS], directive_1[xy-COLS]
        );
        max_equals(
            &diag_next[xy], orth[xy-COLS]-17,
            &directive_0_next[xy], &directive_1_next[xy],
            directive_0[xy-COLS], directive_1[xy-COLS]
        );
        if (x > 0) {
            max_equals(
                &orth_next[xy], min(orth[xy]+150,diag[xy-COLS-1]-(38-17)),
                &directive_0_next[xy], &directive_1_next[xy],
                directive_0[xy-COLS-1], directive_1[xy-COLS-1]
            );
            max_equals(
                &diag_next[xy], min(orth[xy]+55, diag[xy-COLS-1]-24),
                &directive_0_next[xy], &directive_1_next[xy],
                directive_0[xy-COLS-1], directive_1[xy-COLS-1]
            );
        }
        if (x < COLS-1) {
            max_equals(
                &orth_next[xy], min(orth[xy]+150, diag[xy-COLS+1]-(38-17)),
                &directive_0_next[xy], &directive_1_next[xy],
                directive_0[xy-COLS+1], directive_1[xy-COLS+1]
            );
            max_equals(
                &diag_next[xy], min(orth[xy]+55, diag[xy-COLS+1]-24),
                &directive_0_next[xy], &directive_1_next[xy],
                directive_0[xy-COLS+1], directive_1[xy-COLS+1]
            );
        }
    }
    if (y < ROWS-1) {
        max_equals(
            &orth_next[xy], orth[xy+COLS]-17,
            &directive_0_next[xy], &directive_1_next[xy],
            directive_0[xy+COLS], directive_1[xy+COLS]
        );
        max_equals(
            &diag_next[xy], orth[xy+COLS]-17,
            &directive_0_next[xy], &directive_1_next[xy],
            directive_0[xy+COLS], directive_1[xy+COLS]
        );
        if (x > 0) {
            max_equals(
                &orth_next[xy], min(orth[xy]+150, diag[xy+COLS-1]-(38-17)),
                &directive_0_next[xy], &directive_1_next[xy],
                directive_0[xy+COLS-1], directive_1[xy+COLS-1]
            );
            max_equals(
                &diag_next[xy], min(orth[xy]+55,diag[xy+COLS-1]-24),
                &directive_0_next[xy], &directive_1_next[xy],
                directive_0[xy+COLS-1], directive_1[xy+COLS-1]
            );
        }
        if (x < COLS-1) {
            max_equals(
                &orth_next[xy], min(orth[xy]+150,diag[xy+COLS+1]-(38-17)),
                &directive_0_next[xy], &directive_1_next[xy],
                directive_0[xy+COLS+1], directive_1[xy+COLS+1]
            );
            max_equals(
                &diag_next[xy], min(orth[xy]+55, diag[xy+COLS+1]-24),
                &directive_0_next[xy], &directive_1_next[xy],
                directive_0[xy+COLS+1], directive_1[xy+COLS+1]
            );
        }
    }
    if (orth_next[xy] <= 17) {
        directive_0_next[xy] = directive_0[xy];
        directive_1_next[xy] = directive_1[xy];
    }
}

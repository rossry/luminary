#include <stdlib.h>
#include <math.h>

#include <assert.h>

#include "cellular.h"

#include "constants.h"

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
    case 0 : // CR rrheingans-yoo: use y_upper_join if PETALS_ACTIVE
        switch (x % PETAL_COLS) {
        case 0 :
            return y_upper_left;
        case PETAL_COLS-1 :
            return y_upper_right;
        }
        return y_zero;
    case ROWS-1 : 
        return y_rows_minus_one;
    default :
        if (y < PETAL_ROWS && y > 24) {
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
        (((y) < PETAL_ROWS + 3 && (y) > PETAL_ROWS_SEPARATED) \
            || ((x) < COLS-1 && ((y) > PETAL_ROWS_SEPARATED || (x) % PETAL_COLS < PETAL_COLS-1))) ? 9 : \
        6))

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

int maybe_increment(int* grid, int xy, int target, int inc, int neighbors[COLORS], int* n_neighbors) {
    *n_neighbors += 1;
    
    if (grid[target] < 0) {
        return inc;
    }
    
    neighbors[grid[target]] += 1;
    
    if (inc == 2) {
        return inc;
    }
    if (grid[target] == (grid[xy] + 2) % COLORS && rand() < 0.22*RAND_MAX) { // CR-someday rrheingans-yoo: was 0.2; 0.25 is a lot
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
            if (impatience[xy] > 50) {
                return RAND_COLOR;
            }
        }
        
        /* precipitate re-shuffle */
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

// CR rrheingans-yoo: clean up
void diffuse_turing_reagent_horiz(
    turing_vector_t* vv, int radius,
    double* reagent, int* n_neighbors
) {
    int accum_neighbors = 0;
    
    *(
        (&vv[ROWS*COLS-1].scale[0].activ_tmp - &vv[0].scale[0].activ)
        + reagent
    ) = 0.0;
    
    int y_i = 0;
    //for (int y_i = 1-radius; y_i<radius; ++y_i) {
        for (int x_i = -radius; x_i<=radius; ++x_i) {
            accum_neighbors += *(
                (&vv[((0) + (y_i*COLS) + (x_i-1) + ROWS*COLS) % (ROWS*COLS)].scale[0].n_activ - &vv[0].scale[0].n_activ)
                + n_neighbors
            );
            *(
                (&vv[ROWS*COLS-1].scale[0].activ_tmp - &vv[0].scale[0].activ)
                + reagent
            ) += *(
                (&vv[((0) + (y_i*COLS) + (x_i-1) + ROWS*COLS) % (ROWS*COLS)].scale[0].activ - &vv[0].scale[0].activ)
                + reagent
            );
        }
    //}
    
    /*
    *(
        (&vv[ROWS*COLS-1].scale[0].activ_tmp - &vv[0].scale[0].activ)
        + reagent
    ) = accum;
    */
    
    for (int xy=0; xy<ROWS*COLS; ++xy) { 
        int y_i = 0;
        //for (int y_i = -radius; y_i<radius; ++y_i) {
            for (int x_i = -radius; x_i<=radius; ++x_i) {
                /*
                *(
                    (&vv[xy].scale[0].n_activ_tmp - &vv[0].scale[0].n_activ)
                    + n_neighbors
                ) += *(
                    (&vv[(xy + (y_i*COLS) + x_i + ROWS*COLS) % (ROWS*COLS)].scale[0].n_activ - &vv[0].scale[0].n_activ)
                    + n_neighbors
                );
                */
                /*
                *(
                    (&vv[xy].scale[0].activ_tmp - &vv[0].scale[0].activ)
                    + reagent
                ) += *(
                    (&vv[(xy + (y_i*COLS) + x_i + ROWS*COLS) % (ROWS*COLS)].scale[0].activ - &vv[0].scale[0].activ)
                    + reagent
                );
                */
            }
        //}
        
        /*
        assert(
            *(
                (&vv[(xy + (y_i*COLS) + (radius+1) + ROWS*COLS) % (ROWS*COLS)].scale[0].n_activ - &vv[0].scale[0].n_activ)
                + n_neighbors
        ) == *(
                (&vv[(xy + (y_i*COLS) + (-radius) + ROWS*COLS) % (ROWS*COLS)].scale[0].n_activ - &vv[0].scale[0].n_activ)
                + n_neighbors
            )
        );
        assert(accum_neighbors == *(
                (&vv[xy].scale[0].n_activ_tmp - &vv[0].scale[0].n_activ)
                + n_neighbors
            )
        );
        */
        *(
            (&vv[xy].scale[0].n_activ_tmp - &vv[0].scale[0].n_activ)
            + n_neighbors
        ) = accum_neighbors;
        
        
        //accum = *(
        *(
            (&vv[xy].scale[0].activ_tmp - &vv[0].scale[0].activ)
            + reagent
        ) = *(
            (&vv[(xy + (y_i*COLS) + (-1) + ROWS*COLS) % (ROWS*COLS)].scale[0].activ_tmp - &vv[0].scale[0].activ)
            + reagent
        ) + *(
            (&vv[(xy + (y_i*COLS) + (radius) + ROWS*COLS) % (ROWS*COLS)].scale[0].activ - &vv[0].scale[0].activ)
            + reagent
        ) - *(
            (&vv[(xy + (y_i*COLS) + (-radius-1) + ROWS*COLS) % (ROWS*COLS)].scale[0].activ - &vv[0].scale[0].activ)
            + reagent
        );
        
        /*
        assert(
            accum - *(
                (&vv[xy].scale[0].activ_tmp - &vv[0].scale[0].activ)
                + reagent
            ) < 0.0000001
        );*/
        /**(
            (&vv[xy].scale[0].activ_tmp - &vv[0].scale[0].activ)
            + reagent
        ) = accum;
        */
   }
}

// CR rrheingans-yoo: clean up
void diffuse_turing_reagent_vert(
    turing_vector_t* vv, int radius,
    double* reagent, int* n_neighbors
) {
    int accum_neighbors = 0;
    
    /*
    *(
        (&vv[ROWS*COLS-1].scale[0].activ_tmp - &vv[0].scale[0].activ)
        + reagent
    ) = 0.0;
    */
    
    for (int y_i = -radius; y_i<=radius; ++y_i) {
        int x_i = 0;
        //for (int x_i = -radius; x_i<=radius; ++x_i) {
            accum_neighbors += *(
                (&vv[((0) + (y_i*COLS) + (x_i-1) + ROWS*COLS) % (ROWS*COLS)].scale[0].n_activ_tmp - &vv[0].scale[0].n_activ)
                + n_neighbors
            );
            /*
            *(
                (&vv[ROWS*COLS-1].scale[0].activ_tmp - &vv[0].scale[0].activ)
                + reagent
            ) += *(
                (&vv[((0) + (y_i*COLS) + (x_i-1) + ROWS*COLS) % (ROWS*COLS)].scale[0].activ - &vv[0].scale[0].activ)
                + reagent
            );
            */
        //}
    }
    
    for (int xy=0; xy<COLS; ++xy) {
        for (int y_i = -radius; y_i<=radius; ++y_i) {
            int x_i = 0;
            //for (int x_i = -radius; x_i<=radius; ++x_i) {
                *(
                    (&vv[xy - COLS + ROWS*COLS].scale[0].activ - &vv[0].scale[0].activ)
                    + reagent
                ) += *(
                    (&vv[(xy + ((y_i-1)*COLS) + x_i + ROWS*COLS) % (ROWS*COLS)].scale[0].activ_tmp - &vv[0].scale[0].activ)
                    + reagent
                );
            //}
        }
    }
    
    for (int xy=0; xy<ROWS*COLS; ++xy) {
        /*
        for (int y_i = -radius; y_i<=radius; ++y_i) {
            int x_i = 0;
            //for (int x_i = -radius; x_i<radius; ++x_i) {
                *(
                    (&vv[xy].scale[0].n_activ - &vv[0].scale[0].n_activ)
                    + n_neighbors
                ) += *(
                    (&vv[(xy + (y_i*COLS) + x_i + ROWS*COLS) % (ROWS*COLS)].scale[0].n_activ_tmp - &vv[0].scale[0].n_activ)
                    + n_neighbors
                );
                *(
                    (&vv[xy].scale[0].activ - &vv[0].scale[0].activ)
                    + reagent
                ) += *(
                    (&vv[(xy + (y_i*COLS) + x_i + ROWS*COLS) % (ROWS*COLS)].scale[0].activ_tmp - &vv[0].scale[0].activ)
                    + reagent
                );
            //}
        }
        
        
        assert(
            *(
                (&vv[(xy + ((radius+1)*COLS) + (0) + ROWS*COLS) % (ROWS*COLS)].scale[0].n_activ_tmp - &vv[0].scale[0].n_activ)
                + n_neighbors
            ) == *(
                (&vv[(xy + ((-radius)*COLS) + (0) + ROWS*COLS) % (ROWS*COLS)].scale[0].n_activ_tmp - &vv[0].scale[0].n_activ)
                + n_neighbors
            )
        );
        assert(
            *(
                (&vv[xy].scale[0].n_activ - &vv[0].scale[0].n_activ)
                + n_neighbors
            ) == accum_neighbors
        );
        
        assert( xy < COLS ||
            *(
                (&vv[xy].scale[0].activ - &vv[0].scale[0].activ)
                + reagent
            ) - ( *(
                    (&vv[(xy + ((-1)*COLS) + (0) + ROWS*COLS) % (ROWS*COLS)].scale[0].activ - &vv[0].scale[0].activ)
                    + reagent
                ) + *(
                    (&vv[(xy + ((radius)*COLS) + (0) + ROWS*COLS) % (ROWS*COLS)].scale[0].activ_tmp - &vv[0].scale[0].activ)
                    + reagent
                ) - *(
                    (&vv[(xy + ((-radius-1)*COLS) + (0) + ROWS*COLS) % (ROWS*COLS)].scale[0].activ_tmp - &vv[0].scale[0].activ)
                    + reagent
                )
            ) < 0.001
        );
        */
        
        *(
            (&vv[xy].scale[0].n_activ - &vv[0].scale[0].n_activ)
            + n_neighbors
        ) = accum_neighbors;
        
        *(
            (&vv[xy].scale[0].activ - &vv[0].scale[0].activ)
            + reagent
        ) = *(
            (&vv[(xy + ((-1)*COLS) + (0) + ROWS*COLS) % (ROWS*COLS)].scale[0].activ - &vv[0].scale[0].activ)
            + reagent
        ) + *(
            (&vv[(xy + ((radius)*COLS) + (0) + ROWS*COLS) % (ROWS*COLS)].scale[0].activ_tmp - &vv[0].scale[0].activ)
            + reagent
        ) - *(
            (&vv[(xy + ((-radius-1)*COLS) + (0) + ROWS*COLS) % (ROWS*COLS)].scale[0].activ_tmp - &vv[0].scale[0].activ)
            + reagent
        );
    }
}

void compute_turing(turing_vector_t* vv, int pass) {
    if (pass%2 == 1) {
        diffuse_turing_reagent_horiz(vv,  1, &vv[0].scale[0].activ, &vv[0].scale[0].n_activ);
        diffuse_turing_reagent_horiz(vv,  2, &vv[0].scale[0].inhib, &vv[0].scale[0].n_inhib);
        
        diffuse_turing_reagent_horiz(vv,  3, &vv[0].scale[1].activ, &vv[0].scale[1].n_activ);
        diffuse_turing_reagent_horiz(vv,  6, &vv[0].scale[1].inhib, &vv[0].scale[1].n_inhib);
        
        diffuse_turing_reagent_horiz(vv, 10, &vv[0].scale[2].activ, &vv[0].scale[2].n_activ);
        diffuse_turing_reagent_horiz(vv, 20, &vv[0].scale[2].inhib, &vv[0].scale[2].n_inhib);
    } else {
        diffuse_turing_reagent_vert(vv,  1, &vv[0].scale[0].activ, &vv[0].scale[0].n_activ);
        diffuse_turing_reagent_vert(vv,  2, &vv[0].scale[0].inhib, &vv[0].scale[0].n_inhib);
        
        diffuse_turing_reagent_vert(vv,  3, &vv[0].scale[1].activ, &vv[0].scale[1].n_activ);
        diffuse_turing_reagent_vert(vv,  6, &vv[0].scale[1].inhib, &vv[0].scale[1].n_inhib);
        
        diffuse_turing_reagent_vert(vv, 10, &vv[0].scale[2].activ, &vv[0].scale[2].n_activ);
        diffuse_turing_reagent_vert(vv, 20, &vv[0].scale[2].inhib, &vv[0].scale[2].n_inhib);
    }
}

void turing_zero_reagents(turing_vector_t* uu, turing_vector_t* vv) {
    for (int xy=0; xy<ROWS*COLS; ++xy) {
        for (int scl=0; scl<uu[xy].n_scales; ++scl) {
            uu[xy].scale[scl].n_activ = 0;
            uu[xy].scale[scl].activ = 0.0;
            uu[xy].scale[scl].n_inhib = 0;
            uu[xy].scale[scl].inhib = 0.0;
        }
        for (int scl=0; scl<uu[xy].n_scales; ++scl) {
            vv[xy].scale[scl].n_activ = 0;
            vv[xy].scale[scl].activ = 0.0;
            vv[xy].scale[scl].n_inhib = 0;
            vv[xy].scale[scl].inhib = 0.0;
        }
    }
}

void turing_zero_tmp_reagents(turing_vector_t* uu, turing_vector_t* vv) {
    for (int xy=0; xy<ROWS*COLS; ++xy) {
        for (int scl=0; scl<uu[xy].n_scales; ++scl) {
            uu[xy].scale[scl].n_activ_tmp = 0;
            uu[xy].scale[scl].activ_tmp = 0.0;
            uu[xy].scale[scl].n_inhib_tmp = 0;
            uu[xy].scale[scl].inhib_tmp = 0.0;
        }
        for (int scl=0; scl<uu[xy].n_scales; ++scl) {
            vv[xy].scale[scl].n_activ_tmp = 0;
            vv[xy].scale[scl].activ_tmp = 0.0;
            vv[xy].scale[scl].n_inhib_tmp = 0;
            vv[xy].scale[scl].inhib_tmp = 0.0;
        }
    }
}

void compute_turing_all(turing_vector_t* uu, turing_vector_t* vv) {
    // initialize
    for (int xy=0; xy<ROWS*COLS; ++xy) {
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
    turing_zero_tmp_reagents(uu, vv);
    
    // diffuse reagents
    // CR rrheingans-yoo: clean up repetition
    
    compute_turing(uu, 1);
    compute_turing(vv, 1);
    turing_zero_reagents(uu, vv);
    compute_turing(uu, 2);
    compute_turing(vv, 2);
    turing_zero_tmp_reagents(uu, vv);
    
    compute_turing(uu, 3);
    compute_turing(vv, 3);
    turing_zero_reagents(uu, vv);
    compute_turing(uu, 4);
    compute_turing(vv, 4);
    turing_zero_tmp_reagents(uu, vv);
    
    compute_turing(uu, 5);
    compute_turing(vv, 5);
    turing_zero_reagents(uu, vv);
    compute_turing(uu, 6);
    compute_turing(vv, 6);
    // turing_zero_tmp_reagents(uu, vv);
    
    // normalize reagents
    for (int xy=0; xy<ROWS*COLS; ++xy) {
        for (int scl=0; scl<uu[xy].n_scales; ++scl) {
            uu[xy].scale[scl].activ /= uu[xy].scale[scl].n_activ;
            uu[xy].scale[scl].inhib /= uu[xy].scale[scl].n_inhib;
        }
        //uu[xy].scale[2].activ = 0.0;
        //uu[xy].scale[2].inhib = 0.0;
        //uu[xy].scale[1].activ = 0.0;
        //uu[xy].scale[1].inhib = 0.0;
        //uu[xy].scale[0].activ = 0.0;
        //uu[xy].scale[0].inhib = 0.0;
        
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

int turing_min_var(turing_vector_t* vec) {
    int arg_min_var = 0;
    double min_var = 1.0;
    
    for (int ii=0; ii<vec->n_scales; ++ii) {
        if (vec->scale[ii].activ == 0 && vec->scale[ii].inhib == 0) {
            // pass
        } else {
            min_equals1_f(
                &min_var,
                fabs(vec->scale[ii].activ - vec->scale[ii].inhib),
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
    double annealing_factor
) {
    int scl;
    
    scl = turing_min_var(&uu[xy]);
    if (uu[xy].scale[scl].activ > uu[xy].scale[scl].inhib) {
        uu[xy].state += uu[xy].increment[scl] * annealing_factor;
    } else {
        uu[xy].state -= uu[xy].increment[scl] * annealing_factor;
    }
    uu[xy].debug = scl;
    
    scl = turing_min_var(&vv[xy]);
    if (vv[xy].scale[scl].activ > vv[xy].scale[scl].inhib) {
        vv[xy].state += vv[xy].increment[scl] * annealing_factor;
    } else {
        vv[xy].state -= vv[xy].increment[scl] * annealing_factor;
    }
    vv[xy].debug = scl;
    
    double r;
    r = uu[xy].state*uu[xy].state + vv[xy].state*vv[xy].state;
    uu[xy].state /= r;
    vv[xy].state /= r;
}

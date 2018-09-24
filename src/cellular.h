#ifndef CELLULAR_H
#define CELLULAR_H

typedef struct hanabi_cell {
    int color;
    int orth;
    int diag;
} hanabi_cell;

int compute_cyclic(int* grid, int* impatience, int xy);

void compute_decay(
    int* orth, int* diag,
    int* orth_next, int* diag_next,
    int* directive_0, int* directive_1,
    int* directive_0_next, int* directive_1_next,
    int xy
);

void compute_hanabi(
    hanabi_cell* grid,
    hanabi_cell* grid_next,
    int xy
);
void run_hanabi_spark(
    hanabi_cell* grid,
    int xy,
    int color
);

typedef struct turing_reagent {
    double activ;
    double inhib;
    
    double activ_tmp;
    double inhib_tmp;
    
    int n_activ;
    int n_inhib;
    
    int n_activ_tmp;
    int n_inhib_tmp;
} turing_reagent_t;

#define MAX_TURING_SCALES 4

typedef struct vector {
    double state;
    int n_scales;
    turing_reagent_t scale[MAX_TURING_SCALES];
    double increment[MAX_TURING_SCALES];
    
    int debug;
} turing_vector_t;

void compute_turing_all(
    turing_vector_t* u_reagents,
    turing_vector_t* v_reagents
);

void apply_turing(
    turing_vector_t* u_reagents,
    turing_vector_t* v_reagents,
    int xy,
    double annealing_factor
);

#endif /* CELLULAR_H */

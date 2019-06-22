#ifndef CELLULAR_H
#define CELLULAR_H

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

#define MAX_TURING_SCALES 5

typedef struct vector {
    double state;
    int n_scales;
    turing_reagent_t scale[MAX_TURING_SCALES];
    double increment[MAX_TURING_SCALES];
    
    int debug;
} turing_vector_t;

// sets (turing_u, turing_v) from c
void extra_color_to_turing(
    int xy,
    int c,
    turing_vector_t* turing_u,
    turing_vector_t* turing_v
);

// sets (turing_u, turing_v) from rainbow
void rainbow_to_turing(
    int xy,
    int* rainbow,
    turing_vector_t* turing_u,
    turing_vector_t* turing_v,
    int substate // {-1,0,1}
);

// increments (turing_u, turing_v) by rainbow*scale
void rainbow_add_to_turing(
   int xy,
   int* rainbow,
   turing_vector_t* turing_u,
   turing_vector_t* turing_v
);

// returns a color from (turing_u, turing_v)
int color_of_turing(
    int xy,
    turing_vector_t* turing_u,
    turing_vector_t* turing_v
);
// returns an extended-palette color from (turing_u, turing_v)
int extra_color_of_turing(
    int xy,
    turing_vector_t* turing_u,
    turing_vector_t* turing_v
);

int compute_cyclic(int* grid, int* impatience, int xy);

void compute_decay(
    int* orth, int* diag,
    int* orth_next, int* diag_next,
    int* directive_0, int* directive_1,
    int* directive_0_next, int* directive_1_next,
    int xy
);

void compute_turing_all(
    turing_vector_t* u_reagents,
    turing_vector_t* v_reagents
);

void apply_turing(
    turing_vector_t* u_reagents,
    turing_vector_t* v_reagents,
    int xy,
    double annealing_factor,
    double custom_factor
);

#endif /* CELLULAR_H */

#ifndef CELLULAR_H
#define CELLULAR_H

int compute_cyclic(int* grid, int* impatience, int xy);

void compute_decay(
    int* orth, int* diag,
    int* orth_next, int* diag_next,
    int* directive_0, int* directive_1,
    int* directive_0_next, int* directive_1_next,
    int xy
);

#endif /* CELLULAR_H */

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

void compute_hanabi(hanabi_cell* grid, hanabi_cell* grid_next, int xy);
void run_hanabi_spark(hanabi_cell* grid, int xy, int color);

#endif /* CELLULAR_H */

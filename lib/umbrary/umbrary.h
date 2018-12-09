#ifndef UMBRARY_H
#define UMBRARY_H

#define UMBRARY_VERBOSE 1

#define UMBRARY_PIXEL_WIDTH 5

#define UMBRARY_INPUT_ROWS 360
#define UMBRARY_INPUT_COLS 640

#define UMBRARY_OUTPUT_ROWS ((UMBRARY_INPUT_ROWS - 1) / UMBRARY_PIXEL_WIDTH + 1)
#define UMBRARY_OUTPUT_COLS ((UMBRARY_INPUT_COLS - 1) / UMBRARY_PIXEL_WIDTH + 1)

double umbrary_time;
int umbrary_level[UMBRARY_OUTPUT_ROWS*UMBRARY_OUTPUT_COLS]; // {-1, 0, 1}

//debugging
int umbrary_usec_elapsed();

void umbrary_init(const char* umbrary_filename_format);
// no destroy necessary

void umbrary_update(int usec); // 0 to use usec since umbrary_init

// sleep until time elapsed will equal umbrary_time
void umbrary_delay();

void umbrary_sample_frame(int file_i, const char* filename);

#endif /* UMBRARY_H */

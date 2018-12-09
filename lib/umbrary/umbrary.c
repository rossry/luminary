#include <stdio.h>
#include <unistd.h>
#include <string.h>
#include <stdlib.h>
#include <errno.h>
#include <sys/time.h>
#include <math.h>
#include <assert.h>

#include "umbrary.h"

#include "bmp.h"
typedef struct image image_t;

struct timeval start;

image_t* img;
const char* filename_format;

long long bg_sum[UMBRARY_INPUT_ROWS*UMBRARY_INPUT_COLS];
double bg_stdev[UMBRARY_INPUT_ROWS*UMBRARY_INPUT_COLS];
int bg_bin_count[UMBRARY_INPUT_ROWS*UMBRARY_INPUT_COLS*12];
int bg_med[UMBRARY_INPUT_ROWS*UMBRARY_INPUT_COLS];

int umbrary_usec_elapsed() {
    struct timeval now;
    gettimeofday(&now, NULL);
    return (now.tv_usec - start.tv_usec) + (now.tv_sec - start.tv_sec)*1000*1000;
}

void umbrary_delay() {
    int usec_elapsed = umbrary_usec_elapsed();
    
    if (umbrary_time*1000*1000 > usec_elapsed) {
        usleep(umbrary_time*1000*1000 - usec_elapsed);
    }
    
    #ifdef UMBRARY_VERBOSE
        printf("%.3f sec (frame)\n", umbrary_time);
        printf("%.3f sec (elapsed)\n", umbrary_usec_elapsed()/1000000.0);
    #endif /* UMBRARY_VERBOSE */
}

image_t* umbrary_load_bmp(int file_i) {
    char filename[257];
    sprintf(filename, filename_format, file_i);
    return load_bmp(filename);
}

void umbrary_compute_means() {
    // pass 1: compute means and stdevs
    
    for (int xy=0; xy<UMBRARY_INPUT_ROWS*UMBRARY_INPUT_COLS; ++xy) {
        bg_sum[xy] = 0;
        bg_stdev[xy] = 0;
    }
    
    int keep_going = 1;
    for (int file_i=1; file_i<6000 && keep_going; ++file_i) {
        img = umbrary_load_bmp(file_i);
        
        if (img == NULL) {
            keep_going = 0;
            
            #ifdef UMBRARY_VERBOSE
                printf("compute means...\n");
            #endif /* UMBRARY_VERBOSE */
            
            for (int xy=0; xy<UMBRARY_INPUT_ROWS*UMBRARY_INPUT_COLS; ++xy) {
                bg_sum[xy] /= (file_i-1);
                bg_med[xy] = (int)bg_sum[xy];
                bg_stdev[xy] /= (file_i-1);
                bg_stdev[xy] -= bg_sum[xy] * bg_sum[xy];
                bg_stdev[xy] = sqrt(bg_stdev[xy]);
                
                /*
                if (xy % 10000 == 0) {
                    printf(
                        "%lld+/-%5.1f\n",
                        bg_sum[xy],
                        bg_stdev[xy]
                    );
                }
                */
            }
        } else {
            for (int xy=0; xy<img->pixel_array_size/3; ++xy) {
                int intensity = (
                    img->pixel_array[xy*3+0]
                    + img->pixel_array[xy*3+1]
                    + img->pixel_array[xy*3+2]
                );
                
                bg_sum[xy] += intensity;
                bg_stdev[xy] += intensity * intensity;
            }
            
            assert(img->width == UMBRARY_INPUT_COLS);
            assert(img->height == UMBRARY_INPUT_ROWS);
            //assert(img->pixel_array_size/3 == UMBRARY_INPUT_ROWS*UMBRARY_INPUT_COLS);
            
            free_image(img);
        }
    }
}

// refine medians by up to 5*bin_width, in increments of bin_width*(pixel_stdev)
// for 3*8-bit color-depth, a pass of bin_width=0.002 will resolve to single ticks
void umbrary_refine_medians(double bin_width) {
    for (int xy=0; xy<UMBRARY_INPUT_ROWS*UMBRARY_INPUT_COLS; ++xy) {
        for (int ii=0; ii<12; ++ii) {
            bg_bin_count[xy*12+ii] = 0;
        }
    }
    
    int keep_going = 1;
    for (int file_i=1; file_i<6000 && keep_going; ++file_i) {
        img = umbrary_load_bmp(file_i);
        
        if (img == NULL) {
            keep_going = 0;
            
            #ifdef UMBRARY_VERBOSE
                printf("refine to %0.3fsd...\n", bin_width);
            #endif /* UMBRARY_VERBOSE */
            
            for (int xy=0; xy<UMBRARY_INPUT_ROWS*UMBRARY_INPUT_COLS; ++xy) {
                int count_accum = bg_bin_count[xy*12];
                if (count_accum*2 > (file_i-1)) {
                    bg_med[xy] =
                        bg_med[xy]
                        - bg_stdev[xy]*(bin_width*5)
                    ;
                } else {
                    int keep_going = 1;
                    for(int ii=1; ii<11 && keep_going; ++ii) {
                        count_accum += bg_bin_count[xy*12+ii];
                        if (count_accum*2 > (file_i-1)) {
                            bg_med[xy] =
                                bg_med[xy]
                                + bg_stdev[xy]*(ii*bin_width-(bin_width*5.5))
                            ;
                            keep_going = 0;
                        }
                    }
                    if (keep_going) {
                        bg_med[xy] =
                            bg_med[xy]
                            + bg_stdev[xy]*(bin_width*5)
                        ;
                    }
                }
                
                /*
                if (xy % 10000 == 0) {
                    printf(
                        "%lld+/-%5.1f ==> %d [%d;%d..%d;%d..%d;%d]\n",
                        bg_sum[xy],
                        bg_stdev[xy],
                        bg_med[xy],
                        bg_bin_count[xy*12],
                        bg_bin_count[xy*12+1],
                        bg_bin_count[xy*12+5],
                        bg_bin_count[xy*12+6],
                        bg_bin_count[xy*12+10],
                        bg_bin_count[xy*12+11]
                    );
                }
                */
            }
        } else {
            for (int xy=0; xy<img->pixel_array_size/3; ++xy) {
                int intensity = (
                    img->pixel_array[xy*3+0]
                    + img->pixel_array[xy*3+1]
                    + img->pixel_array[xy*3+2]
                );
                
                if (intensity-bg_med[xy] < -bg_stdev[xy]*(bin_width*5)) {
                    bg_bin_count[xy*12] += 1;
                } else if (intensity-bg_med[xy] > bg_stdev[xy]*(bin_width*5)) {
                    bg_bin_count[xy*12+11] += 1;
                } else {
                    bg_bin_count[
                        xy*12
                        + (int)(
                            (intensity-bg_med[xy])
                            / bg_stdev[xy]
                            / bin_width
                            + 6
                        )
                    ] += 1;
                }
            }
            
            free_image(img);
        }
    }
}
void umbrary_write_medians_frame(const char* filename) {
    img = umbrary_load_bmp(1);
    
    for (int xy=0; xy<img->pixel_array_size/3; ++xy) {
        img->pixel_array[xy*3+0] = (bg_med[xy]+0)/3;
        img->pixel_array[xy*3+1] = (bg_med[xy]+1)/3;
        img->pixel_array[xy*3+2] = (bg_med[xy]+2)/3;
    }
    
    write_image(img, filename);
    
    free_image(img);
}

void umbrary_init(const char* filename_format_new) {
    if (strlen(filename_format_new) > 256) {
        fprintf(stderr, "filename format max length 256; was %d.", (int)strlen(filename_format_new));
        exit(EXIT_FAILURE);
    }
    
    filename_format = filename_format_new;
    img = umbrary_load_bmp(1);
    
    if (img == NULL) {
        fprintf(stderr, "%s: %s[%d]\n", strerror(errno), filename_format, 1);
        exit(EXIT_FAILURE);
    }
    
    free_image(img);
    
    img = load_bmp("var/medians3.bmp");
    
    if (img) {
        #ifdef UMBRARY_VERBOSE
            printf("load var/medians3...\n");
        #endif /* UMBRARY_VERBOSE */
        
        for (int xy=0; xy<img->pixel_array_size/3; ++xy) {
            int intensity = (
                img->pixel_array[xy*3+0]
                + img->pixel_array[xy*3+1]
                + img->pixel_array[xy*3+2]
            );
            
            bg_sum[xy] = intensity;
            bg_stdev[xy] = 1;
            bg_med[xy] = intensity;
        }
        
        assert(img->width == UMBRARY_INPUT_COLS);
        assert(img->height == UMBRARY_INPUT_ROWS);
        
        free_image(img);
    } else {
        umbrary_compute_means();
        umbrary_write_medians_frame("var/means.bmp");
        umbrary_refine_medians(0.2);
        umbrary_write_medians_frame("var/medians1.bmp");
        umbrary_refine_medians(0.02);
        umbrary_write_medians_frame("var/medians2.bmp");
        umbrary_refine_medians(0.002);
        umbrary_write_medians_frame("var/medians3.bmp");
    }
    
    gettimeofday(&start, NULL);
}

void umbrary_sample_frame(int file_i, const char* filename) {
    img = umbrary_load_bmp(file_i);
    if (img == NULL) {
        fprintf(stderr, "%s: %s[%d]\n", strerror(errno), filename_format, file_i);
        exit(EXIT_FAILURE);
    }
    
    /* // native resolution
    for (int xy=0; xy<img->pixel_array_size/3; ++xy) {
        int px_intensity = 
            img->pixel_array[xy*3+0]
            + img->pixel_array[xy*3+1]
            + img->pixel_array[xy*3+2]
        ;
        if (px_intensity > bg_med[xy] + 30) {
            img->pixel_array[xy*3+0] = 0x2F;
            img->pixel_array[xy*3+1] = 0x96;
            img->pixel_array[xy*3+2] = 0xDF;
        } else if (px_intensity < bg_med[xy] - 30) {
            img->pixel_array[xy*3+0] = 0xFF;
            img->pixel_array[xy*3+1] = 0x8B;
            img->pixel_array[xy*3+2] = 0x38;
        } else {
            //pass
        }
    }
    */
    
    // downsample by UMBRARY_PIXEL_WIDTH
    for (int xy=0; xy<UMBRARY_INPUT_ROWS*UMBRARY_INPUT_COLS; ++xy) {
        if (
            (xy%UMBRARY_INPUT_COLS)%UMBRARY_PIXEL_WIDTH == 0
            && (xy/UMBRARY_INPUT_COLS)%UMBRARY_PIXEL_WIDTH == 0
        ) {
            int hi = 0;
            int lo = 0;
            
            for (int xi=0; xi<UMBRARY_PIXEL_WIDTH && xy%UMBRARY_INPUT_COLS+xi<UMBRARY_INPUT_COLS; ++xi) {
                for (int yi=0; yi<UMBRARY_PIXEL_WIDTH && xy/UMBRARY_INPUT_COLS+yi<UMBRARY_INPUT_ROWS; ++yi) {
                    int xyi = xy + yi*UMBRARY_INPUT_COLS + xi;
                    int intensity =
                        img->pixel_array[xyi*3+0]
                        + img->pixel_array[xyi*3+1]
                        + img->pixel_array[xyi*3+2]
                    ;
                    int med = bg_med[xyi];
                    
                    if (intensity > med + 30) {
                        hi += 1;
                    }
                    
                    if (intensity < med - 30) {
                        lo += 1;
                    }
                }
            }
            
            for (int xi=0; xi<UMBRARY_PIXEL_WIDTH && xy%UMBRARY_INPUT_COLS+xi<UMBRARY_INPUT_COLS; ++xi) {
                for (int yi=0; yi<UMBRARY_PIXEL_WIDTH && xy/UMBRARY_INPUT_COLS+yi<UMBRARY_INPUT_ROWS; ++yi) {
                    int xyi = xy + yi*UMBRARY_INPUT_COLS + xi;
                    if (hi>0 && hi>lo) {
                        img->pixel_array[xyi*3+0] = 0x2F;
                        img->pixel_array[xyi*3+1] = 0x96;
                        img->pixel_array[xyi*3+2] = 0xDF;
                    } else if (lo>0 && lo>hi) {
                        img->pixel_array[xyi*3+0] = 0xFF;
                        img->pixel_array[xyi*3+1] = 0x8B;
                        img->pixel_array[xyi*3+2] = 0x38;
                    } else {
                        //pass
                    }
                }
            }
        }
    }
    
    write_image(img, filename);
    
    free_image(img);
}

void umbrary_update(int usec) {
    int file_i;
    if (usec == 0) {
        file_i = 1 + umbrary_usec_elapsed() / 66667;
    } else {
        file_i = 1 + usec / 66667;
    }
    img = umbrary_load_bmp(file_i);
    if (img == NULL) {
        fprintf(stderr, "%s: %s[%d]\n", strerror(errno), filename_format, file_i);
        exit(EXIT_FAILURE);
    }
    
    for (int xy=0; xy<UMBRARY_INPUT_ROWS*UMBRARY_INPUT_COLS; ++xy) {
        if (
            (xy%UMBRARY_INPUT_COLS)%UMBRARY_PIXEL_WIDTH == 0
            && (xy/UMBRARY_INPUT_COLS)%UMBRARY_PIXEL_WIDTH == 0
        ) {
            int hi = 0;
            int lo = 0;
            
            for (int xi=0; xi<UMBRARY_PIXEL_WIDTH && xy%UMBRARY_INPUT_COLS+xi<UMBRARY_INPUT_COLS; ++xi) {
                for (int yi=0; yi<UMBRARY_PIXEL_WIDTH && xy/UMBRARY_INPUT_COLS+yi<UMBRARY_INPUT_ROWS; ++yi) {
                    int xyi = xy + yi*UMBRARY_INPUT_COLS + xi;
                    int intensity =
                        img->pixel_array[xyi*3+0]
                        + img->pixel_array[xyi*3+1]
                        + img->pixel_array[xyi*3+2]
                    ;
                    int med = bg_med[xyi];
                    
                    if (intensity > med + 30) {
                        hi += 1;
                    }
                    
                    if (intensity < med - 30) {
                        lo += 1;
                    }
                }
            }
            
            umbrary_level[
                (xy/UMBRARY_INPUT_COLS)/UMBRARY_PIXEL_WIDTH * UMBRARY_OUTPUT_COLS
                + (xy%UMBRARY_INPUT_COLS)/UMBRARY_PIXEL_WIDTH
            ] =
              hi>0 && hi>lo ? 1
            : lo>0 && lo>hi ? -1
            : 0
            ;
        }
    }
    
    free_image(img);
}

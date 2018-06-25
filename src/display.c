#include <stdlib.h>

#include "display.h"

#include "constants.h"
#include "gifenc.h"
#include "pp-server-luminary.h"

int display_current[ROWS * COLS];
ge_GIF *gif;
char gif_palette[128 * 3];

void display_init_color(int id, int xterm, char r, char g, char b) {
    init_pair(id+1, xterm, xterm);
    
    #ifdef OUTPUT_GIF
    gif_palette[id * 3 + 0] = r;
    gif_palette[id * 3 + 1] = g;
    gif_palette[id * 3 + 2] = b;
    #endif /* OUTPUT_GIF */
}

void display_init() {
    for (int xy = 0; xy < ROWS * COLS; ++xy) {
        display_current[xy] = -1;
    }
    
    // ncurses initialization
    initscr();
    raw();
    cbreak();
    timeout(10);
    noecho();
    curs_set(0);
    
    if (!has_colors()) {
        endwin();
		printf("Your terminal does not support color\n");
		exit(1);
	}
    if (!can_change_color()) {
        endwin();
		printf("Your terminal does not support changing colors\n");
		exit(1);
	}
	start_color();
	
	for (int ii = 0; ii < 128 * 3; ++ii) {
	    gif_palette[ii] = 0x00;
	}
    
    display_init_color( 0, RAINBOW_00, 0x6d, 0x3f, 0xa9);
    display_init_color( 1, RAINBOW_01, 0xb1, 0x3c, 0xb1);
    display_init_color( 2, RAINBOW_02, 0xed, 0x43, 0x95);
    display_init_color( 3, RAINBOW_03, 0xff, 0x5d, 0x63);
    display_init_color( 4, RAINBOW_04, 0xff, 0x8b, 0x38);
    display_init_color( 5, RAINBOW_05, 0xd8, 0xc1, 0x31);
    display_init_color( 6, RAINBOW_06, 0xaf, 0xef, 0x5a);
    display_init_color( 7, RAINBOW_07, 0x60, 0xf6, 0x60);
    display_init_color( 8, RAINBOW_08, 0x28, 0xea, 0x8c);
    display_init_color( 9, RAINBOW_09, 0x19, 0xc7, 0xc1);
    display_init_color(10, RAINBOW_10, 0x2f, 0x96, 0xdf);
    display_init_color(11, RAINBOW_11, 0x53, 0x65, 0xd6);
    display_init_color(12, RAINBOW_00, 0x63, 0x3f, 0xa9);
    
    display_init_color( 0+MAKE_DARKER, RAINBOW_40, 0x38, 0x27, 0x79);
    display_init_color( 1+MAKE_DARKER, RAINBOW_41, 0x57, 0x28, 0x87);
    display_init_color( 2+MAKE_DARKER, RAINBOW_42, 0x76, 0x2b, 0x79);
    display_init_color( 3+MAKE_DARKER, RAINBOW_43, 0x8b, 0x36, 0x57);
    display_init_color( 4+MAKE_DARKER, RAINBOW_44, 0x8d, 0x4c, 0x30);
    display_init_color( 5+MAKE_DARKER, RAINBOW_45, 0x7a, 0x6b, 0x11);
    display_init_color( 6+MAKE_DARKER, RAINBOW_46, 0x57, 0x8e, 0x16);
    display_init_color( 7+MAKE_DARKER, RAINBOW_47, 0x2a, 0x8e, 0x43);
    display_init_color( 8+MAKE_DARKER, RAINBOW_48, 0x15, 0x81, 0x77);
    display_init_color( 9+MAKE_DARKER, RAINBOW_49, 0x15, 0x6a, 0x67);
    display_init_color(10+MAKE_DARKER, RAINBOW_50, 0x22, 0x50, 0x70);
    display_init_color(11+MAKE_DARKER, RAINBOW_51, 0x31, 0x38, 0x66);
    display_init_color(12+MAKE_DARKER, RAINBOW_40, 0x38, 0x27, 0x79);
    
    //display_init_color(15, 0, 0x00, 0x00, 0x00);
    
    display_init_color(-1+MAKE_GREY, GREY_0, 0x00, 0x00, 0x00);
    display_init_color( 0+MAKE_GREY, GREY_6, 0x00, 0x00, 0x00);
    display_init_color( 1+MAKE_GREY, GREY_5, 0x00, 0x00, 0x00);
    display_init_color( 2+MAKE_GREY, GREY_4, 0x00, 0x00, 0x00);
    display_init_color( 3+MAKE_GREY, GREY_3, 0x00, 0x00, 0x00);
    display_init_color( 4+MAKE_GREY, GREY_2, 0x00, 0x00, 0x00);
    display_init_color( 5+MAKE_GREY, GREY_1, 0x00, 0x00, 0x00);
    display_init_color( 6+MAKE_GREY, GREY_0, 0x00, 0x00, 0x00);
    display_init_color( 7+MAKE_GREY, GREY_1, 0x00, 0x00, 0x00);
    display_init_color( 8+MAKE_GREY, GREY_2, 0x00, 0x00, 0x00);
    display_init_color( 9+MAKE_GREY, GREY_3, 0x00, 0x00, 0x00);
    display_init_color(10+MAKE_GREY, GREY_4, 0x00, 0x00, 0x00);
    display_init_color(11+MAKE_GREY, GREY_5, 0x00, 0x00, 0x00);
    display_init_color(12+MAKE_GREY, GREY_6, 0x00, 0x00, 0x00);
    
    display_init_color(-1+MAKE_GREY+MAKE_DARKER, GREY_40, 0x00, 0x00, 0x00);
    display_init_color( 0+MAKE_GREY+MAKE_DARKER, GREY_46, 0x00, 0x00, 0x00);
    display_init_color( 1+MAKE_GREY+MAKE_DARKER, GREY_45, 0x00, 0x00, 0x00);
    display_init_color( 2+MAKE_GREY+MAKE_DARKER, GREY_44, 0x00, 0x00, 0x00);
    display_init_color( 3+MAKE_GREY+MAKE_DARKER, GREY_43, 0x00, 0x00, 0x00);
    display_init_color( 4+MAKE_GREY+MAKE_DARKER, GREY_42, 0x00, 0x00, 0x00);
    display_init_color( 5+MAKE_GREY+MAKE_DARKER, GREY_41, 0x00, 0x00, 0x00);
    display_init_color( 6+MAKE_GREY+MAKE_DARKER, GREY_40, 0x00, 0x00, 0x00);
    display_init_color( 7+MAKE_GREY+MAKE_DARKER, GREY_41, 0x00, 0x00, 0x00);
    display_init_color( 8+MAKE_GREY+MAKE_DARKER, GREY_42, 0x00, 0x00, 0x00);
    display_init_color( 9+MAKE_GREY+MAKE_DARKER, GREY_43, 0x00, 0x00, 0x00);
    display_init_color(10+MAKE_GREY+MAKE_DARKER, GREY_44, 0x00, 0x00, 0x00);
    display_init_color(11+MAKE_GREY+MAKE_DARKER, GREY_45, 0x00, 0x00, 0x00);
    display_init_color(12+MAKE_GREY+MAKE_DARKER, GREY_46, 0x00, 0x00, 0x00);
    
    #ifdef OUTPUT_GIF
    gif = ge_new_gif(
        "demo/example2.gif",
        COLS * GIF_ZOOM, ROWS * GIF_ZOOM,
        gif_palette,
        7,              /* palette depth == log2(# of colors) */
        0               /* infinite loop */
    );
    #endif /* OUTPUT_GIF */
    
    pp_server_start();
    pp_server_shutdown();
    
    // CR rrheingans-yoo for ntarleton: dancefloor initialization, as necessary
}

void display_color(int xy, int color) {
    int x = xy % COLS;
    int y = xy / COLS;
    if (display_current[xy] != color) {
        // ncurses drawing
        if (y % DIAGNOSTIC_SAMPLING_RATE == 0
            && x % DIAGNOSTIC_SAMPLING_RATE == 0
            && (y < PETAL_ROWS || x < FLOOR_COLS)) {
            attron(COLOR_PAIR(1+color));
            mvprintw(
                xy/COLS/DIAGNOSTIC_SAMPLING_RATE,
                2*(xy%COLS)/DIAGNOSTIC_SAMPLING_RATE,
                " ."
            );
            attroff(COLOR_PAIR(1+color));
        }
        display_current[xy] = color;
        
        // CR rrheingans-yoo for ntarleton: get ready to set cell xy to color color
    } else {
        if (
            y % DIAGNOSTIC_SAMPLING_RATE == 0
            && x % DIAGNOSTIC_SAMPLING_RATE == 0
            && (y < PETAL_ROWS || x < FLOOR_COLS)
            && (rand() % 100 == 0
                || xy == COLS * (ROWS-1) + FLOOR_COLS - 1
            )
        ) {
            attron(COLOR_PAIR(1+color));
            mvprintw(
                xy/COLS/DIAGNOSTIC_SAMPLING_RATE,
                2*(xy%COLS)/DIAGNOSTIC_SAMPLING_RATE,
                " ,"
            );
            attroff(COLOR_PAIR(1+color));
        }
    }
}

void display_flush(int epoch) {
    // ncurses flush
    refresh();
    
    #ifdef OUTPUT_GIF
    if (
        epoch < INITIALIZATION_EPOCHS + GIF_EPOCHS
        && epoch % WILDFIRE_SPEEDUP == 0
    ) {
        for (int xy = 0; xy < ROWS * COLS; ++xy) {
            int x = xy % COLS;
            int y = xy / COLS;
            for (int xi = 0; xi < GIF_ZOOM; ++xi) {
                for (int yi = 0; yi < GIF_ZOOM; ++yi) {
                    gif->frame[y*COLS*GIF_ZOOM*GIF_ZOOM + yi*COLS*GIF_ZOOM + x*GIF_ZOOM + xi] = (char)display_current[xy];
                }
            }
        }
        
        ge_add_frame(gif, 10);
    }
    
    if (epoch == INITIALIZATION_EPOCHS + GIF_EPOCHS) {
        ge_close_gif(gif);
    }
    #endif /* OUTPUT_GIF */
    
    // CR rrheingans-yoo for ntarleton: set all cell colors at once
}

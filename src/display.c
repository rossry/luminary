#include <stdlib.h>

#include "display.h"

#include "constants.h"

int display_current[ROWS * COLS];

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
    
    init_pair( 1, RAINBOW_00, RAINBOW_00);
    init_pair( 2, RAINBOW_01, RAINBOW_01);
    init_pair( 3, RAINBOW_02, RAINBOW_02);
    init_pair( 4, RAINBOW_03, RAINBOW_03);
    init_pair( 5, RAINBOW_04, RAINBOW_04);
    init_pair( 6, RAINBOW_05, RAINBOW_05);
    init_pair( 7, RAINBOW_06, RAINBOW_06);
    init_pair( 8, RAINBOW_07, RAINBOW_07);
    init_pair( 9, RAINBOW_08, RAINBOW_08);
    init_pair(10, RAINBOW_09, RAINBOW_09);
    init_pair(11, RAINBOW_10, RAINBOW_10);
    init_pair(12, RAINBOW_11, RAINBOW_11);
    
    init_pair( 1+MAKE_DARKER, RAINBOW_40, RAINBOW_40);
    init_pair( 2+MAKE_DARKER, RAINBOW_41, RAINBOW_41);
    init_pair( 3+MAKE_DARKER, RAINBOW_42, RAINBOW_42);
    init_pair( 4+MAKE_DARKER, RAINBOW_43, RAINBOW_43);
    init_pair( 5+MAKE_DARKER, RAINBOW_44, RAINBOW_44);
    init_pair( 6+MAKE_DARKER, RAINBOW_45, RAINBOW_45);
    init_pair( 7+MAKE_DARKER, RAINBOW_46, RAINBOW_46);
    init_pair( 8+MAKE_DARKER, RAINBOW_47, RAINBOW_47);
    init_pair( 9+MAKE_DARKER, RAINBOW_48, RAINBOW_48);
    init_pair(10+MAKE_DARKER, RAINBOW_49, RAINBOW_49);
    init_pair(11+MAKE_DARKER, RAINBOW_50, RAINBOW_50);
    init_pair(12+MAKE_DARKER, RAINBOW_51, RAINBOW_51);
    
    init_pair(16, 0, 0);
    
    init_pair( 0+MAKE_GREY, GREY_0, GREY_0);
    init_pair( 1+MAKE_GREY, GREY_6, GREY_6);
    init_pair( 2+MAKE_GREY, GREY_5, GREY_5);
    init_pair( 3+MAKE_GREY, GREY_4, GREY_4);
    init_pair( 4+MAKE_GREY, GREY_3, GREY_3);
    init_pair( 5+MAKE_GREY, GREY_2, GREY_2);
    init_pair( 6+MAKE_GREY, GREY_1, GREY_1);
    init_pair( 7+MAKE_GREY, GREY_0, GREY_0);
    init_pair( 8+MAKE_GREY, GREY_1, GREY_1);
    init_pair( 9+MAKE_GREY, GREY_2, GREY_2);
    init_pair(10+MAKE_GREY, GREY_3, GREY_3);
    init_pair(11+MAKE_GREY, GREY_4, GREY_4);
    init_pair(12+MAKE_GREY, GREY_5, GREY_5);
    init_pair(13+MAKE_GREY, GREY_6, GREY_6);
    
    init_pair( 0+MAKE_GREY+MAKE_DARKER, GREY_40, GREY_40);
    init_pair( 1+MAKE_GREY+MAKE_DARKER, GREY_46, GREY_46);
    init_pair( 2+MAKE_GREY+MAKE_DARKER, GREY_45, GREY_45);
    init_pair( 3+MAKE_GREY+MAKE_DARKER, GREY_44, GREY_44);
    init_pair( 4+MAKE_GREY+MAKE_DARKER, GREY_43, GREY_43);
    init_pair( 5+MAKE_GREY+MAKE_DARKER, GREY_42, GREY_42);
    init_pair( 6+MAKE_GREY+MAKE_DARKER, GREY_41, GREY_41);
    init_pair( 7+MAKE_GREY+MAKE_DARKER, GREY_40, GREY_40);
    init_pair( 8+MAKE_GREY+MAKE_DARKER, GREY_41, GREY_41);
    init_pair( 9+MAKE_GREY+MAKE_DARKER, GREY_42, GREY_42);
    init_pair(10+MAKE_GREY+MAKE_DARKER, GREY_43, GREY_43);
    init_pair(11+MAKE_GREY+MAKE_DARKER, GREY_44, GREY_44);
    init_pair(12+MAKE_GREY+MAKE_DARKER, GREY_45, GREY_45);
    init_pair(13+MAKE_GREY+MAKE_DARKER, GREY_46, GREY_46);
    
    // CR rrheingans-yoo for ntarleton: dancefloor initialization, as necessary
}

void display_color(int xy, int color) {
    if (display_current[xy] != color) {
        // ncurses drawing
        int x = xy % COLS;
        int y = xy / COLS;
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
            display_current[xy] = color;
        }
        
        // CR rrheingans-yoo for ntarleton: get ready to set cell xy to color color
        //
        // note that the actual grid should use the RGB values given at
        // http://static.rossry.net/lights/v0.5.30/colors.html -- the xterm
        // colors used for ncurses here are approximations
    } else {
        if (rand() % 100 == 0 || xy == ROWS * COLS - 1) {
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

void display_flush() {
    // ncurses flush
    refresh();
    
    // CR rrheingans-yoo for ntarleton: set all cell colors at once
}

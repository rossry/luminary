#include <stdlib.h>
#include <cairo.h>
#include <cairo-xlib.h>

#include "display.h"

#include "constants.h"
#include "gifenc.h"
#include "pp-server-luminary.h"

int display_current[ROWS * COLS];
int petal_mapping[] = PETAL_MAPPING;

// gifenc
ge_GIF *gif;
uint8_t gif_palette[128 * 3];

#ifdef OUTPUT_CAIRO
// cairo
cairo_surface_t *cairo_surface;
cairo_t *cairo_cr;
cairo_surface_t *cairo_blur;
cairo_t *cairo_blur_cr;

Display *cairo_x_display;
Window cairo_x_window;
Visual *cairo_x_visual;

void cairo_set_source_luminary(int id) {
    cairo_set_source_rgb(
        cairo_cr,
        (uint8_t)gif_palette[id * 3 + 0] / 255.0,
        (uint8_t)gif_palette[id * 3 + 1] / 255.0,
        (uint8_t)gif_palette[id * 3 + 2] / 255.0
    );
}
#endif /* OUTPUT_CAIRO */

void display_init_color(int id, int xterm, uint8_t r, uint8_t g, uint8_t b) {
    init_pair(id+1, xterm, xterm);
    
    //#ifdef OUTPUT_GIF
    gif_palette[id * 3 + 0] = r;
    gif_palette[id * 3 + 1] = g;
    gif_palette[id * 3 + 2] = b;
    //#endif /* OUTPUT_GIF */
}

void display_init() {
    for (int xy = 0; xy < ROWS * COLS; ++xy) {
        display_current[xy] = -1 + MAKE_GREY + MAKE_DARKER;
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
    
    display_init_color(15, 16, 0x00, 0x00, 0x00);
    
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
            "demo/example6.gif",
            COLS * GIF_ZOOM, ROWS * GIF_ZOOM,
            gif_palette,
            7,              /* palette depth == log2(# of colors) */
            0               /* infinite loop */
        );
    #endif /* OUTPUT_GIF */
    
    #ifdef OUTPUT_CAIRO
        #ifdef OUTPUT_CAIRO_FULLSCREEN
            cairo_x_display = XOpenDisplay(0);
            XSetWindowAttributes wa;
            wa.override_redirect = True;
            cairo_x_window =
                XCreateWindow(
                    cairo_x_display,
                    DefaultRootWindow(cairo_x_display),
                    0,
                    0,
                    COLS * CAIRO_ZOOM, // width
                    ROWS * CAIRO_ZOOM, // height
                    0,
                    CopyFromParent,
                    CopyFromParent,
                    CopyFromParent,
                    CWBorderPixel|CWColormap|CWEventMask|CWOverrideRedirect,
                    //BlackPixel(cairo_x_display, DefaultScreen(cairo_x_display)),
                    //BlackPixel(cairo_x_display, DefaultScreen(cairo_x_display))
                    &wa
                );
            XMapWindow(cairo_x_display, cairo_x_window);
            cairo_x_visual =
                DefaultVisual(
                    cairo_x_display,
                    DefaultScreen(cairo_x_display)
                );
            cairo_surface =
                cairo_xlib_surface_create(
                    cairo_x_display,
                    cairo_x_window,
                    cairo_x_visual,
                    COLS * CAIRO_ZOOM,
                    ROWS * CAIRO_ZOOM
                );
        #else /* OUTPUT_CAIRO_FULLSCREEN */
            cairo_surface = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, COLS * CAIRO_ZOOM, ROWS * CAIRO_ZOOM);
        #endif
        cairo_cr = cairo_create(cairo_surface);

        cairo_set_source_rgb(cairo_cr, 0x00, 0x00, 0x00);
        cairo_rectangle(cairo_cr, 0, 0, COLS * CAIRO_ZOOM, ROWS * CAIRO_ZOOM);
        cairo_fill(cairo_cr);
        
        cairo_blur = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, CAIRO_ZOOM + 2*CAIRO_BLUR_WIDTH, CAIRO_ZOOM + 2*CAIRO_BLUR_WIDTH);
        cairo_blur_cr = cairo_create(cairo_blur);
        cairo_set_source_rgba(cairo_blur_cr, 0.0, 0.0, 0.0, 1.0);
        
        for (int xi = 0; xi < CAIRO_ZOOM; ++xi) {
            for (int yi = 0; yi < CAIRO_ZOOM; ++yi) {
                switch (yi*CAIRO_ZOOM + xi) {
                #if CAIRO_ZOOM == 15 && CAIRO_BLUR_WIDTH == 4
                    case 1:
                    case 3:
                    case 5:
                    case 7:
                    case 9:
                    case 11:
                    case 13:
                    //case CAIRO_ZOOM+2:
                    case CAIRO_ZOOM+4:
                    case CAIRO_ZOOM+6:
                    case CAIRO_ZOOM+8:
                    case CAIRO_ZOOM+10:
                    //case CAIRO_ZOOM+12:
                    case 2*CAIRO_ZOOM+1:
                    case 2*CAIRO_ZOOM+3:
                    case 2*CAIRO_ZOOM+5:
                    case 2*CAIRO_ZOOM+7:
                    case 2*CAIRO_ZOOM+9:
                    case 2*CAIRO_ZOOM+11:
                    case 2*CAIRO_ZOOM+13:
                    case 3*CAIRO_ZOOM+4:
                    case 3*CAIRO_ZOOM+6:
                    case 3*CAIRO_ZOOM+8:
                    case 3*CAIRO_ZOOM+10:
                        // up edge
                        cairo_rectangle(cairo_blur_cr,
                            CAIRO_BLUR_WIDTH + xi,
                            CAIRO_ZOOM + CAIRO_BLUR_WIDTH + yi,
                            1, 1
                        );
                        break;
                        
                    case 1*CAIRO_ZOOM:
                    case 3*CAIRO_ZOOM:
                    case 5*CAIRO_ZOOM:
                    case 7*CAIRO_ZOOM:
                    case 9*CAIRO_ZOOM:
                    case 11*CAIRO_ZOOM:
                    case 13*CAIRO_ZOOM:
                    //case 1+2*CAIRO_ZOOM:
                    case 1+4*CAIRO_ZOOM:
                    case 1+6*CAIRO_ZOOM:
                    case 1+8*CAIRO_ZOOM:
                    case 1+10*CAIRO_ZOOM:
                    //case 1+12*CAIRO_ZOOM:
                    case 2+1*CAIRO_ZOOM:
                    case 2+3*CAIRO_ZOOM:
                    case 2+5*CAIRO_ZOOM:
                    case 2+7*CAIRO_ZOOM:
                    case 2+9*CAIRO_ZOOM:
                    case 2+11*CAIRO_ZOOM:
                    case 2+13*CAIRO_ZOOM:
                    case 3+4*CAIRO_ZOOM:
                    case 3+6*CAIRO_ZOOM:
                    case 3+8*CAIRO_ZOOM:
                    case 3+10*CAIRO_ZOOM:
                        // left edge
                        cairo_rectangle(cairo_blur_cr,
                            CAIRO_ZOOM + CAIRO_BLUR_WIDTH + xi,
                            CAIRO_BLUR_WIDTH + yi,
                            1, 1
                        );
                        break;
                        
                    case CAIRO_ZOOM*(CAIRO_ZOOM-1)+1:
                    case CAIRO_ZOOM*(CAIRO_ZOOM-1)+3:
                    case CAIRO_ZOOM*(CAIRO_ZOOM-1)+5:
                    case CAIRO_ZOOM*(CAIRO_ZOOM-1)+7:
                    case CAIRO_ZOOM*(CAIRO_ZOOM-1)+9:
                    case CAIRO_ZOOM*(CAIRO_ZOOM-1)+11:
                    case CAIRO_ZOOM*(CAIRO_ZOOM-1)+13:
                    ///case CAIRO_ZOOM*(CAIRO_ZOOM-2)+2:
                    case CAIRO_ZOOM*(CAIRO_ZOOM-2)+4:
                    case CAIRO_ZOOM*(CAIRO_ZOOM-2)+6:
                    case CAIRO_ZOOM*(CAIRO_ZOOM-2)+8:
                    case CAIRO_ZOOM*(CAIRO_ZOOM-2)+10:
                    //case CAIRO_ZOOM*(CAIRO_ZOOM-2)+12:
                    case CAIRO_ZOOM*(CAIRO_ZOOM-3)+1:
                    case CAIRO_ZOOM*(CAIRO_ZOOM-3)+3:
                    case CAIRO_ZOOM*(CAIRO_ZOOM-3)+5:
                    case CAIRO_ZOOM*(CAIRO_ZOOM-3)+7:
                    case CAIRO_ZOOM*(CAIRO_ZOOM-3)+9:
                    case CAIRO_ZOOM*(CAIRO_ZOOM-3)+11:
                    case CAIRO_ZOOM*(CAIRO_ZOOM-3)+13:
                    case CAIRO_ZOOM*(CAIRO_ZOOM-4)+4:
                    case CAIRO_ZOOM*(CAIRO_ZOOM-4)+6:
                    case CAIRO_ZOOM*(CAIRO_ZOOM-4)+8:
                    case CAIRO_ZOOM*(CAIRO_ZOOM-4)+10:
                        // down edge
                        cairo_rectangle(cairo_blur_cr,
                            CAIRO_BLUR_WIDTH + xi,
                            -CAIRO_ZOOM + CAIRO_BLUR_WIDTH + yi,
                            1, 1
                        );
                        break;
                        
                    case (CAIRO_ZOOM-1)+1*CAIRO_ZOOM:
                    case (CAIRO_ZOOM-1)+3*CAIRO_ZOOM:
                    case (CAIRO_ZOOM-1)+5*CAIRO_ZOOM:
                    case (CAIRO_ZOOM-1)+7*CAIRO_ZOOM:
                    case (CAIRO_ZOOM-1)+9*CAIRO_ZOOM:
                    case (CAIRO_ZOOM-1)+11*CAIRO_ZOOM:
                    case (CAIRO_ZOOM-1)+13*CAIRO_ZOOM:
                    //case (CAIRO_ZOOM-2)+2*CAIRO_ZOOM:
                    case (CAIRO_ZOOM-2)+4*CAIRO_ZOOM:
                    case (CAIRO_ZOOM-2)+6*CAIRO_ZOOM:
                    case (CAIRO_ZOOM-2)+8*CAIRO_ZOOM:
                    case (CAIRO_ZOOM-2)+10*CAIRO_ZOOM:
                    //case (CAIRO_ZOOM-2)+12*CAIRO_ZOOM:
                    case (CAIRO_ZOOM-3)+1*CAIRO_ZOOM:
                    case (CAIRO_ZOOM-3)+3*CAIRO_ZOOM:
                    case (CAIRO_ZOOM-3)+5*CAIRO_ZOOM:
                    case (CAIRO_ZOOM-3)+7*CAIRO_ZOOM:
                    case (CAIRO_ZOOM-3)+9*CAIRO_ZOOM:
                    case (CAIRO_ZOOM-3)+11*CAIRO_ZOOM:
                    case (CAIRO_ZOOM-3)+13*CAIRO_ZOOM:
                    case (CAIRO_ZOOM-4)+4*CAIRO_ZOOM:
                    case (CAIRO_ZOOM-4)+6*CAIRO_ZOOM:
                    case (CAIRO_ZOOM-4)+8*CAIRO_ZOOM:
                    case (CAIRO_ZOOM-4)+10*CAIRO_ZOOM:
                        // right edge
                        cairo_rectangle(cairo_blur_cr,
                            -CAIRO_ZOOM + CAIRO_BLUR_WIDTH + xi,
                            CAIRO_BLUR_WIDTH + yi,
                            1, 1
                        );
                        break;
                #elif CAIRO_ZOOM == 3 /* CAIRO_ZOOM == ? */
                    case 1:
                        cairo_rectangle(cairo_blur_cr,
                            CAIRO_BLUR_WIDTH + xi,
                            CAIRO_ZOOM + CAIRO_BLUR_WIDTH + yi,
                            1, 1
                        );
                        break;
                    case 3:
                        cairo_rectangle(cairo_blur_cr,
                            CAIRO_ZOOM + CAIRO_BLUR_WIDTH + xi,
                            CAIRO_BLUR_WIDTH + yi,
                            1, 1
                        );
                        break;
                    case 7:
                        cairo_rectangle(cairo_blur_cr,
                            -CAIRO_ZOOM + CAIRO_BLUR_WIDTH + xi,
                            CAIRO_BLUR_WIDTH + yi,
                            1, 1
                        );
                        break;
                    case 5:
                        cairo_rectangle(cairo_blur_cr,
                            CAIRO_BLUR_WIDTH + xi,
                            -CAIRO_ZOOM + CAIRO_BLUR_WIDTH + yi,
                            1, 1
                        );
                        break;
                #endif /* CAIRO_ZOOM == ? */
                default:
                    cairo_rectangle(cairo_blur_cr,
                        CAIRO_BLUR_WIDTH + xi,
                        CAIRO_BLUR_WIDTH + yi,
                        1, 1
                    );
                }
            }
        }
        cairo_fill(cairo_blur_cr);
    #endif /* OUTPUT_CAIRO */
    
    pp_server_start(display_current);
    pp_server_shutdown();
    
    // CR rrheingans-yoo for ntarleton: dancefloor initialization, as necessary
}

int petal_mapping_pixel(x_p,y) {
    for (int ii = 0; ii < PETAL_MAPPING_PIXELS; ++ii) {
        if (x_p == petal_mapping[ii * 3] && y == petal_mapping[ii * 3 + 1]) {
            return petal_mapping[ii * 3 + 2];
        }
    }
    return 0;
}

void display_color(int xy, int color) {
    int x = xy % COLS;
    int y = xy / COLS;
    if (display_current[xy] != color
        || rand() % 100 == 100
        || xy == COLS * (ROWS-1) + FLOOR_COLS - 1
    ) {
        // ncurses drawing
        if (y % DIAGNOSTIC_SAMPLING_RATE == 0
            && x % DIAGNOSTIC_SAMPLING_RATE == 0
            && (y < PETAL_ROWS || x < FLOOR_COLS)
            #ifdef DISPLAY_PETALS_MODE
                #ifndef DISPLAY_FLOOR_ALSO
                    && y < PETAL_ROWS
                #endif /* DISPLAY_FLOOR_ALSO */
            #endif /* DISPLAY_PETALS_MODE */
        ) {
            #ifdef DISPLAY_PETALS_MODE
                if (petal_mapping_pixel(x%PETAL_COLS,y)) {
                    attron(COLOR_PAIR(1+color));
                } else if (y > PETAL_ROWS) {
                    attron(COLOR_PAIR(1+color + (color < COLORS ? MAKE_DARKER : 0)));
                } else {
                    attron(COLOR_PAIR(1+15));
                }
                mvprintw(
                    ((y/DIAGNOSTIC_SAMPLING_RATE + (y > PETAL_ROWS ? 8 + PETAL_ROWS : 0)) / (y > PETAL_ROWS ? 2 : 1)),
                    2*x/DIAGNOSTIC_SAMPLING_RATE + ((x / PETAL_COLS) * 6),
                    (display_current[xy] == color ?  " ," : " .")
                );
            #else /* DISPLAY_PETALS_MODE */
                attron(COLOR_PAIR(1+color));
                mvprintw(
                    y/DIAGNOSTIC_SAMPLING_RATE,
                    2*x/DIAGNOSTIC_SAMPLING_RATE
                    ,
                    " ."
                );
            #endif /* DISPLAY_PETALS_MODE */
            attroff(COLOR_PAIR(1+color));
        }

        #ifdef OUTPUT_CAIRO_FULLSCREEN
            cairo_set_source_luminary(color);
            cairo_mask_surface(cairo_cr, cairo_blur, -CAIRO_BLUR_WIDTH + x * CAIRO_ZOOM, -CAIRO_BLUR_WIDTH + y * CAIRO_ZOOM);
        #endif /* OUTPUT_CAIRO_FULLSCREEN */

        display_current[xy] = color;
        
        // CR rrheingans-yoo for ntarleton: get ready to set cell xy to color color
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
                    int my_color;
                    #ifdef GIF_BLUR
                        switch (yi*GIF_ZOOM + xi) {
                        #if GIF_ZOOM == 15 && GIF_BLUR_WIDTH == 4
                            case 1:
                            case 3:
                            case 5:
                            case 7:
                            case 9:
                            case 11:
                            case 13:
                            //case GIF_ZOOM+2:
                            case GIF_ZOOM+4:
                            case GIF_ZOOM+6:
                            case GIF_ZOOM+8:
                            case GIF_ZOOM+10:
                            //case GIF_ZOOM+12:
                            case 2*GIF_ZOOM+1:
                            case 2*GIF_ZOOM+3:
                            case 2*GIF_ZOOM+5:
                            case 2*GIF_ZOOM+7:
                            case 2*GIF_ZOOM+9:
                            case 2*GIF_ZOOM+11:
                            case 2*GIF_ZOOM+13:
                            case 3*GIF_ZOOM+4:
                            case 3*GIF_ZOOM+6:
                            case 3*GIF_ZOOM+8:
                            case 3*GIF_ZOOM+10:
                                // up edge
                                my_color = display_current[xy-COLS];
                                break;
                                
                            case 1*GIF_ZOOM:
                            case 3*GIF_ZOOM:
                            case 5*GIF_ZOOM:
                            case 7*GIF_ZOOM:
                            case 9*GIF_ZOOM:
                            case 11*GIF_ZOOM:
                            case 13*GIF_ZOOM:
                            //case 1+2*GIF_ZOOM:
                            case 1+4*GIF_ZOOM:
                            case 1+6*GIF_ZOOM:
                            case 1+8*GIF_ZOOM:
                            case 1+10*GIF_ZOOM:
                            //case 1+12*GIF_ZOOM:
                            case 2+1*GIF_ZOOM:
                            case 2+3*GIF_ZOOM:
                            case 2+5*GIF_ZOOM:
                            case 2+7*GIF_ZOOM:
                            case 2+9*GIF_ZOOM:
                            case 2+11*GIF_ZOOM:
                            case 2+13*GIF_ZOOM:
                            case 3+4*GIF_ZOOM:
                            case 3+6*GIF_ZOOM:
                            case 3+8*GIF_ZOOM:
                            case 3+10*GIF_ZOOM:
                                // left edge
                                my_color = display_current[xy-1];
                                break;
                                
                            case GIF_ZOOM*(GIF_ZOOM-1)+1:
                            case GIF_ZOOM*(GIF_ZOOM-1)+3:
                            case GIF_ZOOM*(GIF_ZOOM-1)+5:
                            case GIF_ZOOM*(GIF_ZOOM-1)+7:
                            case GIF_ZOOM*(GIF_ZOOM-1)+9:
                            case GIF_ZOOM*(GIF_ZOOM-1)+11:
                            case GIF_ZOOM*(GIF_ZOOM-1)+13:
                            ///case GIF_ZOOM*(GIF_ZOOM-2)+2:
                            case GIF_ZOOM*(GIF_ZOOM-2)+4:
                            case GIF_ZOOM*(GIF_ZOOM-2)+6:
                            case GIF_ZOOM*(GIF_ZOOM-2)+8:
                            case GIF_ZOOM*(GIF_ZOOM-2)+10:
                            //case GIF_ZOOM*(GIF_ZOOM-2)+12:
                            case GIF_ZOOM*(GIF_ZOOM-3)+1:
                            case GIF_ZOOM*(GIF_ZOOM-3)+3:
                            case GIF_ZOOM*(GIF_ZOOM-3)+5:
                            case GIF_ZOOM*(GIF_ZOOM-3)+7:
                            case GIF_ZOOM*(GIF_ZOOM-3)+9:
                            case GIF_ZOOM*(GIF_ZOOM-3)+11:
                            case GIF_ZOOM*(GIF_ZOOM-3)+13:
                            case GIF_ZOOM*(GIF_ZOOM-4)+4:
                            case GIF_ZOOM*(GIF_ZOOM-4)+6:
                            case GIF_ZOOM*(GIF_ZOOM-4)+8:
                            case GIF_ZOOM*(GIF_ZOOM-4)+10:
                                // down edge
                                my_color = display_current[xy+COLS];
                                break;
                                
                            case (GIF_ZOOM-1)+1*GIF_ZOOM:
                            case (GIF_ZOOM-1)+3*GIF_ZOOM:
                            case (GIF_ZOOM-1)+5*GIF_ZOOM:
                            case (GIF_ZOOM-1)+7*GIF_ZOOM:
                            case (GIF_ZOOM-1)+9*GIF_ZOOM:
                            case (GIF_ZOOM-1)+11*GIF_ZOOM:
                            case (GIF_ZOOM-1)+13*GIF_ZOOM:
                            //case (GIF_ZOOM-2)+2*GIF_ZOOM:
                            case (GIF_ZOOM-2)+4*GIF_ZOOM:
                            case (GIF_ZOOM-2)+6*GIF_ZOOM:
                            case (GIF_ZOOM-2)+8*GIF_ZOOM:
                            case (GIF_ZOOM-2)+10*GIF_ZOOM:
                            //case (GIF_ZOOM-2)+12*GIF_ZOOM:
                            case (GIF_ZOOM-3)+1*GIF_ZOOM:
                            case (GIF_ZOOM-3)+3*GIF_ZOOM:
                            case (GIF_ZOOM-3)+5*GIF_ZOOM:
                            case (GIF_ZOOM-3)+7*GIF_ZOOM:
                            case (GIF_ZOOM-3)+9*GIF_ZOOM:
                            case (GIF_ZOOM-3)+11*GIF_ZOOM:
                            case (GIF_ZOOM-3)+13*GIF_ZOOM:
                            case (GIF_ZOOM-4)+4*GIF_ZOOM:
                            case (GIF_ZOOM-4)+6*GIF_ZOOM:
                            case (GIF_ZOOM-4)+8*GIF_ZOOM:
                            case (GIF_ZOOM-4)+10*GIF_ZOOM:
                                // right edge
                                my_color = display_current[xy+1];
                                break;
                                
                        #elif GIF_ZOOM == 3 /* GIF_ZOOM == ? */
                            case 1:
                                my_color = display_current[xy-COLS];
                                break;
                            case 3:
                                my_color = display_current[xy-1];
                                break;
                            case 7:
                                my_color = display_current[xy+1];
                                break;
                            case 5:
                                my_color = display_current[xy+COLS];
                                break;
                        #endif /* GIF_ZOOM == ? */
                        default:
                            my_color = display_current[xy];
                        }
                    #else /* GIF_BLUR */
                        my_color = display_current[xy];
                    #endif /* GIF_BLUR */
                    
                    gif->frame[y*COLS*GIF_ZOOM*GIF_ZOOM + yi*COLS*GIF_ZOOM + x*GIF_ZOOM + xi] = (uint8_t)my_color;
                }
            }
        }
        
        ge_add_frame(gif, 10);
    }
    
    if (epoch == INITIALIZATION_EPOCHS + GIF_EPOCHS) {
        ge_close_gif(gif);
        mvprintw(DIAGNOSTIC_ROWS+5, 1, "wrote gif (%d frames)", epoch);
    }
    #endif /* OUTPUT_GIF */
    
    #ifdef OUTPUT_CAIRO
        #ifdef OUTPUT_CAIRO_FULLSCREEN
            // pass
        #else /* OUTPUT_CAIRO_FULLSCREEN */
            if (epoch == CAIRO_SNAPSHOT_EPOCH) {
                for (int xy = 0; xy < ROWS * COLS; ++xy) {
                    int x = xy % COLS;
                    int y = xy / COLS;
                    cairo_set_source_luminary(display_current[xy]);
                    cairo_mask_surface(cairo_cr, cairo_blur, -CAIRO_BLUR_WIDTH + x * CAIRO_ZOOM, -CAIRO_BLUR_WIDTH + y * CAIRO_ZOOM);
                }
                
                cairo_destroy(cairo_cr);
                cairo_surface_write_to_png(cairo_surface, "demo/cairo.png");
                cairo_surface_destroy(cairo_surface);
                
                mvprintw(DIAGNOSTIC_ROWS+4, 1, "wrote cairo (%d frames)", epoch);
            }
        #endif /* OUTPUT_CAIRO_FULLSCREEN */
    #endif /* OUTPUT_CAIRO */
    
    // CR rrheingans-yoo for ntarleton: set all cell colors at once
}

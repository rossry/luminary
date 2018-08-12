#ifndef DISPLAY_H
#define DISPLAY_H

void print_sacn_message(char *message, int y);

void display_init();
void display_color(int xy, int color);
void display_light(int id, int color);
void display_flush(int epoch);

#endif /* DISPLAY_H */

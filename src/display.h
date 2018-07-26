#ifndef DISPLAY_H
#define DISPLAY_H

void display_init();
void display_color(int xy, int color);
void display_light(int id, int color);
void display_flush(int epoch);

#endif /* DISPLAY_H */

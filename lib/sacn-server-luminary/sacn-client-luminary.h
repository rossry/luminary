#ifndef SACN_CLIENT_LUMINARY_H
#define SACN_CLIENT_LUMINARY_H

#ifdef SACN_CLIENT

#include <stdint.h>

void sacn_client_init();
void sacn_draw_color(int logical_pixel, uint8_t r, uint8_t g, uint8_t b);
void sacn_flush();

#endif /* SACN_CLIENT */

#endif /* SACN_CLIENT_LUMINARY_H */

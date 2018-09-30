#ifndef SACN_SERVER_LUMINARY_H
#define SACN_SERVER_LUMINARY_H

#ifdef SACN_SERVER

#include <stdint.h>

typedef struct sacn_channels_petal_t {
    uint8_t intensity;
    uint8_t color;
    uint8_t pattern;
    uint8_t transition;
} sacn_channels_petal_t;

typedef struct sacn_channels_raw {
    uint8_t               mode;
    sacn_channels_petal_t m;
    sacn_channels_petal_t p[5];
} sacn_channels_raw_t;

typedef struct sacn_channels {
    sacn_channels_raw_t raw;
    sacn_channels_raw_t logical;
} sacn_channels_t;

#define SACN_CONTROL(sacn_channels) ((sacn_channels).logical.mode > 0)
//#define SACN_CONTROL(sacn_channels) 1

int sacn_server_get_port();

void sacn_server_start();
int sacn_server_poll(sacn_channels_t *sacn_channels);
void sacn_server_shutdown();

#endif /* SACN_SERVER */

#endif /* SACN_SERVER_LUMINARY_H */
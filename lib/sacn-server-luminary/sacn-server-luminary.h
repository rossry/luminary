#ifndef SACN_SERVER_LUMINARY_H
#define SACN_SERVER_LUMINARY_H

#include <stdint.h>

typedef struct sacn_channels_raw {
    uint8_t m_mode;
    uint8_t m_intensity;
    uint8_t m_color;
    uint8_t m_pattern;
} sacn_channels_raw_t;

typedef struct sacn_channels {
    sacn_channels_raw_t raw;
    sacn_channels_raw_t logical;
} sacn_channels_t;

#define SACN_CONTROL(sacn_channels) ((sacn_channels).logical.m_mode > 0)

int sacn_server_get_port();

void sacn_server_start();
int sacn_server_poll(sacn_channels_t *sacn_channels);
void sacn_server_shutdown();

#endif /* SACN_SERVER_LUMINARY_H */
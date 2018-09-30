#ifdef SACN_CLIENT

#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include <err.h>

#include "sacn-client-luminary.h"

#include "e131.h"
#include "display.h"
#include "sacn-constants-luminary.h"

#define LUMINARY_SACN_CLIENT_UNIVERSES 5

int sockfd[LUMINARY_SACN_CLIENT_UNIVERSES];
e131_packet_t packet[LUMINARY_SACN_CLIENT_UNIVERSES];
e131_addr_t dest[LUMINARY_SACN_CLIENT_UNIVERSES];
uint8_t next_seq[LUMINARY_SACN_CLIENT_UNIVERSES];

char ui_message[256];

void sacn_client_init_universe(int universe) {
    // create a socket for E1.31
    if ((sockfd[universe] = e131_socket()) < 0)
        err(EXIT_FAILURE, "e131_socket");

    // initialize the new E1.31 packet in universe 1 with N_CHANNELS_DOWNSTREAM slots in preview mode
    e131_pkt_init(&packet[universe], universe, N_CHANNELS_DOWNSTREAM);
    memcpy(&packet[universe].frame.source_name, "Luminary E1.31 Client", 18);
    if (e131_set_option(&packet[universe], E131_OPT_PREVIEW, true) < 0)
        err(EXIT_FAILURE, "e131_set_option");

    /*
    // set remote system destination as unicast address
    if (e131_unicast_dest(&dest[universe], "127.0.0.1", LUMINARY_SACN_PORT) < 0)
        err(EXIT_FAILURE, "e131_unicast_dest");
    */

    // set remote system destination as multicast address
    if (e131_multicast_dest(&dest[universe], universe, LUMINARY_SACN_PORT) < 0)
        err(EXIT_FAILURE, "e131_multicast_dest");

    sprintf(ui_message, "sACN client (mc u.%d:%d)", universe, LUMINARY_SACN_PORT);
    print_sacn_message(ui_message, 9);
}

void sacn_client_init() {
    for (int universe = 0; universe < LUMINARY_SACN_CLIENT_UNIVERSES; ++ universe) {
        sacn_client_init_universe(universe);
    }
}

void sacn_draw_color(int logical_pixel, uint8_t r, uint8_t g, uint8_t b) {
    int universe = logical_pixel % 512;
    packet[universe].dmp.prop_val[logical_pixel*3 - 2] = r;
    packet[universe].dmp.prop_val[logical_pixel*3 - 1] = g;
    packet[universe].dmp.prop_val[logical_pixel*3    ] = b;
    packet[universe].dmp.prop_val[logical_pixel*3 + 1] = r;
    packet[universe].dmp.prop_val[logical_pixel*3 + 2] = g;
    packet[universe].dmp.prop_val[logical_pixel*3 + 3] = b;
}

void sacn_flush_universe(int universe) {
    packet[universe].frame.seq_number = next_seq[universe]++;

    if (e131_send(sockfd[universe], &packet[universe], &dest[universe]) < 0)
        err(EXIT_FAILURE, "e131_send");
    //e131_pkt_dump(stderr, &packet);

    sprintf(ui_message, "sent #%03u to %d                         ", next_seq[universe]-1, 0);
    print_sacn_message(ui_message, 10);
}

void sacn_flush() {
    for (int universe=0; universe < LUMINARY_SACN_CLIENT_UNIVERSES; ++universe) {
        sacn_flush_universe(universe);
    }
}

#endif /* SACN_CLIENT */

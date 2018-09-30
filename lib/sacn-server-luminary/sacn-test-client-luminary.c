#ifdef SACN_TEST_CLIENT

#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include <err.h>

#include "sacn-test-client-luminary.h"

#include "e131.h"
#include "display.h"
#include "sacn-constants-luminary.h"

int sockfd;
e131_packet_t packet;
e131_addr_t dest;
uint8_t next_seq_test = 0x01;

char ui_message[256];

uint8_t level = 0;

void sacn_test_client_start() {
    // create a socket for E1.31
    if ((sockfd = e131_socket()) < 0)
        err(EXIT_FAILURE, "e131_socket");

    // initialize the new E1.31 packet in universe 1 with 24 slots in preview mode
    e131_pkt_init(&packet, 1, N_CHANNELS);
    memcpy(&packet.frame.source_name, "E1.31 Test Client", 18);
    if (e131_set_option(&packet, E131_OPT_PREVIEW, true) < 0)
        err(EXIT_FAILURE, "e131_set_option");

    // set remote system destination as unicast address
    if (e131_unicast_dest(&dest, "127.0.0.1", LUMINARY_SACN_PORT) < 0)
        err(EXIT_FAILURE, "e131_unicast_dest");
    
    sprintf(ui_message, "sACN test client (uc 127.0.0.1:%d)", LUMINARY_SACN_PORT);
    print_sacn_message(ui_message, 9);
}

void sacn_test_client_send_message() {
    packet.dmp.prop_val[1] = level++;
    
    packet.frame.seq_number = next_seq_test++;
    
    if (e131_send(sockfd, &packet, &dest) < 0)
        err(EXIT_FAILURE, "e131_send");
    //e131_pkt_dump(stderr, &packet);
}

void sacn_test_client_set_level(int channel, uint8_t level) {
    packet.dmp.prop_val[channel] = level;
    
    packet.frame.seq_number = next_seq_test++;
    
    if (e131_send(sockfd, &packet, &dest) < 0)
        err(EXIT_FAILURE, "e131_send");
    //e131_pkt_dump(stderr, &packet);
    
    sprintf(ui_message, "sent #%03d, ch.%d:=%3d                         ", next_seq_test-1, channel, level);
    print_sacn_message(ui_message, 10);
}

#endif /* SACN_TEST_CLIENT */

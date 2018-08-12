#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <err.h>
#include <poll.h>

#include "sacn-server-luminary.h"

#include "e131.h"
#include "display.h"
#include "sacn-constants-luminary.h"

int sockfd;
e131_packet_t packet;
e131_error_t error;
uint8_t last_seq = 0x00;

struct pollfd sock_poll;

char ui_message[256];



int sacn_server_get_port() {
    return E131_DEFAULT_PORT;
}

void sacn_server_start() {
    // create a socket for E1.31
    if ((sockfd = e131_socket()) < 0)
        err(EXIT_FAILURE, "e131_socket");
    
    // bind the socket to the default E1.31 port and join multicast group for universe 1
    if (e131_bind(sockfd, E131_DEFAULT_PORT) < 0)
        err(EXIT_FAILURE, "e131_bind");
    if (e131_multicast_join(sockfd, 1) < 0)
        err(EXIT_FAILURE, "e131_multicast_join");
    
    sock_poll.fd = sockfd;
    sock_poll.events = POLLIN;
    sock_poll.revents = 0;
}

void store_channel_data(sacn_channels_t *sacn_channels, e131_packet_t *packet) {
    sacn_channels->raw.m_mode = packet->dmp.prop_val[CHANNEL_M_MODE];
    sacn_channels->logical.m_mode = packet->dmp.prop_val[CHANNEL_M_MODE]/85;
    
    sacn_channels->raw.m_intensity = sacn_channels->logical.m_intensity = packet->dmp.prop_val[CHANNEL_M_INTENSITY];
    
    sacn_channels->raw.m_color = packet->dmp.prop_val[CHANNEL_M_COLOR];
    sacn_channels->logical.m_color = packet->dmp.prop_val[CHANNEL_M_COLOR]/22;
    
    sacn_channels->raw.m_pattern = packet->dmp.prop_val[CHANNEL_M_PATTERN];
    sacn_channels->logical.m_pattern = packet->dmp.prop_val[CHANNEL_M_PATTERN]/64;
}

int sacn_server_poll(sacn_channels_t *sacn_channels) {
    poll(&sock_poll, 1, 0);
    
    if (!(sock_poll.revents & POLLIN)) {
        //print_sacn_message("(no packet to read)                                      ", 1);
        return 0;
    }
    
    if (e131_recv(sockfd, &packet) < 0)
        err(EXIT_FAILURE, "e131_recv");
    
    if ((error = e131_pkt_validate(&packet)) != E131_ERR_NONE) {
        fprintf(stderr, "e131_pkt_validate: %s\n", e131_strerror(error));
        return -1;
    }
    
    if (e131_pkt_discard(&packet, last_seq)) {
        sprintf(ui_message, "warning: packet out of order received (was %3d)", packet.frame.seq_number);
        print_sacn_message(ui_message, 1);
        last_seq = packet.frame.seq_number;
        return -1;
    } else {
        print_sacn_message("                                               ", 1);
    }
    
    //e131_pkt_dump(stderr, &packet);
    
    store_channel_data(sacn_channels, &packet);
    
    sprintf(ui_message,
        "poll #%d (%3d|%3d|%3d|%3d)",
        packet.frame.seq_number,
        sacn_channels->raw.m_mode,
        sacn_channels->raw.m_intensity,
        sacn_channels->raw.m_color,
        sacn_channels->raw.m_pattern)
    ;
    print_sacn_message(ui_message, 2);
    
    last_seq = packet.frame.seq_number;
    return 1;
}

void sacn_server_shutdown() {
    
}
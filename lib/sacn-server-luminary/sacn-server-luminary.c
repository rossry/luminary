#ifdef SACN_SERVER

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
    if (e131_bind(sockfd, LUMINARY_SACN_PORT) < 0)
        err(EXIT_FAILURE, "e131_bind");
    if (e131_multicast_join(sockfd, LUMINARY_SACN_MULTICAST_UNIVERSE) < 0)
        err(EXIT_FAILURE, "e131_multicast_join");
    
    sock_poll.fd = sockfd;
    sock_poll.events = POLLIN;
    sock_poll.revents = 0;
    
    sprintf(ui_message, "sACN server (uc :%d|mc u.%d)", LUMINARY_SACN_PORT, LUMINARY_SACN_MULTICAST_UNIVERSE);
    print_sacn_message(ui_message, 0);
    
    sprintf(ui_message,"(no messages yet)");
    print_sacn_message(ui_message, 1);
}

void store_channel_data(sacn_channels_t *sacn_channels, e131_packet_t *packet) {
    sacn_channels->raw.mode = packet->dmp.prop_val[CHANNEL_M_MODE];
    sacn_channels->logical.mode = packet->dmp.prop_val[CHANNEL_M_MODE]/85;

    sacn_channels->raw.m.intensity = sacn_channels->logical.m.intensity = packet->dmp.prop_val[CHANNEL_M_INTENSITY];
    
    sacn_channels->raw.m.color = packet->dmp.prop_val[CHANNEL_M_COLOR];
    sacn_channels->logical.m.color = packet->dmp.prop_val[CHANNEL_M_COLOR]/22;
    
    sacn_channels->raw.m.pattern = packet->dmp.prop_val[CHANNEL_M_PATTERN];
    sacn_channels->logical.m.pattern = packet->dmp.prop_val[CHANNEL_M_PATTERN]/32;
    
    sacn_channels->raw.m.transition = packet->dmp.prop_val[CHANNEL_M_TRANSITION];
    sacn_channels->logical.m.transition = packet->dmp.prop_val[CHANNEL_M_TRANSITION]/64;
    
    for (int ii=0; ii<5; ++ii) {
        sacn_channels->raw.p[ii].intensity = sacn_channels->logical.p[ii].intensity = packet->dmp.prop_val[CHANNEL_PETAL_INTENSITY(ii)];
        
        sacn_channels->raw.p[ii].color = packet->dmp.prop_val[CHANNEL_PETAL_COLOR(ii)];
        sacn_channels->logical.p[ii].color = packet->dmp.prop_val[CHANNEL_PETAL_COLOR(ii)]/22;
        
        sacn_channels->raw.p[ii].pattern = packet->dmp.prop_val[CHANNEL_PETAL_PATTERN(ii)];
        sacn_channels->logical.p[ii].pattern = packet->dmp.prop_val[CHANNEL_PETAL_PATTERN(ii)]/32;
        
        sacn_channels->raw.p[ii].transition = packet->dmp.prop_val[CHANNEL_PETAL_TRANSITION(ii)];
        sacn_channels->logical.p[ii].transition = packet->dmp.prop_val[CHANNEL_PETAL_TRANSITION(ii)]/64;
        
        // CR rrheingans-yoo: for testing
        /*
        sacn_channels->raw.p[ii].intensity = sacn_channels->raw.m.intensity;
        sacn_channels->logical.p[ii].intensity = sacn_channels->logical.m.intensity;
        
        sacn_channels->raw.p[ii].color = sacn_channels->raw.m.color + 44*ii;
        sacn_channels->logical.p[ii].color = sacn_channels->logical.m.color + 2*ii;
        
        sacn_channels->raw.p[ii].pattern = sacn_channels->raw.m.pattern;
        sacn_channels->logical.p[ii].pattern = sacn_channels->logical.m.pattern;
        
        sacn_channels->raw.p[ii].transition = sacn_channels->raw.m.transition;
        sacn_channels->logical.p[ii].transition = sacn_channels->logical.m.transition;
        */
    }
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
        sprintf(ui_message, "INVALID %s\n", e131_strerror(error));
        print_sacn_message(ui_message, 1);
        return -1;
    }
    
    if (e131_pkt_discard(&packet, last_seq)) {
        sprintf(ui_message, "SEQ NO #%03d", packet.frame.seq_number);
        print_sacn_message(ui_message, 1);
        last_seq = packet.frame.seq_number;
        return -1;
    } else {
        print_sacn_message("                     ", 1);
    }
    
    //e131_pkt_dump(stderr, &packet);
    
    store_channel_data(sacn_channels, &packet);
    
    sprintf(ui_message,
        "msg ok #%03d (mode:%3d)",
        packet.frame.seq_number,
        sacn_channels->raw.mode)
    ;
    print_sacn_message(ui_message, 1);
    
    #ifdef LUMINARY_SACN_VERBOSE
        sprintf(ui_message,
            "M(%3di|%3dc|%3dp|%3dt)",
            sacn_channels->raw.m.intensity,
            sacn_channels->raw.m.color,
            sacn_channels->raw.m.pattern,
            sacn_channels->raw.m.transition
        );
        print_sacn_message(ui_message, 2);
        
        for (int ii=0; ii<5; ++ii) {
            sprintf(ui_message,
                "%d(%3di|%3dc|%3dp|%3dt)", ii,
                sacn_channels->raw.p[ii].intensity,
                sacn_channels->raw.p[ii].color,
                sacn_channels->raw.p[ii].pattern,
                sacn_channels->raw.p[ii].transition
            );
            print_sacn_message(ui_message, 3+ii);
        }
    #endif /* LUMINARY_SACN_VERBOSE */
    
    last_seq = packet.frame.seq_number;
    return 1;
}

void sacn_server_shutdown() {
    
}

#endif /* SACN_SERVER */

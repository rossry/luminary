#include <cstdint>

#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "pp-server-luminary.h"

#include "pp-server.h"

// CR rrheingans-yoo: implement pixelpusher server

extern "C" {
    void pp_server_start() {
        // CR rrheingans-yoo: start up pixelpusher server
        return;
    }
    void pp_server_shutdown() {
        //pp::ShutdownPixelPusherServer(); // CR rrheingans-yoo: reactivate me
        return;
    }
}
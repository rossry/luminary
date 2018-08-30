#ifdef PP_SERVER

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
    void pp_server_start(int* display_current) {
        // CR rrheingans-yoo: start up pixelpusher server
        return;
    }
    void pp_server_shutdown() {
        //pp::ShutdownPixelPusherServer(); // CR rrheingans-yoo: reactivate me
        return;
    }
}

#endif /* PP_SERVER */

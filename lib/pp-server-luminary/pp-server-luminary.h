#ifndef PIXEL_PUSH_SERVER_LUMINARY_H
#define PIXEL_PUSH_SERVER_LUMINARY_H

#ifdef __cplusplus
extern "C" {
#endif
    
    void pp_server_start(int* display_current);
    void pp_server_shutdown();

#ifdef __cplusplus
} //end extern "C"
#endif

#endif  /* PIXEL_PUSH_SERVER_LUMINARY_H */
#ifndef SACN_CONSTANTS_LUMINARY_H
#define SACN_CONSTANTS_LUMINARY_H

#include "e131.h"

// general
#define LUMINARY_SACN_VERBOSE


// sACN server

#define LUMINARY_SACN_PORT               E131_DEFAULT_PORT
#define LUMINARY_SACN_MULTICAST_UNIVERSE 1

#define N_CHANNELS 26 // 0 is unused

#define CHANNEL_BASE           253

#define CHANNEL_M_MODE         (CHANNEL_BASE+1)

#define CHANNEL_M_INTENSITY    (CHANNEL_BASE+2)
#define CHANNEL_M_COLOR        (CHANNEL_BASE+3)
#define CHANNEL_M_PATTERN      (CHANNEL_BASE+4)
#define CHANNEL_M_TRANSITION   (CHANNEL_BASE+5)

#define CHANNEL_PETALS_BASE    (CHANNEL_BASE+6)
#define CHANNEL_PETALS_EACH    4

#define CHANNEL_PETAL_INTENSITY(ii)  (0 + CHANNEL_PETALS_BASE + ii*CHANNEL_PETALS_EACH)
#define CHANNEL_PETAL_COLOR(ii)      (1 + CHANNEL_PETALS_BASE + ii*CHANNEL_PETALS_EACH)
#define CHANNEL_PETAL_PATTERN(ii)    (2 + CHANNEL_PETALS_BASE + ii*CHANNEL_PETALS_EACH)
#define CHANNEL_PETAL_TRANSITION(ii) (3 + CHANNEL_PETALS_BASE + ii*CHANNEL_PETALS_EACH)

// sACN client

#define BASE_UNIVERSE_LUMINARY_CLIENT 2

#define N_CHANNELS_DOWNSTREAM 300

#endif /* SACN_CONSTANTS_LUMINARY_H */

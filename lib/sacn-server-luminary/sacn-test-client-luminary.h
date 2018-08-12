#ifndef SACN_TEST_CLIENT_LUMINARY_H
#define SACN_TEST_CLIENT_LUMINARY_H

#include <stdint.h>

void sacn_test_client_start();
void sacn_test_client_send_message();
void sacn_test_client_set_level(int channel, uint8_t level);

#endif /* SACN_TEST_CLIENT_LUMINARY_H */

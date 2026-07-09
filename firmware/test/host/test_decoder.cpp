// Host-compiled conformance test for the C++ decoder (spec §11.9, §17.2.5).
//
// Replays firmware/golden/case1/stream.bin through lumicodec and asserts:
//   1. bit-exact quantized OKLCH state after every KEYFRAME/DELTA frame
//      (expected.bin, written by the Python reference)
//   2. full-strip RGB output within +/-2 of the Python float color pipeline
//      (expected_rgb.bin), validating the Q14 fixed-point path

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "lumicodec.h"

static std::vector<uint8_t> readFile(const std::string& path) {
  FILE* f = fopen(path.c_str(), "rb");
  if (!f) {
    fprintf(stderr, "cannot open %s\n", path.c_str());
    exit(2);
  }
  fseek(f, 0, SEEK_END);
  long size = ftell(f);
  fseek(f, 0, SEEK_SET);
  std::vector<uint8_t> data(static_cast<size_t>(size));
  if (fread(data.data(), 1, data.size(), f) != data.size()) {
    fprintf(stderr, "short read on %s\n", path.c_str());
    exit(2);
  }
  fclose(f);
  return data;
}

int main(int argc, char** argv) {
  std::string dir = argc > 1 ? argv[1] : "../../golden/case1";
  std::vector<uint8_t> stream = readFile(dir + "/stream.bin");
  std::vector<uint8_t> expected = readFile(dir + "/expected.bin");
  std::vector<uint8_t> expectedRgb = readFile(dir + "/expected_rgb.bin");

  lumicodec::Decoder decoder;
  size_t expectedOffset = 0;
  int framesChecked = 0;

  // Feed one wire frame at a time (split on 0x00 delimiters), in two byte
  // chunks each, so state can be checked after every applied frame while
  // still exercising the incremental splitter.
  size_t offset = 0;
  while (offset < stream.size()) {
    size_t end = offset;
    while (end < stream.size() && stream[end] != 0) end++;
    if (end < stream.size()) end++;  // include the delimiter
    size_t mid = offset + (end - offset) / 2;
    int applied = decoder.feed(stream.data() + offset, mid - offset);
    applied += decoder.feed(stream.data() + mid, end - mid);
    offset = end;
    if (applied > 1) {
      fprintf(stderr, "multiple frames applied from one wire frame\n");
      return 1;
    }
    for (int a = 0; a < applied; a++) {
      if (decoder.lastFrameType() == lumicodec::FRAME_SESSION) continue;
      if (expectedOffset + 2 > expected.size()) {
        fprintf(stderr, "ran out of expected blocks\n");
        return 1;
      }
      uint16_t nActive = static_cast<uint16_t>(expected[expectedOffset] |
                                               (expected[expectedOffset + 1] << 8));
      expectedOffset += 2;
      if (nActive != decoder.nActive()) {
        fprintf(stderr, "frame %d: nActive %u != %zu\n", framesChecked, nActive,
                decoder.nActive());
        return 1;
      }
      const int32_t* q = decoder.q();
      for (size_t i = 0; i < static_cast<size_t>(nActive) * 3; i++) {
        uint8_t want = expected[expectedOffset + i];
        if (q[i] != static_cast<int32_t>(want)) {
          fprintf(stderr, "frame %d: q[%zu] = %d, want %u\n", framesChecked,
                  i, q[i], want);
          return 1;
        }
      }
      expectedOffset += static_cast<size_t>(nActive) * 3;
      framesChecked++;
    }
  }
  if (expectedOffset != expected.size()) {
    fprintf(stderr, "unused expected blocks remain (%zu != %zu)\n",
            expectedOffset, expected.size());
    return 1;
  }
  if (decoder.wantResync()) {
    fprintf(stderr, "decoder flagged resync on clean stream\n");
    return 1;
  }

  // RGB tolerance check against the Python float pipeline.
  size_t rgbOffset = 0;
  int stripsChecked = 0;
  std::vector<uint8_t> rgb(3 * 4096);
  while (rgbOffset < expectedRgb.size()) {
    uint8_t channel = expectedRgb[rgbOffset];
    uint16_t length = static_cast<uint16_t>(expectedRgb[rgbOffset + 1] |
                                            (expectedRgb[rgbOffset + 2] << 8));
    rgbOffset += 3;
    uint16_t got = decoder.stripRGB(channel, rgb.data());
    if (got != length) {
      fprintf(stderr, "channel %u: length %u != %u\n", channel, got, length);
      return 1;
    }
    for (size_t i = 0; i < static_cast<size_t>(length) * 3; i++) {
      int want = expectedRgb[rgbOffset + i];
      int have = rgb[i];
      if (abs(want - have) > 2) {
        fprintf(stderr, "channel %u byte %zu: rgb %d, want %d (tol 2)\n",
                channel, i, have, want);
        return 1;
      }
    }
    rgbOffset += static_cast<size_t>(length) * 3;
    stripsChecked++;
  }

  printf("OK: %d frames bit-exact, %d strips within RGB tolerance\n",
         framesChecked, stripsChecked);
  return 0;
}

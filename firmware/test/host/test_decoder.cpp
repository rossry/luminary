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
#include <new>
#include <string>
#include <vector>

#include "lumicodec.h"

// ------------------------------------------------- allocation instrumentation
//
// testDeltaOpBound has to prove the op count is bounded BEFORE it is used to
// size an allocation. A malformed frame is rejected either way -- the parse
// loop runs out of payload and bails -- so rejection alone proves nothing.
// What matters on a 264KB part is that the decoder never tried to reserve
// ~1MB first, and only a counting allocator can see that.

// g_allocBytes is CUMULATIVE, not peak: vector growth reallocates, so the
// running total exceeds live memory. That is fine for what these checks ask
// -- "was a very large array sized off an untrusted count?" -- as long as the
// thresholds are set against the specific allocation being guarded.
//
// NOINLINE matters: if GCC inlines these into the call sites it sees malloc()
// paired with the builtin operator new and warns -Wmismatched-new-delete all
// over the build. Keeping them opaque keeps the build clean under -Wextra.
#if defined(__GNUC__)
#define ALLOC_NOINLINE __attribute__((noinline))
#else
#define ALLOC_NOINLINE
#endif

static size_t g_allocBytes = 0;
static bool g_trackAlloc = false;

ALLOC_NOINLINE void* operator new(size_t n) {
  if (g_trackAlloc) g_allocBytes += n;
  void* p = std::malloc(n ? n : 1);
  if (p == nullptr) throw std::bad_alloc();
  return p;
}
ALLOC_NOINLINE void* operator new[](size_t n) { return operator new(n); }
ALLOC_NOINLINE void operator delete(void* p) noexcept { std::free(p); }
ALLOC_NOINLINE void operator delete[](void* p) noexcept { std::free(p); }
ALLOC_NOINLINE void operator delete(void* p, size_t) noexcept { std::free(p); }
ALLOC_NOINLINE void operator delete[](void* p, size_t) noexcept { std::free(p); }

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

// ---------------------------------------------------- synthetic frame builder
//
// The golden vectors only cover well-formed input for one small geometry, so
// the robustness checks below construct their own frames.

static size_t cobsEncodeLocal(const uint8_t* in, size_t len, uint8_t* out) {
  size_t outIdx = 1, codeIdx = 0;
  uint8_t code = 1;
  for (size_t i = 0; i < len; i++) {
    if (in[i] == 0) {
      out[codeIdx] = code;
      codeIdx = outIdx++;
      code = 1;
    } else {
      out[outIdx++] = in[i];
      if (++code == 0xFF) {
        out[codeIdx] = code;
        codeIdx = outIdx++;
        code = 1;
      }
    }
  }
  out[codeIdx] = code;
  return outIdx;
}

static std::vector<uint8_t> wireFrame(uint8_t type, uint8_t controller,
                                      const std::vector<uint8_t>& payload) {
  std::vector<uint8_t> raw(lumicodec::HEADER_SIZE + payload.size() + 2);
  raw[0] = lumicodec::PROTOCOL_VERSION;
  raw[1] = type;
  raw[2] = controller;
  double t = 0.0;
  std::memcpy(raw.data() + 3, &t, sizeof(double));
  raw[11] = static_cast<uint8_t>(payload.size() & 0xFF);
  raw[12] = static_cast<uint8_t>(payload.size() >> 8);
  std::memcpy(raw.data() + lumicodec::HEADER_SIZE, payload.data(), payload.size());
  size_t crcOver = lumicodec::HEADER_SIZE + payload.size();
  uint16_t crc = lumicodec::crc16(raw.data(), crcOver);
  raw[crcOver] = static_cast<uint8_t>(crc & 0xFF);
  raw[crcOver + 1] = static_cast<uint8_t>(crc >> 8);

  std::vector<uint8_t> out(raw.size() * 2 + 8);
  size_t n = cobsEncodeLocal(raw.data(), raw.size(), out.data());
  out[n++] = 0;
  out.resize(n);
  return out;
}

// SESSION declaring one channel of `length` all-ACTIVE pixels.
static std::vector<uint8_t> sessionOneChannel(uint8_t id, uint16_t length) {
  std::vector<uint8_t> payload;
  payload.push_back(1);
  payload.push_back(id);
  payload.push_back(static_cast<uint8_t>(length & 0xFF));
  payload.push_back(static_cast<uint8_t>(length >> 8));
  for (uint16_t i = 0; i < length; i++) {
    payload.push_back(lumicodec::KIND_ACTIVE);
    payload.push_back(0);
  }
  payload.push_back(255);
  payload.push_back(255);
  payload.push_back(255);
  payload.push_back(255);
  return wireFrame(lumicodec::FRAME_SESSION, 0, payload);
}

// stripRGB must clamp to the caller's buffer, not the wire's strip length.
static int testStripRgbClamp() {
  const uint16_t DECLARED = 1000;  // longer than the caller's buffer
  const uint16_t CAPACITY = 512;   // mirrors main.cpp's MAX_PER_STRIP
  const size_t GUARD = 4096;

  lumicodec::Decoder decoder;
  std::vector<uint8_t> session = sessionOneChannel(0, DECLARED);
  if (decoder.feed(session.data(), session.size()) != 1) {
    fprintf(stderr, "clamp test: oversized SESSION was not applied\n");
    return 1;
  }
  std::vector<uint8_t> kf(decoder.nActive() * 2, 0x11);
  std::vector<uint8_t> keyframe = wireFrame(lumicodec::FRAME_KEYFRAME, 0, kf);
  decoder.feed(keyframe.data(), keyframe.size());

  std::vector<uint8_t> region(static_cast<size_t>(CAPACITY) * 3 + GUARD, 0xAA);
  uint16_t written = decoder.stripRGB(0, region.data(), CAPACITY);
  if (written != CAPACITY) {
    fprintf(stderr, "clamp test: stripRGB returned %u, want %u\n", written,
            CAPACITY);
    return 1;
  }
  for (size_t i = static_cast<size_t>(CAPACITY) * 3; i < region.size(); i++) {
    if (region[i] != 0xAA) {
      fprintf(stderr, "clamp test: wrote past the buffer at +%zu\n",
              i - static_cast<size_t>(CAPACITY) * 3);
      return 1;
    }
  }
  return 0;
}

// A DELTA claiming more ops than there are active lights must be rejected
// before it is used to size any allocation.
static int testDeltaOpBound() {
  lumicodec::Decoder decoder;
  std::vector<uint8_t> session = sessionOneChannel(0, 8);
  if (decoder.feed(session.data(), session.size()) != 1) {
    fprintf(stderr, "op-bound test: SESSION was not applied\n");
    return 1;
  }
  std::vector<uint8_t> payload = {0xFF, 0xFF, 0x00, 0x11, 0x11};  // nOps=65535
  std::vector<uint8_t> delta = wireFrame(lumicodec::FRAME_DELTA, 0, payload);

  g_allocBytes = 0;
  g_trackAlloc = true;
  int applied = decoder.feed(delta.data(), delta.size());
  g_trackAlloc = false;

  if (applied != 0 || !decoder.wantResync()) {
    fprintf(stderr,
            "op-bound test: nOps=65535 over %zu actives was accepted "
            "(applied=%d, wantResync=%d)\n",
            decoder.nActive(), applied, static_cast<int>(decoder.wantResync()));
    return 1;
  }
  // Rejecting the frame is not enough: it must be rejected without first
  // sizing an allocation off the unvalidated count. The frame itself is a
  // couple of dozen bytes, so anything above this means nOps drove a malloc.
  const size_t ALLOC_LIMIT = 64 * 1024;
  if (g_allocBytes > ALLOC_LIMIT) {
    fprintf(stderr,
            "op-bound test: rejected, but allocated %zu bytes from an "
            "unvalidated nOps (limit %zu)\n",
            g_allocBytes, ALLOC_LIMIT);
    return 1;
  }
  return 0;
}

// An oversized SESSION must be refused without allocating from its light
// count, and must drop the board to the onboard test pattern.
static int testOversizedSessionFallback() {
  // 8 channels x 787px ~= the pentagon-4A-35 geometry that hung the board.
  const int CHANNELS = 8;
  const uint16_t PER_CHANNEL = 787;

  std::vector<uint8_t> payload;
  payload.push_back(static_cast<uint8_t>(CHANNELS));
  for (int c = 0; c < CHANNELS; c++) {
    payload.push_back(static_cast<uint8_t>(c));
    payload.push_back(static_cast<uint8_t>(PER_CHANNEL & 0xFF));
    payload.push_back(static_cast<uint8_t>(PER_CHANNEL >> 8));
    for (uint16_t i = 0; i < PER_CHANNEL; i++) {
      payload.push_back(lumicodec::KIND_ACTIVE);
      payload.push_back(0);
    }
  }
  payload.push_back(255);
  payload.push_back(255);
  payload.push_back(255);
  payload.push_back(255);

  lumicodec::Decoder decoder;
  std::vector<uint8_t> frame = wireFrame(lumicodec::FRAME_SESSION, 0, payload);

  g_allocBytes = 0;
  g_trackAlloc = true;
  int applied = decoder.feed(frame.data(), frame.size());
  g_trackAlloc = false;

  if (applied != 0 || decoder.hasSession()) {
    fprintf(stderr,
            "oversized SESSION test: %d lights was accepted (applied=%d)\n",
            CHANNELS * PER_CHANNEL, applied);
    return 1;
  }
  if (!decoder.testPatternActive()) {
    fprintf(stderr, "oversized SESSION test: did not fall back to the test "
                    "pattern\n");
    return 1;
  }
  // The refusal must come before q_/v_ are sized off the light count. Those
  // two alone are 24 bytes x 6296 lights = ~151KB, so a run that stays under
  // that provably never sized them; parsing the channel arrays on the way to
  // the check legitimately costs ~90KB cumulative, which is the gap this
  // threshold sits in. Without the guard the total lands near 240KB.
  const size_t ALLOC_LIMIT = 150 * 1024;
  if (g_allocBytes > ALLOC_LIMIT) {
    fprintf(stderr,
            "oversized SESSION test: refused, but allocated %zu bytes "
            "(limit %zu)\n",
            g_allocBytes, ALLOC_LIMIT);
    return 1;
  }

  // The fallback must paint something: lit beads separated by dark gaps.
  const uint16_t N = 96;
  std::vector<uint8_t> rgb(static_cast<size_t>(N) * 3, 0x7F);
  lumicodec::testPatternRGB(0, rgb.data(), N, 0);
  int lit = 0, dark = 0;
  for (uint16_t i = 0; i < N; i++) {
    const uint8_t* px = rgb.data() + static_cast<size_t>(i) * 3;
    if (px[0] || px[1] || px[2]) lit++; else dark++;
  }
  if (lit == 0 || dark == 0) {
    fprintf(stderr,
            "oversized SESSION test: test pattern is uniform (%d lit, %d "
            "dark) -- expected beads with gaps\n",
            lit, dark);
    return 1;
  }
  // And it must animate: a later timestamp should not be pixel-identical.
  std::vector<uint8_t> later(static_cast<size_t>(N) * 3, 0);
  lumicodec::testPatternRGB(0, later.data(), N, 500);
  if (later == rgb) {
    fprintf(stderr, "oversized SESSION test: test pattern is static\n");
    return 1;
  }
  return 0;
}

// oklchQ14ToRgb8 does its OKLab->LMS matrix, the a/b projection and cube_q14
// in int32 rather than int64, because the RP2040 is a Cortex-M0+ with no
// 64-bit multiply -- every int64 product is an __aeabi_lmul call, and those
// dominated the per-pixel cost. That is only correct if no 32-bit
// intermediate can overflow.
//
// The golden vectors exercise one small geometry and a narrow slice of the
// colour space, so they cannot establish that. This does: the ACTIVE input
// space is exactly 64 x 32 x 256 quantized triples, small enough to walk in
// full and compare against an int64 reference. INTERPOLATED lights feed in
// blended l/c/h, which lie inside the convex hull of the table values and so
// cannot exceed these bounds -- a sampled sweep covers those.
static int testColorPipelineWidth() {
  // Mirrors of the spec §8.4.1 matrices and the §11.4.1 quantization limits.
  // Deliberately restated here rather than shared: if someone retunes a
  // coefficient or widens a quantization level in lumicodec.cpp, the two
  // copies diverge and this test fails, which is exactly the warning wanted.
  const int32_t mL2LMS[9] = {16384, 6494,  3536,
                             16384, -1730, -1046,
                             16384, -1466, -21160};
  const int64_t kInt32Max = 2147483647LL;
  const int64_t lMax = 16384;                  // qL 63/63 * 16384
  const int64_t cMax = (int64_t)(31.0 / 31.0 * 0.4 * 16384.0 + 0.5);  // 6554
  const int64_t trigMax = 16384;

  // |a|, |b| = |c_q14 * cos| >> 14, so both are bounded by cMax.
  const int64_t abMax = (cMax * trigMax) >> 14;
  if ((cMax * trigMax) >= kInt32Max) {
    fprintf(stderr, "a/b projection can overflow int32: %lld\n",
            (long long)(cMax * trigMax));
    return 1;
  }

  // Worst-case L->LMS accumulator, taking every term at its largest.
  int64_t accMax = 0;
  for (int row = 0; row < 3; row++) {
    const int64_t worst = (int64_t)llabs(mL2LMS[row * 3]) * lMax +
                          (int64_t)llabs(mL2LMS[row * 3 + 1]) * abMax +
                          (int64_t)llabs(mL2LMS[row * 3 + 2]) * abMax;
    if (worst >= kInt32Max) {
      fprintf(stderr, "L2LMS row %d can overflow int32: %lld\n", row,
              (long long)worst);
      return 1;
    }
    if (worst > accMax) accMax = worst;
  }

  // cube_q14 on the largest such accumulator: x*x, then (x*x>>14)*x.
  const int64_t xMax = accMax >> 14;
  const int64_t sqMax = xMax * xMax;
  if (sqMax >= kInt32Max) {
    fprintf(stderr, "cube_q14 x*x can overflow int32: %lld\n",
            (long long)sqMax);
    return 1;
  }
  const int64_t cubeMax = (sqMax >> 14) * xMax;
  if (cubeMax >= kInt32Max) {
    fprintf(stderr, "cube_q14 xx*x can overflow int32: %lld\n",
            (long long)cubeMax);
    return 1;
  }

  // gammaEncode narrows to int32 too; its input is the (still int64) LMS->RGB
  // accumulator shifted down, then scaled twice by a u8.
  const int64_t gammaMax = (cubeMax >> 14) * 255;
  if (gammaMax >= kInt32Max) {
    fprintf(stderr, "gammaEncode can overflow int32: %lld\n",
            (long long)gammaMax);
    return 1;
  }

  printf("  color pipeline int32 headroom: L2LMS %.1fx, cube %.1fx, "
         "gamma %.0fx\n",
         (double)kInt32Max / (double)accMax,
         (double)kInt32Max / (double)cubeMax,
         (double)kInt32Max / (double)gammaMax);
  return 0;
}

// ---------------------------------------------- presentation clock (13.9)

static int testPresentationClock() {
  const double fps = 60.0;
  const uint32_t frameUs = (uint32_t)(1e6 / fps);

  // Queuing delay is non-negative by construction -- it is time spent
  // waiting, never time saved -- so the true offset is the floor, and the
  // minimum over a window converges on it while a mean cannot.
  const int32_t queueA[8] = {4300, 900, 120, 0, 40, 1500, 70, 2600};
  const int32_t queueB[8] = {0, 2600, 70, 1500, 40, 4300, 120, 900};

  // The base is captured from the *first* frame, whose own queuing delay is
  // arbitrary. So the filter's real job is undoing an unlucky first frame:
  // board A started 4300 us late, and its skew must walk back by that much.
  lumicodec::PresentationClock a;
  const uint32_t bootA = 500000, latA = 1200;
  for (int i = 0; i < 200; i++) {
    const double t = i / fps;
    a.observe(t, bootA + (uint32_t)(t * 1e6) + latA + (uint32_t)queueA[i % 8]);
  }
  if (a.skewUs() > -4100 || a.skewUs() < -4500) {
    fprintf(stderr,
            "clock: skew %d us, expected ~-4300 (undoing a late first frame, "
            "not averaging the queuing)\n",
            (int)a.skewUs());
    return 1;
  }

  // The property the whole mechanism exists for. Two boards with different
  // link latencies, different local epochs, and differently unlucky first
  // frames must present the same frame at deadlines differing by exactly
  // their link-latency difference -- no first-frame luck may survive, or the
  // boards paint out of step forever.
  lumicodec::PresentationClock b;
  const uint32_t bootB = 99000000, latB = 7800;
  for (int i = 0; i < 200; i++) {
    const double t = i / fps;
    b.observe(t, bootB + (uint32_t)(t * 1e6) + latB + (uint32_t)queueB[i % 8]);
  }
  const double showT = 200 / fps;
  const uint32_t delay = 50000;
  const int64_t relA = (int64_t)(a.deadline(showT, delay) - bootA);
  const int64_t relB = (int64_t)(b.deadline(showT, delay) - bootB);
  const int64_t spread = relA > relB ? relA - relB : relB - relA;
  const int64_t want = (int64_t)latB - (int64_t)latA;
  if (spread < want - 200 || spread > want + 200) {
    fprintf(stderr,
            "clock: boards %lld us apart, expected ~%lld (their link latency "
            "difference, first-frame luck removed)\n",
            (long long)spread, (long long)want);
    return 1;
  }

  // A board that has seen nothing must not claim a deadline.
  lumicodec::PresentationClock fresh;
  if (fresh.ready()) {
    fprintf(stderr, "clock: reported ready before any frame\n");
    return 1;
  }

  // The display delay is capped below one frame period: only one snapshot is
  // in flight, so a longer hold stalls the pipeline instead of buffering it.
  lumicodec::PresentationClock paced;
  for (int i = 0; i < 40; i++) {
    paced.observe(i / fps, 1000000 + (uint32_t)(i / fps * 1e6));
  }
  if (paced.intervalUs() < frameUs - 200 || paced.intervalUs() > frameUs + 200) {
    fprintf(stderr, "clock: interval %u us, expected ~%u\n",
            paced.intervalUs(), frameUs);
    return 1;
  }
  if (paced.usableDelay(1000) != 1000) {
    fprintf(stderr, "clock: a delay inside one frame must pass through\n");
    return 1;
  }
  if (paced.usableDelay(500000) >= frameUs) {
    fprintf(stderr, "clock: delay %u us not capped below the %u us frame\n",
            paced.usableDelay(500000), frameUs);
    return 1;
  }

  // Deadlines advance exactly one frame period per frame.
  lumicodec::PresentationClock even;
  for (int i = 0; i < 200; i++) {
    even.observe(i / fps, 1000000 + (uint32_t)(i / fps * 1e6));
  }
  const int32_t step =
      (int32_t)(even.deadline(11 / fps, 0) - even.deadline(10 / fps, 0));
  if (step < (int32_t)frameUs - 2 || step > (int32_t)frameUs + 2) {
    fprintf(stderr, "clock: deadline step %d us, expected %u\n", (int)step,
            frameUs);
    return 1;
  }
  return 0;
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
  const uint16_t RGB_CAPACITY = 4096;
  std::vector<uint8_t> rgb(3 * RGB_CAPACITY);
  while (rgbOffset < expectedRgb.size()) {
    uint8_t channel = expectedRgb[rgbOffset];
    uint16_t length = static_cast<uint16_t>(expectedRgb[rgbOffset + 1] |
                                            (expectedRgb[rgbOffset + 2] << 8));
    rgbOffset += 3;
    uint16_t got = decoder.stripRGB(channel, rgb.data(), RGB_CAPACITY);
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

  // Robustness checks on synthetic frames the golden vectors cannot cover.
  if (testStripRgbClamp() != 0) return 1;
  if (testDeltaOpBound() != 0) return 1;
  if (testOversizedSessionFallback() != 0) return 1;
  if (testColorPipelineWidth() != 0) return 1;
  if (testPresentationClock() != 0) return 1;

  printf("OK: %d frames bit-exact, %d strips within RGB tolerance, "
         "5 robustness checks passed\n",
         framesChecked, stripsChecked);
  return 0;
}

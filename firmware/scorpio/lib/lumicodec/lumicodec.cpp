#include "lumicodec.h"

#include <cmath>
#include <cstring>

namespace lumicodec {

// ------------------------------------------------------------------- CRC16

uint16_t crc16(const uint8_t* data, size_t len) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < len; i++) {
    crc = static_cast<uint16_t>(crc ^ (static_cast<uint16_t>(data[i]) << 8));
    for (int b = 0; b < 8; b++) {
      crc = (crc & 0x8000) ? static_cast<uint16_t>((crc << 1) ^ 0x1021)
                           : static_cast<uint16_t>(crc << 1);
    }
  }
  return crc;
}

// -------------------------------------------------------------------- COBS

size_t cobsDecode(const uint8_t* in, size_t len, uint8_t* out) {
  size_t inIdx = 0, outIdx = 0;
  while (inIdx < len) {
    uint8_t code = in[inIdx];
    if (code == 0 || inIdx + code > len + 1) return 0;
    for (uint8_t i = 1; i < code && inIdx + i < len; i++) {
      out[outIdx++] = in[inIdx + i];
    }
    inIdx += code;
    if (code != 0xFF && inIdx < len) out[outIdx++] = 0;
  }
  return outIdx;
}

static size_t cobsEncode(const uint8_t* in, size_t len, uint8_t* out) {
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

// --------------------------------------------------------------- predictor

static inline int32_t clampi(int32_t v, int32_t lo, int32_t hi) {
  return v < lo ? lo : (v > hi ? hi : v);
}

static inline int32_t hueMod(int32_t v) { return ((v % 256) + 256) % 256; }

static inline int32_t hueWrapDiff(int32_t a, int32_t b) {
  return hueMod(a - b + 128) - 128;
}

// ----------------------------------------------------------------- decoder

Decoder::Decoder() { pending_.reserve(1024); }

int Decoder::feed(const uint8_t* data, size_t len) {
  int applied = 0;
  for (size_t i = 0; i < len; i++) {
    uint8_t byte = data[i];
    if (byte != 0) {
      if (pending_.size() < MAX_FRAME) pending_.push_back(byte);
      continue;
    }
    if (pending_.empty()) continue;
    std::vector<uint8_t> decoded(pending_.size());
    size_t decodedLen = cobsDecode(pending_.data(), pending_.size(), decoded.data());
    pending_.clear();
    if (decodedLen == 0 || !decodeFrame(decoded.data(), decodedLen)) {
      wantResync_ = true;
      continue;
    }
    applied++;
  }
  return applied;
}

bool Decoder::decodeFrame(const uint8_t* raw, size_t len) {
  if (len < HEADER_SIZE + 2) return false;
  uint16_t expected = static_cast<uint16_t>(raw[len - 2] | (raw[len - 1] << 8));
  if (crc16(raw, len - 2) != expected) return false;
  if (raw[0] != PROTOCOL_VERSION) return false;
  uint8_t type = raw[1];
  uint8_t controller = raw[2];
  double t;
  std::memcpy(&t, raw + 3, sizeof(double));  // little-endian host assumed (RP2040, x86)
  uint16_t payloadLen = static_cast<uint16_t>(raw[11] | (raw[12] << 8));
  if (HEADER_SIZE + payloadLen + 2 != len) return false;
  const uint8_t* payload = raw + HEADER_SIZE;

  if (hasSession_ && controller != controller_ && type != FRAME_SESSION) {
    return true;  // frame for another controller on a shared bus: ignore
  }
  lastT_ = t;
  lastFrameType_ = type;
  switch (type) {
    case FRAME_SESSION:
      controller_ = controller;
      return applySession(payload, payloadLen);
    case FRAME_KEYFRAME:
      return applyKeyframe(payload, payloadLen);
    case FRAME_DELTA:
      return applyDelta(payload, payloadLen);
    default:
      return false;
  }
}

bool Decoder::applySession(const uint8_t* payload, size_t len) {
  if (len < 1) return false;
  size_t off = 0;
  uint8_t nChannels = payload[off++];
  channels_.clear();
  channelIds_.clear();
  nActive_ = 0;
  for (uint8_t c = 0; c < nChannels; c++) {
    if (off + 3 > len) return false;
    uint8_t id = payload[off];
    uint16_t length = static_cast<uint16_t>(payload[off + 1] | (payload[off + 2] << 8));
    off += 3;
    if (off + static_cast<size_t>(length) * 2 > len) return false;
    ChannelState channel;
    channel.length = length;
    channel.kinds.resize(length);
    channel.weights.resize(length);
    // Reserve up front: push_back's doubling would otherwise churn through
    // several times this much memory on a long strip. length is already
    // bounded by the frame size checked above.
    channel.activePositions.reserve(length);
    channel.base = static_cast<uint32_t>(nActive_);
    for (uint16_t i = 0; i < length; i++) {
      channel.kinds[i] = payload[off + i * 2];
      channel.weights[i] = payload[off + i * 2 + 1];
      if (channel.kinds[i] == KIND_ACTIVE) channel.activePositions.push_back(i);
    }
    off += static_cast<size_t>(length) * 2;
    nActive_ += channel.activePositions.size();
    channels_.push_back(std::move(channel));
    channelIds_.push_back(id);
  }
  if (off + 4 > len) return false;

  // Refuse a geometry too large to hold before sizing q_/v_ off it. At 24
  // bytes per light these are by far the biggest allocations the decoder
  // makes, and on a 264KB part the failure is not graceful -- it hangs the
  // board mid-SESSION with USB half-enumerated, needing a physical replug.
  // Drop to the onboard test pattern instead, so the board stays responsive
  // and visibly reports that it has no usable geometry.
  if (nActive_ > MAX_ACTIVE_LIGHTS) {
    channels_.clear();
    channelIds_.clear();
    q_.clear();
    v_.clear();
    nActive_ = 0;
    hasSession_ = false;
    synced_ = false;
    testPattern_ = true;
    return false;
  }

  brightness_ = payload[off];
  colorCorrection_[0] = payload[off + 1];
  colorCorrection_[1] = payload[off + 2];
  colorCorrection_[2] = payload[off + 3];
  q_.assign(nActive_ * 3, 0);
  v_.assign(nActive_ * 3, 0);
  hasSession_ = true;
  synced_ = false;
  testPattern_ = false;
  return true;
}

bool Decoder::applyKeyframe(const uint8_t* payload, size_t len) {
  if (!hasSession_ || len != nActive_ * 2) return false;
  for (size_t i = 0; i < nActive_; i++) {
    uint16_t word = static_cast<uint16_t>(payload[i * 2] | (payload[i * 2 + 1] << 8));
    q_[i * 3 + 0] = ((word >> 11) & 31) << 1;
    q_[i * 3 + 1] = ((word >> 7) & 15) << 1;
    q_[i * 3 + 2] = (word & 127) << 1;
    v_[i * 3 + 0] = v_[i * 3 + 1] = v_[i * 3 + 2] = 0;
  }
  synced_ = true;
  return true;
}

bool Decoder::applyDelta(const uint8_t* payload, size_t len) {
  if (!hasSession_ || len < 2) return false;
  uint16_t nOps = static_cast<uint16_t>(payload[0] | (payload[1] << 8));
  size_t off = 2;

  // Bound the op count before allocating from it. Positions are strictly
  // ascending and must each be < nActive_, so more ops than active lights is
  // never valid; without this a frame claiming nOps=65535 asks for ~1MB on a
  // 264KB part, and the allocation failure aborts the firmware.
  if (nOps > nActive_) return false;

  // Parse ops first (positions ascending), then run the shared frame step.
  std::vector<int32_t> positions(nOps);
  std::vector<int32_t> corrections(static_cast<size_t>(nOps) * 3);
  int32_t prev = -1;
  for (uint16_t opIdx = 0; opIdx < nOps; opIdx++) {
    uint32_t skip = 0;
    int shift = 0;
    for (;;) {
      if (off >= len) return false;
      uint8_t byte = payload[off++];
      skip |= static_cast<uint32_t>(byte & 0x7F) << shift;
      if (!(byte & 0x80)) break;
      shift += 7;
      if (shift > 28) return false;
    }
    if (off + 2 > len) return false;
    uint16_t word = static_cast<uint16_t>(payload[off] | (payload[off + 1] << 8));
    off += 2;
    int32_t pos = prev + 1 + static_cast<int32_t>(skip);
    if (pos < 0 || static_cast<size_t>(pos) >= nActive_) return false;
    positions[opIdx] = pos;
    prev = pos;
    int32_t mL = (word >> 11) & 15;
    int32_t mC = (word >> 7) & 7;
    int32_t mH = word & 63;
    corrections[opIdx * 3 + 0] = ((word >> 15) & 1) ? -mL : mL;
    corrections[opIdx * 3 + 1] = ((word >> 10) & 1) ? -mC : mC;
    corrections[opIdx * 3 + 2] = ((word >> 6) & 1) ? -mH : mH;
  }
  if (off != len) return false;

  // The normative frame step (spec §11.5.4): coast, correct, blend velocity.
  size_t opCursor = 0;
  for (size_t i = 0; i < nActive_; i++) {
    int32_t qL = q_[i * 3], qC = q_[i * 3 + 1], qH = q_[i * 3 + 2];
    int32_t pL = clampi(qL + ((v_[i * 3] + 4) >> 3), 0, 63);
    int32_t pC = clampi(qC + ((v_[i * 3 + 1] + 4) >> 3), 0, 31);
    int32_t pH = hueMod(qH + ((v_[i * 3 + 2] + 4) >> 3));
    if (opCursor < positions.size() && positions[opCursor] == static_cast<int32_t>(i)) {
      pL = clampi(pL + corrections[opCursor * 3 + 0], 0, 63);
      pC = clampi(pC + corrections[opCursor * 3 + 1], 0, 31);
      pH = hueMod(pH + corrections[opCursor * 3 + 2]);
      opCursor++;
    }
    int32_t dL = pL - qL;
    int32_t dC = pC - qC;
    int32_t dH = hueWrapDiff(pH, qH);
    v_[i * 3 + 0] += ((dL << 3) - v_[i * 3 + 0]) >> 2;
    v_[i * 3 + 1] += ((dC << 3) - v_[i * 3 + 1]) >> 2;
    v_[i * 3 + 2] += ((dH << 3) - v_[i * 3 + 2]) >> 2;
    q_[i * 3 + 0] = pL;
    q_[i * 3 + 1] = pC;
    q_[i * 3 + 2] = pH;
  }
  return true;
}

const ChannelState* Decoder::channel(uint8_t id) const {
  for (size_t i = 0; i < channelIds_.size(); i++) {
    if (channelIds_[i] == id) return &channels_[i];
  }
  return nullptr;
}

uint16_t Decoder::stripLength(uint8_t id) const {
  const ChannelState* ch = channel(id);
  return ch ? ch->length : 0;
}

// -------------------------------------------------- fixed-point color path

// Q14 tables (spec §13.4.1), built lazily; boot-time float math is fine.
namespace {
int32_t g_cos_q14[257];   // 257th entry duplicates [0] for interpolation
int32_t g_lq14_of_ql[64];
int32_t g_cq14_of_qc[32];
uint8_t g_gamma_lut[4097];  // linear Q14 (>>2) -> gamma sRGB8
bool g_tablesReady = false;

// OKLab matrices in Q14 (spec §8.4.1).
constexpr int32_t M_L2LMS[9] = {16384, 6494,  3536,
                                16384, -1730, -1046,
                                16384, -1466, -21160};
constexpr int32_t M_LMS2RGB[9] = {66793, -54194, 3784,
                                  -20782, 42758, -5592,
                                  -69,   -11525, 27978};

// M_PI is a POSIX/GNU extension, not standard C++: it is absent under a
// strict -std=c++17 host build (e.g. MinGW-w64, MSVC). Define it locally so
// the core compiles on every conformance-test toolchain. The expression in
// buildTables() is left unchanged, so the tables stay bit-identical.
constexpr double kPi = 3.14159265358979323846;

void buildTables() {
  if (g_tablesReady) return;
  for (int h = 0; h < 256; h++) {
    g_cos_q14[h] =
        static_cast<int32_t>(lround(cos(2.0 * kPi * h / 256.0) * 16384.0));
  }
  g_cos_q14[256] = g_cos_q14[0];
  for (int i = 0; i < 64; i++) {
    g_lq14_of_ql[i] = static_cast<int32_t>(lround(i / 63.0 * 16384.0));
  }
  for (int i = 0; i < 32; i++) {
    g_cq14_of_qc[i] = static_cast<int32_t>(lround(i / 31.0 * 0.4 * 16384.0));
  }
  for (int i = 0; i <= 4096; i++) {
    double linear = i * 4.0 / 16384.0;
    if (linear > 1.0) linear = 1.0;
    double s = linear <= 0.0031308 ? 12.92 * linear
                                   : 1.055 * pow(linear, 1.0 / 2.4) - 0.055;
    if (s < 0) s = 0;
    if (s > 1) s = 1;
    g_gamma_lut[i] = static_cast<uint8_t>(lround(255.0 * s));
  }
  g_tablesReady = true;
}

inline int32_t cosInterp_q14(int32_t h_88) {
  // h_88 is hue in 8.8 fixed point on the 0..256 ring.
  int32_t idx = (h_88 >> 8) & 255;
  int32_t frac = h_88 & 255;
  int32_t a = g_cos_q14[idx];
  int32_t b = g_cos_q14[idx + 1];
  return a + (((b - a) * frac) >> 8);
}

inline int32_t cube_q14(int32_t x) {
  int64_t xx = (static_cast<int64_t>(x) * x) >> 14;
  return static_cast<int32_t>((xx * x) >> 14);
}

inline uint8_t gammaEncode(int64_t linear_q14, uint8_t scale1, uint8_t scale2) {
  if (linear_q14 < 0) linear_q14 = 0;
  // brightness and per-channel correction in linear space (spec §8.4.3)
  linear_q14 = (linear_q14 * scale1) >> 8;
  linear_q14 = (linear_q14 * scale2) >> 8;
  if (linear_q14 > 16384) linear_q14 = 16384;
  return g_gamma_lut[linear_q14 >> 2];
}
}  // namespace

void oklchQ14ToRgb8(int32_t l_q14, int32_t c_q14, int32_t h_88,
                    uint8_t brightness, const uint8_t correction[3],
                    uint8_t out[3]) {
  buildTables();
  int32_t cosH = cosInterp_q14(h_88);
  int32_t sinH = cosInterp_q14(((64 << 8) - h_88) & 0xFFFF);  // sin x = cos(64-x)
  int32_t a = static_cast<int32_t>((static_cast<int64_t>(c_q14) * cosH) >> 14);
  int32_t b = static_cast<int32_t>((static_cast<int64_t>(c_q14) * sinH) >> 14);

  int32_t lms[3];
  for (int i = 0; i < 3; i++) {
    int64_t acc = static_cast<int64_t>(M_L2LMS[i * 3]) * l_q14 +
                  static_cast<int64_t>(M_L2LMS[i * 3 + 1]) * a +
                  static_cast<int64_t>(M_L2LMS[i * 3 + 2]) * b;
    lms[i] = cube_q14(static_cast<int32_t>(acc >> 14));
  }
  for (int i = 0; i < 3; i++) {
    int64_t acc = static_cast<int64_t>(M_LMS2RGB[i * 3]) * lms[0] +
                  static_cast<int64_t>(M_LMS2RGB[i * 3 + 1]) * lms[1] +
                  static_cast<int64_t>(M_LMS2RGB[i * 3 + 2]) * lms[2];
    out[i] = gammaEncode(acc >> 14, brightness, correction[i]);
  }
}

uint16_t Decoder::stripRGB(uint8_t id, uint8_t* rgb, uint16_t maxPixels) const {
  const ChannelState* ch = channel(id);
  if (ch == nullptr) return 0;
  buildTables();

  // Never write past the caller's buffer: ch->length comes from the SESSION
  // frame and applySession() bounds it only by the frame size, so a strip
  // longer than the caller's buffer (a real geometry with long runs, or a
  // garbled-but-CRC-valid SESSION) would otherwise overrun it.
  const uint16_t limit = ch->length < maxPixels ? ch->length : maxPixels;

  // Active slot lookup by strip position (linear scan cursor: positions are
  // ascending, and we walk the strip in order — O(length) total).
  size_t activeCursor = 0;
  for (uint16_t pos = 0; pos < limit; pos++) {
    uint8_t* out = rgb + static_cast<size_t>(pos) * 3;
    uint8_t kind = ch->kinds[pos];
    if (kind == KIND_INACTIVE) {
      out[0] = out[1] = out[2] = 0;
      continue;
    }
    if (kind == KIND_ACTIVE) {
      size_t slot = ch->base + activeCursor;
      activeCursor++;
      oklchQ14ToRgb8(g_lq14_of_ql[q_[slot * 3]], g_cq14_of_qc[q_[slot * 3 + 1]],
                     q_[slot * 3 + 2] << 8, brightness_, colorCorrection_, out);
      continue;
    }
    // INTERPOLATED: bounding actives are the cursor's neighbors.
    if (activeCursor == 0 || activeCursor >= ch->activePositions.size()) {
      out[0] = out[1] = out[2] = 0;  // loader forbids this; be safe on wire
      continue;
    }
    size_t prevSlot = ch->base + activeCursor - 1;
    size_t nextSlot = ch->base + activeCursor;
    int32_t w = ch->weights[pos];  // 0..255
    int32_t lA = g_lq14_of_ql[q_[prevSlot * 3]];
    int32_t lB = g_lq14_of_ql[q_[nextSlot * 3]];
    int32_t cA = g_cq14_of_qc[q_[prevSlot * 3 + 1]];
    int32_t cB = g_cq14_of_qc[q_[nextSlot * 3 + 1]];
    int32_t l_q14 = lA + static_cast<int32_t>((static_cast<int64_t>(lB - lA) * w) >> 8);
    int32_t c_q14 = cA + static_cast<int32_t>((static_cast<int64_t>(cB - cA) * w) >> 8);
    // OKLCH shortest-arc hue in 8.8 fixed point (spec §13.5.1).
    int32_t hA = q_[prevSlot * 3 + 2];
    int32_t dH = hueWrapDiff(q_[nextSlot * 3 + 2], hA);
    int32_t h_88 = ((hA << 8) + dH * w) & 0xFFFF;
    oklchQ14ToRgb8(l_q14, c_q14, h_88, brightness_, colorCorrection_, out);
  }
  return limit;
}

// -------------------------------------------------------- onboard fallback

void testPatternRGB(uint8_t channel, uint8_t* rgb, uint16_t nPixels,
                    uint32_t timeMs) {
  buildTables();

  constexpr int32_t SPACING = 12;  // pixels from one bead to the next
  constexpr int32_t WIDTH = 4;     // lit pixels per bead
  // Lightness across a bead in Q14: dim leading edge, bright core, short tail,
  // so the beads read as moving rather than as a static dashed line.
  constexpr int32_t PROFILE[WIDTH] = {4500, 14000, 11500, 5500};
  constexpr int32_t CHROMA_Q14 = 5200;  // vivid but inside the OKLCH palette

  static const uint8_t correction[3] = {255, 255, 255};

  // One pixel of travel every 40ms (~25 px/s). Each channel is offset around
  // the bead lattice so the eight outputs can be told apart on sight -- useful
  // when what you are checking is that channel N drives the strip you think.
  const int32_t travel =
      static_cast<int32_t>((timeMs / 40) % static_cast<uint32_t>(SPACING));
  const int32_t offset = (travel + static_cast<int32_t>(channel) * 3) % SPACING;

  for (uint16_t i = 0; i < nPixels; i++) {
    uint8_t* out = rgb + static_cast<size_t>(i) * 3;
    // + SPACING keeps this non-negative for every i and offset.
    const int32_t rel = (static_cast<int32_t>(i) + SPACING - offset) % SPACING;
    if (rel >= WIDTH) {
      out[0] = out[1] = out[2] = 0;
      continue;
    }
    // Rainbow along the strip (full sweep every 64px), scrolling with time.
    const int32_t hue =
        (static_cast<int32_t>(i) * 4 + static_cast<int32_t>(timeMs / 16)) & 255;
    oklchQ14ToRgb8(PROFILE[rel], CHROMA_Q14, hue << 8, 255, correction, out);
  }
}

// ---------------------------------------------------------- outbound frames

static size_t buildFrame(uint8_t type, uint8_t controller, uint8_t out[64]) {
  uint8_t raw[HEADER_SIZE + 2];
  raw[0] = PROTOCOL_VERSION;
  raw[1] = type;
  raw[2] = controller;
  double t = 0.0;
  std::memcpy(raw + 3, &t, sizeof(double));
  raw[11] = 0;
  raw[12] = 0;
  uint16_t crc = crc16(raw, HEADER_SIZE);
  raw[HEADER_SIZE] = static_cast<uint8_t>(crc & 0xFF);
  raw[HEADER_SIZE + 1] = static_cast<uint8_t>(crc >> 8);
  size_t encoded = cobsEncode(raw, sizeof(raw), out);
  out[encoded] = 0;
  return encoded + 1;
}

size_t buildHello(uint8_t controller, uint8_t out[64]) {
  return buildFrame(FRAME_HELLO, controller, out);
}

size_t buildResync(uint8_t controller, uint8_t out[64]) {
  return buildFrame(FRAME_RESYNC, controller, out);
}

}  // namespace lumicodec

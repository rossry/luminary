// Luminary wire decoder + fixed-point color pipeline — C++ core (spec §13).
//
// Plain C++17 with no Arduino dependencies so it host-compiles for the golden
// vector conformance tests (spec §11.9, §17.2.5). The Arduino sketch in
// src/main.cpp wraps this with serial I/O and NeoPXL8 output.
//
// Mirrors luminary/comms/{protocol,predictor}.py bit-for-bit: int32
// arithmetic, arithmetic shifts, hue on the mod-256 ring (spec §11.5.4).

#pragma once

#include <cstddef>
#include <cstdint>
#include <vector>

namespace lumicodec {

constexpr uint8_t PROTOCOL_VERSION = 1;
constexpr uint8_t FRAME_SESSION = 0;
constexpr uint8_t FRAME_KEYFRAME = 1;
constexpr uint8_t FRAME_DELTA = 2;
constexpr uint8_t FRAME_HELLO = 3;
constexpr uint8_t FRAME_RESYNC = 4;

constexpr uint8_t KIND_ACTIVE = 0;
constexpr uint8_t KIND_INTERPOLATED = 1;
constexpr uint8_t KIND_INACTIVE = 2;

constexpr size_t HEADER_SIZE = 13;  // u8 ver, u8 type, u8 ctrl, f64 t, u16 len
constexpr size_t MAX_FRAME = 16384; // decoded frame ceiling (RAM guard)

uint16_t crc16(const uint8_t* data, size_t len);

// COBS-decode in[0..len) (no 0x00 inside) into out; returns decoded length,
// or 0 on malformed input. out must hold at least len bytes.
size_t cobsDecode(const uint8_t* in, size_t len, uint8_t* out);

struct ChannelState {
  uint16_t length = 0;
  std::vector<uint8_t> kinds;
  std::vector<uint8_t> weights;
  std::vector<uint16_t> activePositions;
  uint32_t base = 0;  // first active-slot index of this channel
};

class Decoder {
 public:
  Decoder();

  // Feed raw stream bytes (COBS frames + 0x00 delimiters). Returns the
  // number of frames applied. Corrupt frames set wantResync().
  int feed(const uint8_t* data, size_t len);

  bool hasSession() const { return hasSession_; }
  bool synced() const { return synced_; }
  bool wantResync() const { return wantResync_; }
  void clearResync() { wantResync_ = false; }
  uint8_t lastFrameType() const { return lastFrameType_; }
  double lastT() const { return lastT_; }
  uint8_t controllerId() const { return controller_; }

  size_t nActive() const { return nActive_; }
  const int32_t* q() const { return q_.data(); }  // nActive*3: qL,qC,qH

  uint8_t nChannels() const { return static_cast<uint8_t>(channels_.size()); }
  uint16_t stripLength(uint8_t channel) const;

  // Full-strip gamma sRGB8 with on-device interpolation (spec §13.5) and
  // brightness/color-correction (spec §8.4.3). rgb must hold 3*stripLength.
  // Returns the strip length written (0 for unknown channel).
  uint16_t stripRGB(uint8_t channel, uint8_t* rgb) const;

 private:
  bool decodeFrame(const uint8_t* raw, size_t len);
  bool applySession(const uint8_t* payload, size_t len);
  bool applyKeyframe(const uint8_t* payload, size_t len);
  bool applyDelta(const uint8_t* payload, size_t len);
  const ChannelState* channel(uint8_t id) const;

  std::vector<uint8_t> pending_;  // bytes of the current COBS chunk
  std::vector<ChannelState> channels_;
  std::vector<uint8_t> channelIds_;
  std::vector<int32_t> q_;
  std::vector<int32_t> v_;
  size_t nActive_ = 0;
  uint8_t controller_ = 0;
  uint8_t brightness_ = 255;
  uint8_t colorCorrection_[3] = {255, 255, 255};
  bool hasSession_ = false;
  bool synced_ = false;
  bool wantResync_ = false;
  uint8_t lastFrameType_ = 0xFF;
  double lastT_ = 0.0;
};

// Fixed-point OKLCH -> gamma sRGB8 (spec §13.4). Q14 L/C with an 8.8
// fixed-point hue index into an interpolated cos/sin table; brightness and
// per-channel correction are u8 multipliers applied in linear space.
// Exposed for the host tolerance test against the Python float reference.
void oklchQ14ToRgb8(int32_t l_q14, int32_t c_q14, int32_t h_88,
                    uint8_t brightness, const uint8_t correction[3],
                    uint8_t out[3]);

// Build a HELLO frame into out (>= 64 bytes); returns its length (spec §13.3).
size_t buildHello(uint8_t controller, uint8_t out[64]);

// Build a RESYNC frame into out (>= 64 bytes); returns its length.
size_t buildResync(uint8_t controller, uint8_t out[64]);

}  // namespace lumicodec

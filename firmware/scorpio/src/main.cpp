// Luminary Scorpio firmware (spec §13): serial wire in, NeoPXL8 out.
//
// Reads COBS-framed codec frames from USB serial, decodes with lumicodec,
// reconstructs interpolated lights, converts OKLCH -> gamma sRGB8 in fixed
// point, and writes the eight parallel strip buffers.
//
// Build with PlatformIO (see platformio.ini) or the Arduino IDE with the
// Adafruit_NeoPXL8 library installed. Host-side conformance tests for the
// decoder core live in firmware/test/host (spec §17.2.5).

#ifdef ARDUINO

#include <Adafruit_NeoPXL8.h>
#include <Arduino.h>

#include "lumicodec.h"

// Controller identity: set per board at flash time (spec §6.2.1).
#ifndef LUMINARY_CONTROLLER_ID
#define LUMINARY_CONTROLLER_ID 0
#endif

// SCORPIO's eight level-shifted outputs are GPIO 16-23.
static int8_t PINS[8] = {16, 17, 18, 19, 20, 21, 22, 23};
// Every show() stages and clocks out this many pixels on all eight outputs
// regardless of how many the loaded geometry uses, so this constant sets the
// per-frame cost outright and is the single biggest lever on frame rate:
// 360 px is 360*24 bits at 1.25 us = 10.8 ms of DMA plus proportional
// staging, 180 px is half that. Set it to the longest strip actually
// installed -- overshooting costs frame rate for pixels that do not exist.
#ifndef LUMINARY_MAX_PER_STRIP
#define LUMINARY_MAX_PER_STRIP 360
#endif
static const uint16_t MAX_PER_STRIP = LUMINARY_MAX_PER_STRIP;

static Adafruit_NeoPXL8 pixels(MAX_PER_STRIP, PINS, NEO_GRB);
static lumicodec::Decoder decoder;
static uint8_t rgbBuffer[MAX_PER_STRIP * 3];
static uint8_t serialBuffer[512];
static uint8_t outFrame[64];
static bool dirty = false;
static uint32_t lastShowMs = 0;
static uint32_t ackedFrames = 0;

void setup() {
  Serial.begin(2000000);
  // Single-buffered deliberately. Double buffering (begin(true) plus a
  // split stage()/show()) was measured and gave no frame-rate gain -- the
  // per-frame CPU cost already exceeds the DMA time, so there is nothing
  // left to overlap -- and the board wedged under sustained load with it
  // enabled where the same test had run clean without. Not re-enabled
  // without a repeat of that overdrive test.
  pixels.begin();
  pixels.show();  // all off
  size_t helloLen = lumicodec::buildHello(LUMINARY_CONTROLLER_ID, outFrame);
  Serial.write(outFrame, helloLen);
}

void loop() {
  int available = Serial.available();
  while (available > 0) {
    int toRead = min(available, (int)sizeof(serialBuffer));
    int got = Serial.readBytes(serialBuffer, toRead);
    if (got <= 0) break;
    if (decoder.feed(serialBuffer, got) > 0) dirty = true;
    available -= got;
  }

  if (decoder.wantResync()) {
    decoder.clearResync();
    size_t len = lumicodec::buildResync(LUMINARY_CONTROLLER_ID, outFrame);
    Serial.write(outFrame, len);
  }

  // Repaint at most every 15 ms. The test pattern is self-driven, so it
  // repaints on the timer alone; decoded frames repaint only when new data
  // has landed.
  //
  // canShow() gates on the previous DMA having finished. Without it, show()
  // busy-waits inside the library (while (sending);) and the loop stops
  // draining USB for the rest of the transfer. Skipping the repaint instead
  // costs a frame of latency and keeps the serial side responsive.
  uint32_t now = millis();
  bool testMode = decoder.testPatternActive();
  bool due = testMode || (dirty && decoder.synced());
  if (due && now - lastShowMs >= 15 && pixels.canShow()) {
    dirty = false;
    lastShowMs = now;
    for (uint8_t channel = 0; channel < 8; channel++) {
      // Bound by the buffer, not by the wire's declared strip length: a
      // longer strip is clamped here rather than overrunning rgbBuffer.
      uint16_t length;
      if (testMode) {
        length = MAX_PER_STRIP;
        lumicodec::testPatternRGB(channel, rgbBuffer, length, now);
      } else {
        length = decoder.stripRGB(channel, rgbBuffer, MAX_PER_STRIP);
      }
      for (uint16_t i = 0; i < length; i++) {
        pixels.setPixelColor(
            (uint32_t)channel * MAX_PER_STRIP + i,
            rgbBuffer[i * 3], rgbBuffer[i * 3 + 1], rgbBuffer[i * 3 + 2]);
      }
    }
    pixels.show();
  }

  // Flow control (spec §11.7.6). Acknowledge after the repaint, so an ACK
  // means a whole consume-and-render cycle finished, not merely that bytes
  // were parsed -- the sender paces on this, and pacing on decode alone would
  // let it run ahead of the strips. One ACK per changed count, so an idle
  // board is silent and a busy one self-limits to its actual loop rate.
  uint32_t consumed = decoder.framesApplied();
  if (consumed != ackedFrames) {
    ackedFrames = consumed;
    size_t len = lumicodec::buildAck(LUMINARY_CONTROLLER_ID, decoder.lastT(),
                                     outFrame);
    Serial.write(outFrame, len);
  }
}

#endif  // ARDUINO

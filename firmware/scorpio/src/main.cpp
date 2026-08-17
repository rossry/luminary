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
static uint32_t lastHelloMs = 0;
static uint32_t ackedFrames = 0;

// Host-silence fallback (spec §11.7.7): a crashed server otherwise leaves
// the last frame lit forever -- indistinguishable from working, at full
// power draw. After this long without a frame, fade to black over ~2 s.
// The rainbow test pattern is NOT used here; it keeps its one meaning,
// "no usable geometry loaded". Frames resuming restore output immediately.
static const uint32_t SILENCE_TIMEOUT_MS = 60000;
static uint32_t lastFrameMs = 0;
static uint32_t framesSeen = 0;
static uint16_t fadeScale = 256;  // 256 = full brightness, 0 = black

// Never block on outbound. USB-CDC writes can stall when the host stops
// reading while keeping the port open (a frozen server); a blocked write
// here would starve the loop and eventually trip the watchdog for no fault
// of the board's. Dropped ACKs are safe -- they are cumulative (spec
// §11.7.6.1) -- and HELLO/RESYNC both repeat by design.
static void writeIfRoom(const uint8_t* data, size_t len) {
  if (static_cast<size_t>(Serial.availableForWrite()) >= len) {
    Serial.write(data, len);
  }
}

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
  // Hardware watchdog (spec §11.7.7): a hang anywhere in this loop becomes
  // an automatic reboot instead of a dark board needing a physical replug.
  // The sender re-uploads SESSION when the rebooted board says HELLO or
  // reconnects, so recovery is end-to-end automatic. 8 s is far above any
  // legitimate loop() iteration (the longest blocking step, show()'s DMA
  // wait, is ~11 ms).
  rp2040.wdt_begin(8000);
}

void loop() {
  rp2040.wdt_reset();
  int available = Serial.available();
  while (available > 0) {
    int toRead = min(available, (int)sizeof(serialBuffer));
    int got = Serial.readBytes(serialBuffer, toRead);
    if (got <= 0) break;
    if (decoder.feed(serialBuffer, got) > 0) dirty = true;
    available -= got;
  }

  // HELLO (spec §13.3). setup() runs before USB-CDC enumerates, so the boot
  // HELLO is written into a void and no host has ever received one -- the
  // sender then blocks its whole hello_timeout at startup for nothing.
  // Repeat until the first frame arrives, which is the only evidence that a
  // host is actually listening.
  if (decoder.framesApplied() == 0 && millis() - lastHelloMs >= 250) {
    lastHelloMs = millis();
    size_t len = lumicodec::buildHello(LUMINARY_CONTROLLER_ID, outFrame);
    writeIfRoom(outFrame, len);
  }

  if (decoder.wantResync()) {
    decoder.clearResync();
    size_t len = lumicodec::buildResync(LUMINARY_CONTROLLER_ID, outFrame);
    writeIfRoom(outFrame, len);
  }

  // Repaint at most every 15 ms. The test pattern is self-driven, so it
  // repaints on the timer alone; decoded frames only when new data landed.
  //
  // canShow() gates the whole repaint deliberately, keeping the colour
  // conversion strictly *after* the previous transfer rather than during it.
  // Overlapping the two looks like free parallelism and measures worse --
  // 24.0 fps against 27.8 at 6x360 -- because the DMA and the CPU contend
  // for the same banked SRAM, so the conversion stalls more than the
  // serialisation costs. Double-buffering (begin(true) + split stage/show)
  // was tried for the same reason and also gave nothing. Re-measure before
  // trying either again.
  //
  // Without the gate, show() busy-waits inside the library
  // (while (sending);) and the loop stops draining USB mid-transfer.
  uint32_t now = millis();

  // Track frame arrival for the silence fallback. Restoring fadeScale on
  // resumption forces one repaint (dirty) so brightness snaps back even if
  // the resumed frame changed nothing.
  uint32_t consumedNow = decoder.framesApplied();
  if (consumedNow != framesSeen) {
    framesSeen = consumedNow;
    lastFrameMs = now;
    if (fadeScale != 256) {
      fadeScale = 256;
      dirty = true;
    }
  }
  bool silent = framesSeen > 0 && decoder.hasSession() &&
                (now - lastFrameMs) >= SILENCE_TIMEOUT_MS;
  bool fading = silent && fadeScale > 0;

  bool testMode = decoder.testPatternActive();
  bool due = testMode || fading || (dirty && decoder.synced());
  if (due && now - lastShowMs >= 15 && pixels.canShow()) {
    dirty = false;
    lastShowMs = now;
    if (fading) {
      // 256 -> 0 in steps of 2 at the 15 ms repaint gate: ~1.9 s fade.
      fadeScale = (fadeScale >= 2) ? fadeScale - 2 : 0;
    }
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
      const uint32_t scale = fadeScale;  // 256 is exact identity (x*256>>8)
      for (uint16_t i = 0; i < length; i++) {
        pixels.setPixelColor(
            (uint32_t)channel * MAX_PER_STRIP + i,
            (uint8_t)((rgbBuffer[i * 3] * scale) >> 8),
            (uint8_t)((rgbBuffer[i * 3 + 1] * scale) >> 8),
            (uint8_t)((rgbBuffer[i * 3 + 2] * scale) >> 8));
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
    writeIfRoom(outFrame, len);
  }
}

#endif  // ARDUINO

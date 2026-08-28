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

#include <cstring>
#include <vector>

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

// Strip byte order, as a build flag so a differing batch is a rebuild and
// not a code change. Verified against the physical strip by the solid-colour
// cycle (firmware-intended R->G->B observed as R->G->B): WS2812B is GRB.
// If a strip shows red and green swapped, it wants -DLUMINARY_COLOR_ORDER=NEO_RGB.
#ifndef LUMINARY_COLOR_ORDER
#define LUMINARY_COLOR_ORDER NEO_GRB
#endif
static Adafruit_NeoPXL8 pixels(MAX_PER_STRIP, PINS, LUMINARY_COLOR_ORDER);
static lumicodec::Decoder decoder;
static uint8_t rgbBuffer[MAX_PER_STRIP * 3];
// Play-out queue of staged frames (spec 13.10). Staging is decoupled from
// the DMA by buffers of our own: writing straight into NeoPXL8's pixel buffer
// means staging cannot begin until the transfer reading it has finished,
// which serialises DMA (10.8 ms at 360 px) with staging and cost
// 59.0 -> 46.9 fps at 8x360. These are ours, deliberately not NeoPXL8's
// internal double buffering -- that was measured before, gave no gain, and
// wedged the board under load.
//
// Depth is what lets the display delay exceed a frame period. With a single
// slot a frame held longer than one period stalls the pipeline instead of
// buffering it (8 ms and 20 ms both measured 56 fps at 8x360, 33 ms measured
// 45); with a queue, a late arrival is absorbed instead of shown late.
//
// The queue holds staged *pixels*, not decoded state: 8.6 KB per slot at
// 360 px against 34.5 KB for a state snapshot at 2880 active, so the depth
// is affordable. Only one state snapshot is needed, since core1 converts out
// of it immediately and then frees it.
// Depth is a fixed byte budget, not a fixed slot count. A slot is a whole
// staged frame, so its size scales with MAX_PER_STRIP; holding the budget
// constant gives 8 slots on a 180 px build and 4 on a 360 px one. Eight
// 360 px slots is 69 KB, and at 8x360 the decoder already holds ~104 KB of
// state -- reserving both left a 264 KB part unable to take the SESSION at
// all. Claiming the slots from the heap at runtime instead was tried and is
// worse: when the claim fails it retries every frame and thrashes the heap.
#ifndef LUMINARY_QUEUE_DEPTH
#define LUMINARY_QUEUE_DEPTH (MAX_PER_STRIP <= 180 ? 8 : 4)
#endif
static const uint8_t QUEUE_DEPTH = LUMINARY_QUEUE_DEPTH;
static const size_t STAGE_BYTES = 8u * MAX_PER_STRIP * 3u;
static uint8_t stageQueue[LUMINARY_QUEUE_DEPTH][8 * MAX_PER_STRIP * 3];
static uint32_t stageDeadline[LUMINARY_QUEUE_DEPTH];
// Ring indices are core1-private: both ends of the queue are worked by core1,
// so the only cross-core state remains the two sequence numbers.
static uint8_t queueHead = 0;
static uint8_t queueTail = 0;
static uint8_t queueCount = 0;
static uint32_t statQueueDepthSum = 0;
static uint32_t statLateFrames = 0;
static uint8_t serialBuffer[512];
static uint8_t outFrame[64];
static uint8_t statsFrame[96];
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
static uint32_t fadeStartMs = 0;
static const uint32_t FADE_MS = 1900;  // hold-then-fade duration (spec 11.7.7)

// Per-phase instrumentation (spec 13.7). Accumulated in microseconds and
// reported once a second as a STATS frame, so optimisation work is measured
// on the board rather than inferred from ACK round trips -- those fold
// decode, render and DMA into one number and cannot say which moved.
static uint32_t statFrames = 0;
static uint32_t statDecodeUs = 0;
static uint32_t statConvertUs = 0;
static uint32_t statStageUs = 0;
static uint32_t statShowUs = 0;
static uint32_t statLoopMaxUs = 0;
static uint32_t lastStatsMs = 0;
static const uint32_t STATS_INTERVAL_MS = 1000;

// ---------------------------------------------------------------- two cores
//
// Split by determinism, not by load (spec 13.8). Core1 owns everything from
// decoded state to pixels -- colour conversion, staging, show() -- which is
// fixed-cost work against a hard deadline, and therefore schedulable. Core0
// keeps everything whose cost varies: USB, COBS, CRC, decode, the predictor,
// ACK. It has no deadline; it only has to keep core1 fed.
//
// Putting only show() on core1 was rejected: that moves the cheap part and
// leaves colour conversion -- the largest deadline-relevant cost -- on the
// core servicing USB interrupts.
//
// The handoff is a state snapshot plus two sequence numbers. Core0 publishes
// by incrementing renderSeq; core1 answers by matching renderedSeq. Core0
// only touches the snapshot (or the channel metadata, on a SESSION) while
// the two are equal, which is the whole mutual exclusion -- no locks on
// either core's hot path.
static volatile uint32_t renderSeq = 0;
static volatile uint32_t renderedSeq = 0;
static volatile uint32_t renderStartedMs = 0;
static uint32_t lastProgressSeq = 0;
static uint32_t lastProgressMs = 0;
static volatile bool renderTestMode = false;
static volatile uint32_t renderDeadline = 0;
static lumicodec::PresentationClock presentClock;
// Fixed display delay. Every board applies the same one, so it shifts the
// whole show in time without pulling the boards apart; what it buys is slack
// for a frame that arrives late. Must exceed worst-case arrival jitter, since
// a frame later than its own deadline can only be shown late.
// With a play-out queue this can exceed a frame period: 100 ms is three
// frames at 30 fps and six at 60, comfortably more than the worst arrival
// jitter measured over USB, and irrelevant as latency for an installation.
// It is still clamped to what the queue can actually hold.
#ifndef LUMINARY_PRESENT_DELAY_US
#define LUMINARY_PRESENT_DELAY_US 100000
#endif
static volatile uint16_t renderFade = 256;
static std::vector<int32_t> qSnapshot;
static uint32_t statRenderUs = 0;

static inline bool renderIdle() { return renderedSeq == renderSeq; }



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

// Decoded state -> staged pixels in `slot`. Runs on core1; does NOT show.
static void stageFrame(uint8_t slot) {
  const uint32_t started = micros();
  const bool testMode = renderTestMode;
  const uint32_t scale = renderFade;
  const uint32_t now = millis();
  for (uint8_t channel = 0; channel < 8; channel++) {
    uint16_t length;
    if (testMode) {
      length = MAX_PER_STRIP;
      const uint32_t convertStart = micros();
      lumicodec::testPatternRGB(channel, rgbBuffer, length, now);
      statConvertUs += micros() - convertStart;
    } else {
      const uint32_t convertStart = micros();
      length = decoder.stripRGBFrom(qSnapshot.data(), channel, rgbBuffer,
                                    MAX_PER_STRIP);
      statConvertUs += micros() - convertStart;
    }
    const uint32_t stageStart = micros();
    // Write NeoPXL8's buffer directly rather than one setPixelColor() call
    // per pixel -- at 8x360 that was 2880 calls of offset math per frame.
    constexpr uint8_t R_OFF = (LUMINARY_COLOR_ORDER >> 4) & 0b11;
    constexpr uint8_t G_OFF = (LUMINARY_COLOR_ORDER >> 2) & 0b11;
    constexpr uint8_t B_OFF = LUMINARY_COLOR_ORDER & 0b11;
    uint8_t* out = stageQueue[slot] + (uint32_t)channel * MAX_PER_STRIP * 3;
    for (uint16_t i = 0; i < length; i++) {
      out[R_OFF] = (uint8_t)((rgbBuffer[i * 3] * scale) >> 8);
      out[G_OFF] = (uint8_t)((rgbBuffer[i * 3 + 1] * scale) >> 8);
      out[B_OFF] = (uint8_t)((rgbBuffer[i * 3 + 2] * scale) >> 8);
      out += 3;
    }
    statStageUs += micros() - stageStart;
  }
  statRenderUs += micros() - started;
}

void setup1() {}

void loop1() {
  // Two independent steps, so work happens as soon as a frame lands but the
  // pixels appear at the scheduled instant. Boards share the frame's `t` and
  // the same delay, so they light the same frame together without ever
  // exchanging a clock.

  // Fill: stage a newly published frame while a slot is free. No canShow()
  // gate -- staging writes our own buffer and can run during the transfer.
  if (!renderIdle() && queueCount < QUEUE_DEPTH) {
    const uint32_t seq = renderSeq;
    stageDeadline[queueHead] = renderDeadline;
    stageFrame(queueHead);
    queueHead = (uint8_t)((queueHead + 1) % QUEUE_DEPTH);
    queueCount++;
    renderedSeq = seq;  // frees the state snapshot for core0
  }

  // Drain: show the oldest staged frame once its deadline arrives.
  if (queueCount == 0) return;
  // Wrap-safe comparison: micros() rolls over every ~71 minutes.
  const int32_t late = (int32_t)(micros() - stageDeadline[queueTail]);
  if (late < 0) return;
  // Never spin waiting on the DMA: core1 busy-waiting on canShow() wedged the
  // board outright and it needed a physical replug. Returning retries next
  // pass, so a transfer in flight costs a pass, not the board.
  if (!pixels.canShow()) return;
  const uint32_t showStart = micros();
  std::memcpy(pixels.getPixels(), stageQueue[queueTail], STAGE_BYTES);
  pixels.show();
  statShowUs += micros() - showStart;
  statFrames++;
  statQueueDepthSum += queueCount;
  // A frame shown more than a frame period past its deadline is one the
  // buffer failed to absorb -- the number that says whether depth is enough.
  if (presentClock.intervalUs() &&
      late > (int32_t)presentClock.intervalUs()) {
    statLateFrames++;
  }
  queueTail = (uint8_t)((queueTail + 1) % QUEUE_DEPTH);
  queueCount--;
}

void loop() {
  // Core0 pets the watchdog, so a core1 that wedged would go unnoticed. The
  // test is PROGRESS, not the age of any one frame: with a play-out queue a
  // frame is legitimately outstanding for as long as its deadline is away,
  // and an age test read that as a hang and rebooted the board mid-show.
  {
    const uint32_t seen = renderedSeq;
    if (seen != lastProgressSeq) {
      lastProgressSeq = seen;
      lastProgressMs = millis();
    }
    if (renderIdle() || (millis() - lastProgressMs) < 2000) {
      rp2040.wdt_reset();
    }
  }
  const uint32_t loopStart = micros();
  int available = Serial.available();
  while (available > 0) {
    int toRead = min(available, (int)sizeof(serialBuffer));
    int got = Serial.readBytes(serialBuffer, toRead);
    if (got <= 0) break;
    // Time the decode itself, not the loop's idle spinning: this block runs
    // far more often than a frame is shown, so anything measured from the
    // top of loop() would fold waiting-for-bytes into the decode bucket.
    const uint32_t decodeStart = micros();
    if (decoder.feed(serialBuffer, got) > 0) dirty = true;
    statDecodeUs += micros() - decodeStart;
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
    // Sample the host clock on arrival, before any of our own queuing.
    presentClock.observe(decoder.lastT(), micros());
    if (fadeScale != 256) {
      fadeScale = 256;
      dirty = true;
    }
  }
  bool silent = framesSeen > 0 && decoder.hasSession() &&
                (now - lastFrameMs) >= SILENCE_TIMEOUT_MS;
  if (!silent) fadeStartMs = now;  // reset while the stream is alive
  bool fading = silent && fadeScale > 0;

  // Hand the frame to core1 (spec 13.8). The snapshot and the channel
  // metadata may only be touched while core1 is idle, which is what makes
  // the handoff safe without locking either hot path.
  const bool testMode = decoder.testPatternActive();
  const bool due = testMode || fading || (dirty && decoder.synced());
  if (due && renderIdle()) {
    if (fading) {
      // Fade on the clock, not on the repaint count: a fixed step per
      // repaint made the fade's duration a side effect of the repaint rate.
      const uint32_t elapsed = now - fadeStartMs;
      fadeScale = (elapsed >= FADE_MS)
                      ? 0
                      : (uint16_t)(256 - (elapsed * 256) / FADE_MS);
    }
    if (!testMode) {
      const size_t words = decoder.snapshotWords();
      if (qSnapshot.size() != words) qSnapshot.assign(words, 0);
      std::memcpy(qSnapshot.data(), decoder.q(), words * sizeof(int32_t));
    }
    dirty = false;
    lastShowMs = now;
    renderTestMode = testMode;
    renderFade = fadeScale;
    renderStartedMs = now;
    renderDeadline =
        presentClock.ready()
            ? presentClock.deadline(
                  decoder.lastT(),
                  presentClock.usableDelay(LUMINARY_PRESENT_DELAY_US,
                                           QUEUE_DEPTH))
            : micros();
    renderSeq = renderSeq + 1;
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

  const uint32_t loopUs = micros() - loopStart;
  if (loopUs > statLoopMaxUs) statLoopMaxUs = loopUs;
  if (now - lastStatsMs >= STATS_INTERVAL_MS) {
    lastStatsMs = now;
    const uint32_t fields[11] = {
        statFrames,    statDecodeUs, lumicodec::g_predictUs,
        statConvertUs, statStageUs,  statShowUs,
        statLoopMaxUs, (uint32_t)decoder.nActive(),
        statQueueDepthSum, statLateFrames, (uint32_t)QUEUE_DEPTH,
    };
    size_t len = lumicodec::buildStats(LUMINARY_CONTROLLER_ID, fields, 11,
                                       statsFrame);
    if (len) writeIfRoom(statsFrame, len);
    statFrames = statDecodeUs = statConvertUs = 0;
    statStageUs = statShowUs = statLoopMaxUs = 0;
    statQueueDepthSum = statLateFrames = 0;
    lumicodec::g_predictUs = 0;
  }
}

#endif  // ARDUINO

# Luminary Scorpio firmware

Target: **Adafruit Feather RP2040 SCORPIO** (8 level-shifted parallel strip
outputs on GPIO 16–23), spec §13.

## What it does

1. Reads COBS-framed Luminary wire frames from USB-CDC serial (spec §11.7.1)
2. Decodes SESSION / KEYFRAME / DELTA with the shared `lumicodec` core —
   the same integer predictor as the Python and JS decoders (spec §11.5.4)
3. Reconstructs INTERPOLATED lights in OKLCH with shortest-arc hue (§13.5)
4. Converts OKLCH → OKLab → linear → gamma sRGB8 in Q14 fixed point with
   lookup tables (§13.4), applying brightness / color correction (§8.4.3)
5. Writes NeoPXL8's eight parallel buffers and shows
6. Sends HELLO on boot and RESYNC on CRC/framing errors (§13.3)
7. Falls back to an onboard test pattern — rainbow beads running down each
   strip — when a SESSION declares more lights than the board can hold
8. ACKs each consumed frame so the sender can bound frames in flight
   (§11.7.6) — see *Flow control* below

## Limits

Sizes that arrive on the wire are treated as untrusted, because exceeding any
of them on a 264KB part is not a graceful failure:

| Limit | Value | Behaviour when exceeded |
|---|---|---|
| Pixels per strip | `MAX_PER_STRIP`, 360 | Clamped; extra pixels stay dark |
| Active lights per SESSION | `MAX_ACTIVE_LIGHTS`, 4096 | SESSION refused, test pattern runs |
| DELTA ops per frame | `nActive` | Frame rejected, RESYNC requested |

`MAX_PER_STRIP` is a build flag (`-DLUMINARY_MAX_PER_STRIP=n`, default 360).
Every `show()` stages and clocks out that many pixels on **all eight** outputs
whatever the loaded geometry uses, so it sets the frame-rate ceiling directly
— overshooting costs frame rate for pixels that do not exist.

The active-light ceiling is the binding one: `q_` and `v_` cost 24 bytes per
light between them, so 4096 lights is ~100KB. A geometry above it is refused
outright rather than attempted — an allocation failure mid-SESSION hangs the
board with USB half-enumerated, which takes a physical replug to clear. The
test pattern is the visible signal that this happened: if the strips show
running rainbow beads instead of your pattern, the board has no usable
geometry loaded.

## Flow control

The RP2040's USB-CDC stack does **not** apply backpressure when its receive
buffer backs up — it stops responding to the host entirely, and recovery needs
the board physically reconnected. So pacing is a correctness requirement of
the transport, not a throughput optimization (spec §11.7.6).

The board ACKs each frame it consumes, identifying it by the header `t` it
echoes back. `SerialDriver` holds at most `max_in_flight` frames (default 4)
unacknowledged per controller and skips a tick outright when the window is
full. Measured on a Feather SCORPIO over a 1 ft lead:

| | |
|---|---|
| Framing the board discards without decoding | ~117 KiB/s |
| Decoded and rendered, 104-active-light geometry | ~69 KiB/s |
| ACK round trip, same geometry | 0.74 ms median |
| Unpaced overdrive, before flow control | unrecoverable stall after ~4 s |
| Same overdrive, with the window | 15 s clean at 1102 frames/s |

**The window reduces but does not eliminate the wedge.** A later repeat of
that overdrive stalled the board after ~5 s at ~1126 frames/s with the window
holding correctly (never more than 3 outstanding of 4), so sustained
high-frame-rate load can still kill it by some mechanism other than queue
depth. That run differed only in having NeoPXL8 double-buffering enabled,
which has since been reverted; the interaction is unresolved and is the first
thing to re-test.

## Performance at production sizing

Numbers above use the hex demo (104 ACTIVE, 48 px strips). Against a
6 × 360 all-ACTIVE geometry the picture is different and **30 fps is not yet
met**:

| Config | Achieved | Note |
|---|---|---|
| 6 × 360, default budget | 10.7 fps | `budget_for_baud` yields 5333 B/frame |
| 6 × 360, 800 B budget | ~21 fps | board-limited |
| ≤ 1080 px, 800 B budget | 24.6 fps | host-limited, see below |

Two independent ceilings, both open:

1. **`budget_for_baud` derives the per-frame budget from the link rate**, not
   from what the board can consume. At 2 Mbaud/30 fps it asks for 5333 bytes
   per frame, which costs the board ~86 ms each. Capping the budget by
   measured device throughput roughly doubles frame rate on its own.
2. **`SerialDriver.run` paces with `time.sleep()`**, which Windows rounds to
   ~15.6 ms granularity, capping the host at ~24.6 fps regardless of geometry
   or hardware. `_poll_inbound` also runs once per tick, so ACK latency
   measured through the driver is quantised to the tick period rather than
   reflecting the board.

Note that "180 on the wire, 360 on the strip" (every other light
INTERPOLATED) halves wire size and decode cost but **not** the repaint: the
DMA and the per-pixel colour conversion scale with physical LEDs, not with
ACTIVE ones.

## Building

With [PlatformIO](https://platformio.org): `pio run` in this directory, then
`pio run -t upload` with the board in BOOTSEL mode. Set the controller id per
board with the `controller0` / `controller1` envs (or `-DLUMINARY_CONTROLLER_ID=n`).

With the Arduino IDE: install *Adafruit NeoPXL8* (+ its NeoPixel dependency),
open `src/main.cpp` alongside `lib/lumicodec/`, select the SCORPIO board.

## Conformance tests (no hardware needed)

`firmware/test/host/` compiles `lumicodec` with plain g++ and replays the
checked-in golden vectors (spec §11.9):

    cd firmware/test/host && make && ./test_decoder ../../golden/case1

This asserts bit-exact quantized OKLCH state after every frame and RGB output
within ±2/255 of the Python float reference.

## Driving it

    python -m luminary.cli play --lights <geometry> --pattern <name> \
        --serial /dev/ttyACM0

The server negotiates nothing beyond the SESSION frame; a freshly booted
board syncs at the first keyframe (spec §11.7.3).

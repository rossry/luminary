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

The one failure ever seen with the window in place turned out to be the
NeoPXL8 double-buffering experiment, since reverted (see *Things that did not
work*). On the shipped single-buffered firmware the overdrive has now run
clean five consecutive times, ~105 s and ~150k frames total, with the board
alive after each.

## Performance

**30 fps at 6 x 360 is met**, end to end through `SerialDriver`, all lights
ACTIVE, zero RESYNC and zero window stalls:

| Config | Board ceiling | Through the driver |
|---|---|---|
| 6 x 360 all-ACTIVE | 39.1 fps | 29.91 fps |
| 6 x 360 every-other INTERPOLATED | — | 30.00 fps |
| 8 x 360 all-ACTIVE | 29.3 fps | 29.38 fps |

Getting there took four fixes, two of them worth more than the rest:

1. **The colour pipeline was doing 64-bit multiplies on a Cortex-M0+**, which
   has no 64-bit multiply — every one became an `__aeabi_lmul` call, ~20 per
   pixel. Narrowing the OKLab->LMS matrix, the a/b projection and `cube_q14`
   to int32 (proven safe by the bounds check in the host conformance test)
   took 6 x 360 from 27.8 to 38.7 fps. The LMS->RGB accumulator stays 64-bit:
   its worst case is ~2.04e9 against a 2.15e9 limit, too little margin.
2. **`SerialDriver.run` paced with `time.sleep()`**, whose granularity on
   Windows is ~15.6 ms, capping the host near 24 fps regardless of hardware.
   It now requests a 1 ms timer period and spins the last 2 ms.
3. **`_route` COBS-decoded whole frames** to read a 13-byte header. Now
   decodes the header only.
4. **HELLO was unreceivable**, so every run burned the full `hello_timeout`
   at startup. The board now repeats HELLO until its first frame arrives;
   `open()` went from 2.07 s to 0.10 s.

Per-frame cost scales as roughly **10 ms fixed + 3 ms per 360-px channel** —
the fixed part is the DMA (360 px x 24 bits x 1.25 us = 10.8 ms).

When the caller does not set `budget_bytes`, `SerialDriver` finds the
sustainable per-frame budget itself (spec §11.7.6.6): it starts at 512 and
adapts each second — shrinking when the window stalls **or** the median ACK
round trip exceeds the frame interval, growing only when round trips sit
comfortably inside it. The RTT signal is the essential one: serial writes
block when the OS buffer backs up, ACKs arrive during the blocked write, and
the window never fills — so frame rate can sink without a single stall being
recorded. Measured, default config, 30 s each:

| Geometry | fps | Budget settled at |
|---|---|---|
| 1 x 48 (hex-sized) | 29.99 | 5333 (the link-rate cap) |
| 6 x 360 | 29.89 | 512 |
| 8 x 360 | 29.69 | 384 |

An explicitly configured `budget_bytes` is respected and never adapted —
`firmware/tools/bench.py` relies on that for reproducible measurements.

Note that "180 on the wire, 360 on the strip" (every other light
INTERPOLATED) buys almost nothing — 28.4 fps against 27.8 before the int32
work. It halves wire size and decode cost, but DMA and per-pixel colour
conversion scale with *physical* LEDs.

## Things that did not work

Recorded so they are not retried blindly. Both are attempts to overlap the
DMA with CPU work, and both measured *worse* on this hardware, which points
at the RP2040's DMA and CPU contending for the same banked SRAM:

| Attempt | Result |
|---|---|
| NeoPXL8 double buffering (`begin(true)` + split `stage()`/`show()`) | No frame-rate gain, and the board wedged under sustained load where the same test ran clean without |
| Rendering during the transfer (gating only `show()` on `canShow()`) | 24.0 fps against 27.8 serial, with worse jitter (max RTT 230 ms vs 102 ms) |

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

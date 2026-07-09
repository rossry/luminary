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

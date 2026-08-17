# Firmware tools

Standalone utilities that are *not* part of the Luminary firmware build.

## `strip_diagnostic.py`

A CircuitPython strip diagnostic for the Feather RP2040 SCORPIO. It exists to
answer "is this strip wired and working at all?" without involving the wire
protocol, the codec, or a host — useful while swapping physical components,
where a dark strip could equally mean bad geometry, a bad frame, a bad data
line, or a dead LED.

Drives the chosen outputs through solid red, green and blue (one channel at a
time, so a dead colour channel is obvious), optionally followed by a single
white dot walking down the strip — which shows exactly how far data travels
before a break, and confirms data direction since the dot starts at the DIN
end. The onboard status NeoPixel animates throughout, so you can tell the
board is running even when the external strip stays dark.

Works with WS2812/WS2812B, SK6812, and the backup-data WS2813/WS2815 parts.
For a backup-data strip, feed the controller into the **primary** data input
(DIN), not the backup (BIN).

### Running it

This needs **CircuitPython**, not the PlatformIO firmware — the two cannot be
installed at once, so flashing this replaces the Luminary firmware and vice
versa.

1. Install CircuitPython for `adafruit_feather_rp2040_scorpio` (BOOTSEL, then
   copy the CircuitPython `.uf2`)
2. Copy `neopixel.mpy` from the Adafruit CircuitPython bundle into `lib/`
3. Copy this file to the `CIRCUITPY` drive as `code.py`

Edit the `CONFIG` block and save — CircuitPython auto-reloads. `NUM_PIXELS`
larger than the physical strip is harmless. Keep `BRIGHTNESS` modest (0.02 is
a sensible default) so a long strip does not overdraw its supply.

To return to Luminary firmware, flash `firmware/scorpio` normally
(`pio run -e controller0 -t upload`, or copy the `.uf2` in BOOTSEL mode);
that overwrites CircuitPython and its filesystem.

### Why it lives here

It was written on-device and existed only on the board's `CIRCUITPY`
filesystem, which is erased by any firmware flash. Checked in so it survives.

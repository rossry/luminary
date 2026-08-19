# Scorpio LED-strip diagnostic test pattern
# =========================================
# Runs on an Adafruit Feather RP2040 Scorpio under CircuitPython.
# Designed for *diagnosing* a strip while swapping components.
#
# Works with NeoPixel-protocol strips: WS2812/WS2812B, SK6812, and the
# backup-data variants WS2813 (5V) / WS2815 (12V). For a backup-data strip,
# feed the controller's data into the PRIMARY data input (DIN), not the
# backup (BIN).
#
# It drives the chosen Scorpio output(s) through 4 phases on a loop:
#   1. solid RED     (checks the R channel + that ANY data arrives)
#   2. solid GREEN   (checks the G channel)
#   3. solid BLUE    (checks the B channel)
#   4. a single white dot that WALKS down the strip slowly
#      -> shows exactly how far data travels before a break / dead pixel,
#         and confirms data direction (dot starts at the DIN end).
#
# It also animates the onboard status NeoPixel so you can confirm the
# board is running even if the external strip is dark.
#
# Tweak the CONFIG block, save, and CircuitPython auto-reloads.

import time
import board
import neopixel

# ----------------------------- CONFIG -----------------------------
NUM_PIXELS = 1000       # how many LEDs to drive per output (extra is harmless)
BRIGHTNESS = 0.6        # 0.0-1.0. Bench setting — fine for a single strip.
                        # ⚠️ Turn this down before driving the sphere. The documented cap is
                        # 0.25: "25% keeps 4x 5m @ 60/m down to 18A" — and that budget
                        # assumed 4 strips, so 8 roughly doubles the draw.
OUTPUTS    = "all"      # "all" = drive all 8 outputs, or a list like [0] or [0, 3]
PHASE_SECONDS = 1       # seconds per solid-color phase
DOT_STEP_SECONDS = 0.04 # how fast the walking dot moves
# ------------------------------------------------------------------

# onboard status pixel: proves the board is alive and running THIS code
status = None
try:
    status = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=0.3, auto_write=True)
except Exception as e:
    print("no onboard status pixel:", e)

# resolve which output pins to use
if OUTPUTS == "all":
    want = list(range(8))
else:
    want = list(OUTPUTS)

pins = []
for i in want:
    name = "NEOPIXEL%d" % i
    if hasattr(board, name):
        pins.append((name, getattr(board, name)))
if not pins:  # fallback to raw GPIO if named outputs are unavailable
    for gp in (16, 17, 18, 19, 20, 21, 22, 23):
        nm = "GP%d" % gp
        if hasattr(board, nm):
            pins.append((nm, getattr(board, nm)))

strips = []
for name, pin in pins:
    try:
        strips.append(neopixel.NeoPixel(pin, NUM_PIXELS, brightness=BRIGHTNESS,
                                        auto_write=False))
    except Exception as e:
        print("could not init", name, ":", e)

print("=== SCORPIO STRIP DIAGNOSTIC ===")
print("CircuitPython driving", len(strips), "output(s):",
      [n for n, _ in pins])
print("pixels/output:", NUM_PIXELS, " brightness:", BRIGHTNESS)
print("phases: RED -> GREEN -> BLUE -> walking white dot")


def fill(color):
    for s in strips:
        s.fill(color)
        s.show()


def phase_color(name, color, status_color):
    print("phase:", name)
    fill(color)
    end = time.monotonic() + PHASE_SECONDS
    while time.monotonic() < end:
        if status:
            status[0] = status_color
        time.sleep(0.1)


def phase_walk():
    print("phase: walking white dot (watch how far it travels)")
    for i in range(NUM_PIXELS):
        for s in strips:
            s.fill((0, 0, 0))
            s[i] = (255, 255, 255)
            s.show()
        if status:
            status[0] = (40, 40, 40)
        time.sleep(DOT_STEP_SECONDS)


while True:
    phase_color("RED",   (255, 0, 0), (60, 0, 0))
    phase_color("GREEN", (0, 255, 0), (0, 60, 0))
    phase_color("BLUE",  (0, 0, 255), (0, 0, 60))
    # phase_walk()  # walking-dot disabled — solid colors only
    print("heartbeat", round(time.monotonic(), 1), "s")

# Scorpio "Morse glyph" puzzle pattern
# ====================================
# Renders MESSAGE in Morse code SPATIALLY along the strip:
#   dot  = short lit segment (1 unit)
#   dash = long lit segment  (3 units)
#   gap between symbols = 1 dark unit, between letters = 3 dark units
# The lit segments gently pulse/shimmer in gold over a faint deep-blue
# background so it reads as decoration until someone notices the
# short/long structure and decodes it.
#
# Previous animations: code_diagnostic_backup.py, code_aurora_backup.py.
# Edit MESSAGE and save — CircuitPython auto-reloads.

import time
import math
import board
import neopixel

# ----------------------------- CONFIG -----------------------------
MESSAGE = "SPHERE"       # the puzzle answer
NUM_PIXELS = 200
BRIGHTNESS = 0.25        # power-safe cap
OUTPUTS = "all"

FG = (255, 170, 20)      # lit-segment color (gold)
BG = (0, 4, 16)          # background (very dim blue, shows strip extent)
PULSE_SPEED = 0.4        # shimmer speed; keep slow so segments stay readable
# ------------------------------------------------------------------

MORSE = {
    'A': '.-', 'B': '-...', 'C': '-.-.', 'D': '-..', 'E': '.', 'F': '..-.',
    'G': '--.', 'H': '....', 'I': '..', 'J': '.---', 'K': '-.-', 'L': '.-..',
    'M': '--', 'N': '-.', 'O': '---', 'P': '.--.', 'Q': '--.-', 'R': '.-.',
    'S': '...', 'T': '-', 'U': '..-', 'V': '...-', 'W': '.--', 'X': '-..-',
    'Y': '-.--', 'Z': '--..',
    '0': '-----', '1': '.----', '2': '..---', '3': '...--', '4': '....-',
    '5': '.....', '6': '-....', '7': '--...', '8': '---..', '9': '----.',
}

# build a unit map: list of 0/1 for dark/lit units
units = []
for li, ch in enumerate(MESSAGE.upper()):
    if ch == ' ':
        units += [0] * 4  # word gap (7 total with surrounding letter gaps)
        continue
    if li and units:
        units += [0] * 3  # letter gap
    code = MORSE.get(ch)
    if not code:
        continue
    for si, sym in enumerate(code):
        if si:
            units.append(0)  # symbol gap
        units += [1] * (1 if sym == '.' else 3)

# scale units to the strip, centered, with margins at each end
px_per_unit = max(1, NUM_PIXELS // (len(units) + 8))
used = len(units) * px_per_unit
margin = (NUM_PIXELS - used) // 2
lit = bytearray(NUM_PIXELS)
for u, on in enumerate(units):
    if on:
        for p in range(margin + u * px_per_unit,
                       margin + (u + 1) * px_per_unit):
            if 0 <= p < NUM_PIXELS:
                lit[p] = 1

print("message:", MESSAGE, "|", len(units), "units,", px_per_unit,
      "px/unit,", used, "px used")

# hardware setup
try:
    status = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=0.2, auto_write=True)
except Exception:
    status = None

want = list(range(8)) if OUTPUTS == "all" else list(OUTPUTS)
strips = []
for i in want:
    name = "NEOPIXEL%d" % i
    if hasattr(board, name):
        try:
            strips.append(neopixel.NeoPixel(getattr(board, name), NUM_PIXELS,
                                            brightness=BRIGHTNESS,
                                            auto_write=False))
        except Exception as e:
            print("could not init", name, ":", e)

while True:
    t = time.monotonic()
    # gentle traveling shimmer on the lit segments (never below 55% so
    # segment boundaries stay crisp and decodable)
    for s in strips:
        for i in range(NUM_PIXELS):
            if lit[i]:
                w = 0.775 + 0.225 * math.sin(t * 2 * math.pi * PULSE_SPEED
                                             + i * 0.15)
                s[i] = (int(FG[0] * w), int(FG[1] * w), int(FG[2] * w))
            else:
                s[i] = BG
        s.show()
    if status:
        status[0] = (20, 12, 0)
    time.sleep(0.03)

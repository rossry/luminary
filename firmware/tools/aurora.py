# Scorpio "aurora comets" animation
# =================================
# A slowly drifting rainbow aurora as the base layer, with bright comets
# that periodically streak down the strip leaving fading tails, plus
# occasional white sparkles.
#
# The previous diagnostic pattern is preserved in code_diagnostic_backup.py.
#
# Brightness is kept moderate (see the power warning in the backup file:
# documented cap is 0.25 for the full sphere). Tweak CONFIG and save —
# CircuitPython auto-reloads.

import time
import random
import board
import neopixel

# ----------------------------- CONFIG -----------------------------
NUM_PIXELS = 200
BRIGHTNESS = 0.25        # power-safe cap per the sphere's documented budget
OUTPUTS = "all"          # "all" or a list like [0]

WAVE_SPEED = 0.35        # rainbow drift, hue-wheel revolutions per second
WAVE_SCALE = 1.5         # how many rainbows fit on the strip at once
COMET_EVERY = (1.5, 4.0) # seconds (min, max) between comet launches
COMET_SPEED = 140        # pixels per second
COMET_TAIL = 18          # tail length in pixels
SPARKLE_CHANCE = 0.06    # chance per frame of a new sparkle
# ------------------------------------------------------------------

# onboard status pixel
try:
    status = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=0.2, auto_write=True)
except Exception:
    status = None

# resolve output pins (same approach as the diagnostic script)
want = list(range(8)) if OUTPUTS == "all" else list(OUTPUTS)
pins = []
for i in want:
    name = "NEOPIXEL%d" % i
    if hasattr(board, name):
        pins.append(getattr(board, name))

strips = []
for pin in pins:
    try:
        strips.append(neopixel.NeoPixel(pin, NUM_PIXELS, brightness=BRIGHTNESS,
                                        auto_write=False))
    except Exception as e:
        print("could not init pin:", e)

print("aurora comets on", len(strips), "output(s),", NUM_PIXELS, "pixels")


def wheel(pos):
    # 0-255 position on the hue wheel -> (r, g, b)
    pos &= 255
    if pos < 85:
        return (255 - pos * 3, pos * 3, 0)
    if pos < 170:
        pos -= 85
        return (0, 255 - pos * 3, pos * 3)
    pos -= 170
    return (pos * 3, 0, 255 - pos * 3)


class Comet:
    def __init__(self, t):
        self.start = t
        self.forward = random.random() < 0.5

    def head(self, t):
        return (t - self.start) * COMET_SPEED


comets = []
sparkles = {}  # index -> remaining life 0.0-1.0
next_comet = time.monotonic() + 1.0
frame = bytearray(NUM_PIXELS * 3)

while True:
    t = time.monotonic()

    # launch a comet now and then
    if t >= next_comet:
        comets.append(Comet(t))
        next_comet = t + random.uniform(*COMET_EVERY)

    # base layer: drifting rainbow, dimmed so comets pop
    offset = int(t * WAVE_SPEED * 256)
    step = int(WAVE_SCALE * 256 / NUM_PIXELS) or 1
    for i in range(NUM_PIXELS):
        r, g, b = wheel(i * step + offset)
        j = i * 3
        frame[j] = r >> 2      # ~25% of the wheel color
        frame[j + 1] = g >> 2
        frame[j + 2] = b >> 2

    # comet layer: bright white-hot head, rainbow tail fading out
    for c in comets:
        head = c.head(t)
        for k in range(COMET_TAIL):
            p = int(head) - k
            if not 0 <= p < NUM_PIXELS:
                continue
            i = p if c.forward else NUM_PIXELS - 1 - p
            fade = (COMET_TAIL - k) / COMET_TAIL
            fade *= fade
            if k == 0:
                r, g, b = 255, 255, 255
            else:
                r, g, b = wheel(i * step + offset)
            j = i * 3
            frame[j] = min(255, frame[j] + int(r * fade))
            frame[j + 1] = min(255, frame[j + 1] + int(g * fade))
            frame[j + 2] = min(255, frame[j + 2] + int(b * fade))
    comets = [c for c in comets if c.head(t) - COMET_TAIL < NUM_PIXELS]

    # sparkle layer
    if random.random() < SPARKLE_CHANCE:
        sparkles[random.randrange(NUM_PIXELS)] = 1.0
    dead = []
    for i, life in sparkles.items():
        v = int(200 * life * life)
        j = i * 3
        frame[j] = min(255, frame[j] + v)
        frame[j + 1] = min(255, frame[j + 1] + v)
        frame[j + 2] = min(255, frame[j + 2] + v)
        life -= 0.08
        if life <= 0:
            dead.append(i)
        else:
            sparkles[i] = life
    for i in dead:
        del sparkles[i]

    # push the frame to every strip
    for s in strips:
        buf = s
        for i in range(NUM_PIXELS):
            j = i * 3
            buf[i] = (frame[j], frame[j + 1], frame[j + 2])
        s.show()

    if status:
        status[0] = wheel(offset)


## `color_cycle.py`

Cycles firmware-intended solid RED → GREEN → BLUE (2 s each, looping) on all
8 outputs, for verifying strip byte order by eye: a strip that disagrees with
`LUMINARY_COLOR_ORDER` shows the sequence permuted (G,R,B = the strip wants
RGB; G,B,R = BGR; and so on). Runs against the normal Luminary firmware — no
reflash needed, unlike `strip_diagnostic.py`. Defaults to 0.2 brightness,
which is ~0.2x strip current.

    python firmware/tools/color_cycle.py --port COM8

## `whoami.py`

Answers "which controller id is on this port?" Two boards enumerate with the
same VID:PID, so the mapping cannot come from enumeration; instead a
deliberately corrupt frame provokes a RESYNC, whose header carries the
board's compiled-in id. Works in any board state.

    python firmware/tools/whoami.py

## `aurora.py`, `morse_puzzle.py`

Personal CircuitPython pieces preserved off board 2 before it was reflashed
to Luminary firmware (see strip_diagnostic.py for the running-them steps):
a drifting rainbow aurora with comets, and a pattern that renders a message
in spatial Morse along the strip. Not Luminary components; kept because the
CIRCUITPY filesystem is erased by any flash. The July 2026 diagnostic
revision (now the checked-in strip_diagnostic.py) carries the installation
power budget: brightness cap 0.25 = "4x 5m @ 60/m down to 18A", and 8
strips roughly doubles that.


## `color_cycle.py`

Cycles firmware-intended solid RED → GREEN → BLUE (2 s each, looping) on all
8 outputs, for verifying strip byte order by eye: a strip that disagrees with
`LUMINARY_COLOR_ORDER` shows the sequence permuted (G,R,B = the strip wants
RGB; G,B,R = BGR; and so on). Runs against the normal Luminary firmware — no
reflash needed, unlike `strip_diagnostic.py`. Defaults to 0.2 brightness,
which is ~0.2x strip current.

    python firmware/tools/color_cycle.py --port COM8

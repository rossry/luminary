"""Ringfall: the ring motif, slowed to a toll.

A registration of the shared
:class:`~luminary.patterns.primitives.RingWave` primitive (book two) —
the same ``ring_field`` the mapping visuals use (invariant §2.9), in
spectral mode: each pass re-keys its hue to a fresh seeded angle.
"""

from luminary.patterns.primitives import RingWave


class Ringfall(RingWave):
    name = "ringfall"
    description = "A slow luminous ring tolling apex to rim, re-keyed each pass"

    notes = (
        "The ring motif slowed to a toll: one luminous band, apex to rim, "
        "thirteen seconds a descent, a fresh hue each pass."
    )

    period = 13.0
    sigma_deg = 8.0
    l_gain = 0.66

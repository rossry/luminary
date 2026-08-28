"""Starlight: a quiet field of warm stars over indigo airglow.

Book two opens with pure composition: this file is a registration of
the shared :class:`~luminary.patterns.primitives.Starfield` primitive —
tuning lives in class-attribute overrides, field math lives in the
library, written once (invariant §2.9).
"""

from luminary.patterns.primitives import Starfield


class Starlight(Starfield):
    name = "starlight"
    description = "A quiet field of warm stars over indigo airglow"

    density = 0.032
    twinkle_s = 7.0
    star_hue = 80.0

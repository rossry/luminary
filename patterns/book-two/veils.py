"""Veils: auroral curtains draped from the apex.

A registration of the shared
:class:`~luminary.patterns.primitives.AuroraVeils` primitive (book
two). Where book one's ``aurora`` paints a planar sky, this one hangs
from the sphere's own coordinates — curtains as azimuthal harmonics,
so the drape has no seam.
"""

from luminary.patterns.primitives import AuroraVeils


class Veils(AuroraVeils):
    name = "veils"
    description = "Auroral curtains draped from the apex, seamless in azimuth"

    notes = (
        "Auroral curtains hung from the apex, seamless in azimuth — "
        "harmonics swaying against each other, green cores, violet "
        "fringes."
    )

    speed = 0.9

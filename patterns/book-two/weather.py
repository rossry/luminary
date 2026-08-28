"""Weather: sea-glass banks of warped noise, drifting slowly.

A registration of the shared
:class:`~luminary.patterns.primitives.NoiseGlow` primitive (book two):
domain-warped fbm through the SEA_GLASS palette, tuned for
dark-adapted patience — features take minutes to cross the sphere.
"""

from luminary.patterns.primitives import NoiseGlow


class Weather(NoiseGlow):
    name = "weather"
    description = "Sea-glass weather: warped noise banks drifting slowly"

    notes = (
        "Sea-glass banks drifting on minutes-long clocks. Features take "
        "their time crossing; let your eyes adjust and the field starts "
        "to breathe."
    )

    scale = 2.4
    speed = 0.022
    contrast = 1.6
    breathe_s = 47.0

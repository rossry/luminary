"""Small Planet: the sphere as a tiny living world. (registration)

The voice lives in :mod:`luminary.patterns.repertoire` — importable, so
other shows can nest a planet. See its docstring for the design: sun,
seasons, cities, aurora cap, and a moon whose brightness is its phase.
"""

from luminary.patterns import repertoire


class SmallPlanet(repertoire.SmallPlanet):
    """Registered as ``small_planet`` with the repertoire tuning."""

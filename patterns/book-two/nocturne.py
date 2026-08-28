"""Nocturne: an hour of night, in seven movements. (registration)

The movement list lives in
:func:`luminary.patterns.repertoire.nocturne_movements` — importable,
so other shows (``overnight``) can nest the same hour. Everything is
composition: the voices are library primitives, the sequencing is
:class:`~luminary.patterns.compose.Conductor`. Total length exactly
3600 s; ``duration`` lets a queue advance gaplessly when the hour ends.
"""

from luminary.patterns.compose import Conductor
from luminary.patterns.repertoire import nocturne_movements


class Nocturne(Conductor):
    name = "nocturne"
    description = "Half an hour of night: embers, stars, veils, sea, rings, candles"

    notes = (
        "Thirty minutes of night in seven movements, each one action at "
        "the size of the sphere: fire drains, a sky fills, a storm "
        "crests, the sea rests, a toll approaches, candles gather, and "
        "the same stars let go in reverse order of arrival."
    )

    def __init__(self) -> None:
        super().__init__(nocturne_movements())

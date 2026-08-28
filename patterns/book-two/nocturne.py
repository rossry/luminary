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
    description = "An hour of night: embers, stars, veils, sea, rings, candles"

    def __init__(self) -> None:
        super().__init__(nocturne_movements())

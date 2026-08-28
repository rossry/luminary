"""Nocturne: half an hour of night, in seven movements. (registration)

Pairs with ``var/audio/nocturne.mp3`` — assemble it from the intended
soundtrack (one file, in order; trim or crossfade to taste, and if your
cut lands on different lengths, say so and the movements can be retimed
to it, cue-sheet style):

  I    dusk         Biosphere — "Poa Alpina" (~4:31)
  II   first-stars  Ólafur Arnalds — "Saman" (~3:24)
  III  veils        Jóhann Jóhannsson — "Flight from the City" (~5:26)
  IV   deep-sea     Harold Budd & Brian Eno — "The Pearl" (~4:04)
  V    rings        Arvo Pärt — "Cantus in Memoriam Benjamin Britten" (excerpt ~4:00)
  VI   candles      A Winged Victory for the Sullen — "Requiem for the
                    Static King, Part One" (3:53, let Part Two begin)
  VII  starfall     Eluvium — "Radio Ballet" (~4:03)

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
    audio = "nocturne.mp3"

    notes = (
        "Thirty minutes of night in seven movements, each one action at "
        "the size of the sphere: fire drains, a sky fills, a storm "
        "crests, the sea rests, a toll approaches, candles gather, and "
        "the same stars let go in reverse order of arrival."
    )

    def __init__(self) -> None:
        super().__init__(nocturne_movements())

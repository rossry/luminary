"""Nocturne: half an hour of night, in seven movements. (registration)

Each act carries its own track, as a separate file in ``var/audio`` —
queued as chapters, the stage starts each act's music at the act. The
movements are timed to these exact recordings (video runtimes; retime
the movement if your file differs):

  I    embers       nocturne-embers.mp3       4:11
       Biosphere — "Poa Alpina" (Substrata)
       https://www.youtube.com/watch?v=xc7atbM0k6g
  II   first-stars  nocturne-first-stars.mp3  2:12
       Ólafur Arnalds — "saman" (re:member)
       https://www.youtube.com/watch?v=XmHs_sMDueA
  III  veils        nocturne-veils.mp3        6:31
       Jóhann Jóhannsson — "Flight from the City" (Orphée)
       https://www.youtube.com/watch?v=aXlx-YnvgKU
  IV   deep-sea     nocturne-deep-sea.mp3     3:14
       Harold Budd & Brian Eno — "The Pearl" (2005 remaster)
       https://www.youtube.com/watch?v=qySCf2ovWJc
  V    rings        nocturne-rings.mp3        7:19
       Arvo Pärt — "Cantus in Memoriam Benjamin Britten"
       (Nagano / Orchestre Philharmonique de Radio France)
       https://www.youtube.com/watch?v=GMF2C2-zcWM
  VI   candles      nocturne-candles.mp3      2:46
       A Winged Victory for the Sullen — "Requiem for the Static
       King, Part One"
       https://www.youtube.com/watch?v=SwmRJQAx8eA
  VII  starfall     nocturne-starfall.mp3     3:31
       Eluvium — "Radio Ballet" (2019 Pianoworks version; the 2007
       Copia original runs 3:13 — say so and VII retimes)
       https://www.youtube.com/watch?v=nvtV4fvNJpY

The movement list lives in
:func:`luminary.patterns.repertoire.nocturne_movements` — importable,
so other shows (``overnight``) can nest the same night. Everything is
composition: the voices are library primitives, the sequencing is
:class:`~luminary.patterns.compose.Conductor`. Total 1784 s (29:44);
``duration`` lets a queue advance gaplessly when the night ends.
"""

from luminary.patterns.compose import Conductor
from luminary.patterns.repertoire import nocturne_movements


class Nocturne(Conductor):
    name = "nocturne"
    description = "Half an hour of night: embers, stars, veils, sea, rings, candles"

    notes = (
        "A half hour of night in seven movements, each one action at "
        "the size of the sphere: fire drains, a sky fills, a storm "
        "crests, the sea rests, a toll passes through every color of "
        "night, candles roar and are breathed out, and the stars fall. "
        "Each act carries its own track — queue it as chapters and the "
        "music changes with the act."
    )

    def __init__(self) -> None:
        super().__init__(nocturne_movements())

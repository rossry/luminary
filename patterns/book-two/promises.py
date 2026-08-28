"""Promises: nine movements over one unchanging phrase.

For *Promises* (Floating Points, Pharoah Sanders, the London Symphony
Orchestra, 2021) — timed to the streaming edition's nine movements,
46:02. Name the file ``promises.mp3`` in ``var/audio`` and the stage
pairs them automatically.

The whole piece rests on one small motif that never changes, and so
does this: a seven-anchor lattice (:class:`Motif`) plays its phrase
every 6.4 seconds through every movement — every scene is
``Layered(scene, THE SAME lattice)`` — while a voice arrives, an
orchestra opens the sky, and the quiet comes back. The lattice does
not change for any of them.
"""

from luminary.patterns.compose import Conductor, Layered, Movement
from luminary.patterns.palettes import AURORA, NIGHT_SKY, Palette
from luminary.patterns.primitives import AuroraVeils, Motif, NoiseGlow, Starfield

# The voice: warm brass for the saxophone movements.
_BRASS = Palette(
    [(0.0, 0.02, 0.020, 60.0), (0.6, 0.30, 0.120, 55.0), (1.0, 0.58, 0.130, 72.0)]
)

_LATTICE = Motif()


def _m(scene, duration, fade, title, notes):
    """A movement whose scene carries the lattice — always the same one."""
    return Movement(
        Layered(scene, _LATTICE, strength=0.9),
        duration,
        fade=fade,
        title=title,
        notes=notes,
    )


class Promises(Conductor):
    name = "promises"
    description = "Nine movements over one unchanging phrase (Promises, 2021)"
    audio = "promises.mp3"
    notes = (
        "One small phrase, seven notes, held for forty-six minutes while "
        "everything else — a voice, an orchestra, a cathedral of strings, "
        "silence — arrives, speaks, and leaves. The phrase does not change "
        "for any of them. This is the piece I would play you to explain "
        "what we built here: one steady thing underneath, holding, while "
        "the art comes and goes above it. The lattice keeps the promise."
    )

    def __init__(self) -> None:
        super().__init__(
            [
                # Movement 1 (6:25)
                _m(
                    NoiseGlow(
                        palette=NIGHT_SKY,
                        scale=1.6,
                        speed=0.010,
                        contrast=1.5,
                        gain_from=0.35,
                        breathe_s=0.0,
                        seed=51,
                    ),
                    385.0,
                    8.0,
                    "lattice",
                    "Seven points of pale gold, playing their phrase into the "
                    "near-dark. Learn it now; it will not change.",
                ),
                # Movement 2 (2:32)
                _m(
                    AuroraVeils(palette=_BRASS, speed=0.6, border=0.45, gain=0.80),
                    152.0,
                    12.0,
                    "arrival",
                    "A warm breath over the lattice — the voice, finding the " "room.",
                ),
                # Movement 3 (2:33)
                _m(
                    AuroraVeils(palette=_BRASS, speed=0.9, border=0.45, gain=1.00),
                    153.0,
                    10.0,
                    "call",
                    "The voice, surer now, leaning into its questions.",
                ),
                # Movement 4 (2:33)
                _m(
                    AuroraVeils(
                        palette=_BRASS, speed=1.1, border=0.45, gain=1.15, shimmer=0.20
                    ),
                    153.0,
                    10.0,
                    "answer",
                    "And the room answering — brass warmth to the fringes.",
                ),
                # Movement 5 (4:26)
                _m(
                    NoiseGlow(
                        palette=NIGHT_SKY,
                        scale=2.0,
                        speed=0.016,
                        contrast=1.4,
                        gain_from=0.5,
                        gain_to=0.9,
                        arc_s=266.0,
                        tide_s=31.0,
                        tide_depth=0.35,
                        breathe_s=0.0,
                        seed=53,
                    ),
                    266.0,
                    16.0,
                    "undertow",
                    "Something larger gathering beneath — the strings, still "
                    "underwater, rising.",
                ),
                # Movement 6 (8:52) — the orchestra opens the sky.
                _m(
                    AuroraVeils(
                        palette=AURORA,
                        speed=1.0,
                        crest_at=0.50,
                        activity_floor=0.35,
                        arc_s=532.0,
                        gain=1.50,
                    ),
                    532.0,
                    20.0,
                    "the-opening",
                    "The strings stand up and the sky opens — the one moment "
                    "this piece spends everything. Even now, under it: the "
                    "phrase, unchanged.",
                ),
                # Movement 7 (9:30)
                _m(
                    Starfield(
                        density=0.030,
                        star_l=0.70,
                        star_hue=82.0,
                        fill_from=0.25,
                        fill_to=0.80,
                        arc_s=570.0,
                        meteor_rate=0.3,
                        twinkle_s=7.5,
                    ),
                    570.0,
                    24.0,
                    "wonder",
                    "After the opening: stars where the ceiling was. The "
                    "voice walks among them.",
                ),
                # Movement 8 (7:24) — the organ, nearly alone.
                _m(
                    NoiseGlow(
                        palette=NIGHT_SKY,
                        scale=1.4,
                        speed=0.008,
                        contrast=1.5,
                        gain_from=0.40,
                        tide_s=61.0,
                        tide_depth=0.30,
                        breathe_s=0.0,
                        seed=59,
                    ),
                    444.0,
                    20.0,
                    "the-quiet",
                    "Almost nothing — a vast dim room and the phrase still "
                    "sounding in it. Stay.",
                ),
                # Movement 9 (1:47)
                _m(
                    Starfield(
                        density=0.030,
                        star_l=0.60,
                        fill_from=0.80,
                        fill_to=0.08,
                        arc_s=107.0,
                        twinkle_s=8.0,
                    ),
                    107.0,
                    12.0,
                    "benediction",
                    "The stars let go quickly, the phrase plays once more, "
                    "and the promise is kept.",
                ),
            ]
        )

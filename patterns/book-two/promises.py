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

**Everything else does.** The scenes are what the lattice is heard
against, and each one travels its own movement: the opening near-dark
gathers for six minutes before anything else happens; the voice's
three movements are three crests, each arriving earlier and burning
hotter than the last; the undertow rises; the opening spends
everything; the quiet drains to almost nothing. Movement 7 is the
piece's longest and needs two scenes — a sky filling, then the voice
walking in it — so it is a nested pair.
"""

from luminary.patterns.compose import Conductor, Layered, Movement
from luminary.patterns.palettes import AURORA, NIGHT_SKY, Palette
from luminary.patterns.primitives import AuroraVeils, Motif, NoiseGlow, Starfield

# The voice: warm brass for the saxophone movements.
_BRASS = Palette(
    [(0.0, 0.02, 0.020, 60.0), (0.6, 0.30, 0.120, 55.0), (1.0, 0.58, 0.130, 72.0)]
)

_LATTICE = Motif()

_WONDER = "promises-wonder"  # movement 7's two scenes are one sky


def _lay(scene):
    """Any scene, carrying the lattice — always the same instance."""
    return Layered(scene, _LATTICE, strength=0.9)


def _m(scene, duration, fade, title, notes):
    """A movement whose scene carries the lattice — always the same one."""
    return Movement(_lay(scene), duration, fade=fade, title=title, notes=notes)


def _wonder() -> Conductor:
    """Movement 7 (9:30) as its two halves: the sky, then the walking.

    The longest stretch in the piece, and the one place a single fill
    would just be a slider moving for nine and a half minutes. The same
    ``salt`` across both scenes: it is one sky, and the second half is
    what it is like to be inside it.
    """
    return Conductor(
        [
            Movement(
                _lay(
                    Starfield(
                        density=0.030,
                        star_l=0.70,
                        star_hue=82.0,
                        fill_from=0.14,
                        fill_to=0.88,
                        arc_s=300.0,
                        meteor_rate=0.35,
                        twinkle_s=7.5,
                        tint=0.85,
                        flutter=0.09,
                        sparse_boost=0.40,
                        swell=0.22,
                        churn=0.20,
                        salt=_WONDER,
                    )
                ),
                300.0,
                fade=0.0,  # the outer movement's 24 s crossfade is the entry
                title="where-the-ceiling-was",
                notes=(
                    "After the opening, the roof is simply gone. Stars "
                    "arrive into the space it left — a few at first, "
                    "burning near full because they have the dark to "
                    "themselves, then the whole sky."
                ),
            ),
            Movement(
                _lay(
                    Starfield(
                        density=0.030,
                        star_l=0.74,
                        star_hue=82.0,
                        fill_from=0.88,
                        fill_to=0.52,
                        arc_s=270.0,
                        meteor_rate=0.20,
                        twinkle_s=8.5,
                        tint=0.85,
                        flutter=0.08,
                        sparse_boost=0.35,
                        swell=0.18,
                        churn=0.24,
                        churn_life_s=11.0,
                        salt=_WONDER,
                    )
                ),
                270.0,
                fade=30.0,
                title="the-voice-among-them",
                notes=(
                    "The same sky — the same stars, by salt — and now "
                    "somebody is walking in it. The deep ones go on "
                    "rising while the newest quietly let go, and short-"
                    "lived ones come up and fade all through. Nothing "
                    "is being built any more; it is being lived in."
                ),
            ),
        ]
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
                        gain_from=0.26,
                        gain_to=0.72,
                        arc_s=385.0,
                        tide_s=97.0,
                        tide_depth=0.30,
                        breathe_s=0.0,
                        seed=51,
                    ),
                    385.0,
                    8.0,
                    "lattice",
                    "Seven points of pale gold, playing their phrase into a "
                    "near-dark that spends the whole six minutes deciding to "
                    "become a room. Learn the phrase now; it will not change.",
                ),
                # Movement 2 (2:32)
                _m(
                    AuroraVeils(
                        palette=_BRASS,
                        speed=0.6,
                        border=0.45,
                        gain=0.85,
                        crest_at=0.62,
                        activity_floor=0.24,
                        crest_width=0.30,
                        arc_s=152.0,
                    ),
                    152.0,
                    12.0,
                    "arrival",
                    "A warm breath over the lattice — the voice, finding the "
                    "room. It takes its time about it: the crest comes late "
                    "and lets go before the movement is over.",
                ),
                # Movement 3 (2:33)
                _m(
                    AuroraVeils(
                        palette=_BRASS,
                        speed=0.9,
                        border=0.45,
                        gain=1.05,
                        crest_at=0.50,
                        activity_floor=0.30,
                        crest_width=0.30,
                        arc_s=153.0,
                    ),
                    153.0,
                    10.0,
                    "call",
                    "The voice, surer now, leaning into its questions — the "
                    "same shape as the arrival, arriving sooner and reaching "
                    "higher.",
                ),
                # Movement 4 (2:33)
                _m(
                    AuroraVeils(
                        palette=_BRASS,
                        speed=1.1,
                        border=0.45,
                        gain=1.20,
                        shimmer=0.20,
                        crest_at=0.42,
                        activity_floor=0.38,
                        crest_width=0.32,
                        arc_s=153.0,
                        surge_s=27.0,
                    ),
                    153.0,
                    10.0,
                    "answer",
                    "And the room answering — brass warmth to the fringes, "
                    "arriving almost at once now, with surges racing the "
                    "sphere at the top of it. Three movements, three crests, "
                    "each one earlier and hotter than the last.",
                ),
                # Movement 5 (4:26)
                _m(
                    NoiseGlow(
                        palette=NIGHT_SKY,
                        scale=2.0,
                        speed=0.016,
                        contrast=1.4,
                        gain_from=0.36,
                        gain_to=1.10,
                        arc_s=266.0,
                        tide_s=31.0,
                        tide_depth=0.35,
                        tide2_s=53.0,
                        tide2_depth=0.26,
                        tide2_angle=112.0,
                        breathe_s=0.0,
                        seed=53,
                    ),
                    266.0,
                    16.0,
                    "undertow",
                    "Something larger gathering beneath — the strings, still "
                    "underwater, rising for four and a half minutes and never "
                    "once breaking the surface. Two swells cross under there.",
                ),
                # Movement 6 (8:52) — the orchestra opens the sky.
                _m(
                    AuroraVeils(
                        palette=AURORA,
                        speed=1.0,
                        crest_at=0.52,
                        activity_floor=0.35,
                        crest_width=0.26,
                        arc_s=532.0,
                        gain=1.50,
                        surge_s=29.0,
                        white_hot=0.82,
                    ),
                    532.0,
                    20.0,
                    "the-opening",
                    "The strings stand up and the sky opens — the one moment "
                    "this piece spends everything, four and a half minutes "
                    "getting there and four coming down, with the cores "
                    "burning white at the top of it. Even now, under it: the "
                    "phrase, unchanged.",
                ),
                # Movement 7 (9:30) — the longest stretch, in two scenes.
                # A plain Movement over the sub-Conductor: its children
                # carry the lattice themselves, so the chapter tree (and
                # the stage's liner notes) can see both halves.
                Movement(
                    _wonder(),
                    570.0,
                    fade=24.0,
                    title="wonder",
                    notes=(
                        "After the opening: stars where the ceiling was, and "
                        "then the voice walking among them. Nine and a half "
                        "minutes, one sky, two things to do in it."
                    ),
                ),
                # Movement 8 (7:24) — the organ, nearly alone.
                _m(
                    NoiseGlow(
                        palette=NIGHT_SKY,
                        scale=1.4,
                        speed=0.008,
                        contrast=1.5,
                        gain_from=0.82,
                        gain_to=0.28,
                        arc_s=444.0,
                        tide_s=71.0,
                        tide_depth=0.30,
                        breathe_s=0.0,
                        seed=59,
                    ),
                    444.0,
                    20.0,
                    "the-quiet",
                    "Almost nothing — a vast dim room and the phrase still "
                    "sounding in it, and over seven minutes the room gives up "
                    "half the little light it had. Stay.",
                ),
                # Movement 9 (1:47)
                _m(
                    Starfield(
                        density=0.030,
                        star_l=0.60,
                        fill_from=0.80,
                        fill_to=0.06,
                        arc_s=107.0,
                        twinkle_s=8.0,
                        sparse_boost=0.45,
                        swell=0.20,
                        flutter=0.08,
                        tint=0.70,
                        salt=_WONDER,
                    ),
                    107.0,
                    12.0,
                    "benediction",
                    "The stars let go quickly — the same stars, one last "
                    "time, the newest first and the deepest burning brighter "
                    "as the sky empties around them. The phrase plays once "
                    "more, and the promise is kept.",
                ),
            ]
        )

"""Apollo: a cue-sheet show for Eno's *Apollo: Atmospheres and Soundtracks*.

Twelve movements, one per track, timed to the original 1983 edition
(49:18 total) — queue this pattern on the stage with the album as its
audio and the sphere plays the record. Cue times are hardcoded from
the 1983 CD edition; remasters differ by seconds per track, and the
20–30 s crossfades are the tolerance. To retune for another pressing,
edit the labeled durations — the show is just a
:class:`Conductor` over library voices.

This file is the worked example of a *cue-sheet show*: an album is a
Movement list whose durations are the track lengths. The stage reads
``duration`` (49:18) to advance the queue when the record ends.
"""

from luminary.patterns.compose import Conductor, Movement
from luminary.patterns.palettes import NIGHT_SKY, SEA_GLASS, Palette
from luminary.patterns.primitives import AuroraVeils, NoiseGlow, RingWave, Starfield

# Album-local colorways (data, not logic — library palettes stay house-wide).
_SILVER = Palette(
    [(0.0, 0.04, 0.010, 240.0), (0.6, 0.30, 0.030, 220.0), (1.0, 0.60, 0.020, 200.0)]
)
_LAGOON = Palette(
    [
        (0.0, 0.06, 0.030, 250.0),
        (0.5, 0.30, 0.110, 210.0),
        (0.85, 0.55, 0.120, 180.0),
        (1.0, 0.68, 0.090, 95.0),
    ]
)
_ASCENT = Palette(
    [(0.0, 0.05, 0.030, 70.0), (0.55, 0.36, 0.100, 78.0), (1.0, 0.72, 0.080, 90.0)]
)
# Deep blue with a usable range — NIGHT_SKY is a sky (a backdrop for
# stars) and bottoms out as a standalone field; the grotto does not.
_GROTTO = Palette(
    [(0.0, 0.035, 0.020, 250.0), (0.55, 0.16, 0.080, 240.0), (1.0, 0.40, 0.100, 225.0)]
)


class Apollo(Conductor):
    name = "apollo"
    description = "Cue-sheet show for Eno's Apollo (1983): pair with the album"
    notes = (
        "The record, played by the sphere: twelve tracks, twelve scenes, "
        "49:18. Load the album into var/audio and queue them together — "
        "the crossfades absorb pressing drift. It ends under the stars it "
        "began under."
    )

    def __init__(self) -> None:
        super().__init__(
            [
                # 1. Under Stars (4:29)
                Movement(
                    Starfield(density=0.030, twinkle_s=7.0, sky_l=0.026),
                    269.0,
                    fade=10.0,
                    title="under-stars",
                    notes="The launch vigil: a held sky, patient, waiting.",
                ),
                # 2. The Secret Place (3:31)
                Movement(
                    NoiseGlow(
                        palette=_GROTTO,
                        scale=2.4,
                        speed=0.012,
                        contrast=1.35,
                        gain_from=0.55,
                        gain_to=1.0,
                        arc_s=90.0,
                        tide_s=41.0,
                        tide_depth=0.30,
                        breathe_s=0.0,
                        seed=8,
                    ),
                    211.0,
                    fade=20.0,
                    title="the-secret-place",
                    notes=(
                        "Underground blue, rising from half-light as the "
                        "track opens — a grotto with a slow tide through it."
                    ),
                ),
                # 3. Matta (4:20)
                Movement(
                    AuroraVeils(speed=0.55, shimmer=0.20, border=0.52),
                    260.0,
                    fade=25.0,
                    title="matta",
                    notes="Something alien stirring above — curtains that are not weather.",
                ),
                # 4. Signals (2:47)
                Movement(
                    RingWave(period=8.5, sigma_deg=5.0, l_gain=0.55, chroma=0.10),
                    167.0,
                    fade=15.0,
                    title="signals",
                    notes="Radio pings walking the sphere, apex to rim, re-keyed each pass.",
                ),
                # 5. An Ending (Ascent) (4:24)
                Movement(
                    NoiseGlow(
                        palette=_ASCENT,
                        scale=1.5,
                        speed=0.017,
                        contrast=1.05,
                        breathe_s=44.0,
                        breathe_depth=0.12,
                        seed=15,
                    ),
                    264.0,
                    fade=30.0,
                    title="an-ending",
                    notes=(
                        "The golden swell. Let it be as bright as the room "
                        "can bear — this is the album's heart."
                    ),
                ),
                # 6. Under Stars II (3:23)
                Movement(
                    Starfield(density=0.040, twinkle_s=6.0, sky_l=0.024),
                    203.0,
                    fade=25.0,
                    title="under-stars-ii",
                    notes="The same stars, denser dark — the vigil resumed after the climb.",
                ),
                # 7. Drift (3:05)
                Movement(
                    NoiseGlow(
                        palette=SEA_GLASS,
                        scale=2.0,
                        speed=0.010,
                        contrast=1.7,
                        breathe_s=51.0,
                        seed=23,
                    ),
                    185.0,
                    fade=25.0,
                    title="drift",
                    notes="Weightless green-blue banks, barely moving. Nothing to hold onto.",
                ),
                # 8. Silver Morning (2:40)
                Movement(
                    NoiseGlow(
                        palette=_SILVER,
                        scale=1.8,
                        speed=0.020,
                        contrast=1.2,
                        breathe_s=31.0,
                        seed=29,
                    ),
                    160.0,
                    fade=20.0,
                    title="silver-morning",
                    notes="First light with no color in it yet — pewter, then pearl.",
                ),
                # 9. Deep Blue Day (3:58)
                Movement(
                    NoiseGlow(
                        palette=_LAGOON,
                        scale=2.2,
                        speed=0.024,
                        contrast=1.1,
                        breathe_s=26.0,
                        seed=31,
                    ),
                    238.0,
                    fade=20.0,
                    title="deep-blue-day",
                    notes=(
                        "Lagoon light under the pedal steel — the one track "
                        "that smiles. Sand shows through the shallows."
                    ),
                ),
                # 10. Weightless (4:35)
                Movement(
                    NoiseGlow(
                        palette=NIGHT_SKY,
                        scale=1.4,
                        speed=0.007,
                        contrast=1.0,
                        gain_from=1.35,
                        gain_to=1.35,
                        arc_s=275.0,
                        tide_s=61.0,
                        tide_depth=0.30,
                        breathe_s=0.0,
                        seed=37,
                    ),
                    275.0,
                    fade=30.0,
                    title="weightless",
                    notes=(
                        "Floating in the big blue-black, a sixty-one-second "
                        "swell the only gravity."
                    ),
                ),
                # 11. Always Returning (4:04)
                Movement(
                    RingWave(period=21.0, sigma_deg=10.0, palette=SEA_GLASS),
                    244.0,
                    fade=25.0,
                    title="always-returning",
                    notes="Long waves coming home, twenty-one seconds apart. They know the way.",
                ),
                # 12. Stars (8:02)
                Movement(
                    Starfield(density=0.034, twinkle_s=8.5, star_l=0.55, sky_l=0.028),
                    482.0,
                    fade=30.0,
                    title="stars",
                    notes=(
                        "Eight minutes of stars to carry it out. The album "
                        "ends under its opening sky — hold still and let it."
                    ),
                ),
            ]
        )

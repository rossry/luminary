"""Köln: for Keith Jarrett's *The Köln Concert* (1975).

Four movements timed to the canonical edition — Part I 26:02,
Part IIa 14:54, Part IIb 18:13, Part IIc 6:56 (66:05 total). Name the
file ``koln-concert.mp3`` in ``var/audio`` and the stage pairs them.
"""

from luminary.patterns.compose import Conductor, Movement
from luminary.patterns.palettes import CANDLE, Palette
from luminary.patterns.primitives import Candles, NoiseGlow, RingWave, Starfield

# The vamp: gospel-warm golds for the driving second part.
_VAMP = Palette(
    [(0.0, 0.025, 0.020, 45.0), (0.55, 0.32, 0.120, 52.0), (1.0, 0.66, 0.110, 75.0)]
)


class Koln(Conductor):
    name = "koln"
    description = "For The Köln Concert (1975): four parts, 66:05"
    audio = "koln-concert.mp3"
    notes = (
        "The wrong piano — too small, thin in the bass, sticky in the "
        "middle — played anyway, because the promoter was seventeen and "
        "the tickets were sold. He worked around its wounds all night and "
        "made the best-loved solo record there is. For everyone building "
        "with what actually showed up."
    )

    def __init__(self) -> None:
        super().__init__(
            [
                # Part I (26:02) — the long unfolding.
                Movement(
                    NoiseGlow(
                        palette=CANDLE,
                        scale=2.0,
                        speed=0.050,
                        contrast=1.2,
                        gain_from=0.90,
                        tide_s=37.0,
                        tide_depth=0.35,
                        breathe_s=0.0,
                        seed=61,
                    ),
                    1562.0,
                    fade=10.0,
                    title="part-i",
                    notes=(
                        "Warm banks wandering and never settling — an "
                        "improvisation with no destination, only momentum. "
                        "When the left hand locks into a vamp, watch the "
                        "tide pick up."
                    ),
                ),
                # Part IIa (14:54) — the drive.
                Movement(
                    RingWave(
                        period=9.5,
                        sigma_deg=7.0,
                        palette=_VAMP,
                        gain_from=0.4,
                        gain_to=1.0,
                        arc_s=60.0,
                    ),
                    894.0,
                    fade=18.0,
                    title="part-iia",
                    notes=(
                        "The pulse: gold rings walking apex to rim every "
                        "nine and a half seconds, each one a right hand "
                        "over the same left-hand figure."
                    ),
                ),
                # Part IIb (18:13) — the lyrical heart.
                Movement(
                    Candles(
                        fill_from=0.20,
                        fill_to=0.78,
                        arc_s=1000.0,
                        flicker_s=5.0,
                    ),
                    1093.0,
                    fade=22.0,
                    title="part-iib",
                    notes=(
                        "The tender stretch: candles gathering one by one "
                        "for eighteen minutes, a congregation assembling "
                        "in no hurry at all."
                    ),
                ),
                # Part IIc (6:56) — the encore.
                Movement(
                    Starfield(
                        density=0.028,
                        star_l=0.60,
                        star_hue=70.0,
                        fill_from=0.80,
                        fill_to=0.45,
                        arc_s=416.0,
                        twinkle_s=7.0,
                    ),
                    416.0,
                    fade=16.0,
                    title="part-iic",
                    notes=(
                        "The encore — the one written tune of the night, "
                        "played like a goodnight. Warm stars, thinning "
                        "but not gone, when the lights come up."
                    ),
                ),
            ]
        )

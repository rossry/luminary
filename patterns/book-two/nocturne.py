"""Nocturne: an hour of night, in seven movements.

The first conducted show (book two): dusk embers cool into a starfield,
aurora veils rise and give way to deep-sea weather, slow rings toll
through blue, candlelight gathers, and the same stars return to carry
the night out. Movement order walks neighboring hue families (ember ->
indigo -> aurora teal -> sea glass -> night blue -> candle -> indigo)
so every crossfade blends kin colors; the one deliberate leap — blue
into candlelight — reads as warmth arriving, and the OKLab crossfade
carries it through neutral instead of around the wheel.

Movements 2 and 7 share the default starfield salt on purpose: they are
the same stars, found again at the end.

Everything is composition — the voices live in
``luminary/patterns/primitives.py``, the sequencing in ``compose.py``.
Total length exactly 3600 s; the conductor's ``duration`` lets a queue
advance gaplessly when the hour ends.
"""

from luminary.patterns.compose import Conductor, Movement
from luminary.patterns.palettes import AURORA, CANDLE, EMBER, NIGHT_SKY, SEA_GLASS
from luminary.patterns.primitives import AuroraVeils, NoiseGlow, RingWave, Starfield


class Nocturne(Conductor):
    name = "nocturne"
    description = "An hour of night: embers, stars, veils, sea, rings, candles"

    def __init__(self) -> None:
        super().__init__(
            [
                # I. Dusk — the last of the fire, breathing out. (8 min)
                Movement(
                    NoiseGlow(
                        palette=EMBER,
                        scale=1.8,
                        speed=0.020,
                        contrast=1.7,
                        breathe_s=41.0,
                        seed=3,
                    ),
                    480.0,
                    fade=12.0,
                ),
                # II. First stars over indigo airglow. (7 min)
                Movement(
                    Starfield(density=0.030, twinkle_s=6.5, star_hue=80.0),
                    420.0,
                    fade=35.0,
                ),
                # III. Veils — aurora curtains from the apex. (10 min)
                Movement(AuroraVeils(palette=AURORA, speed=0.8), 600.0, fade=40.0),
                # IV. Deep sea — slow warped weather in green-blue. (8 min)
                Movement(
                    NoiseGlow(
                        palette=SEA_GLASS,
                        scale=2.6,
                        speed=0.014,
                        contrast=1.9,
                        breathe_s=53.0,
                        seed=12,
                    ),
                    480.0,
                    fade=40.0,
                ),
                # V. Rings tolling through night blue. (8 min)
                Movement(
                    RingWave(period=16.0, sigma_deg=9.0, palette=NIGHT_SKY),
                    480.0,
                    fade=30.0,
                ),
                # VI. Candlelight gathers — the warm turn. (10 min)
                Movement(
                    NoiseGlow(
                        palette=CANDLE,
                        scale=1.6,
                        speed=0.025,
                        contrast=1.4,
                        breathe_s=29.0,
                        seed=21,
                    ),
                    600.0,
                    fade=45.0,
                ),
                # VII. The same stars, dimmer, carrying the night out. (9 min)
                Movement(
                    Starfield(density=0.020, twinkle_s=9.0, star_l=0.50, sky_l=0.022),
                    540.0,
                    fade=45.0,
                ),
            ]
        )

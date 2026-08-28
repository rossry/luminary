"""Apollo: a cue-sheet show for Eno's *Apollo: Atmospheres and Soundtracks*.

Twelve movements, one per track, timed to the original 1983 edition
(49:18 total) — queue this pattern on the stage with the album as its
audio and the sphere plays the record: cold starfields for the launch
vigil, radio-ping rings for "Signals", a golden swell for "An Ending
(Ascent)", lagoon blues under the pedal steel of "Deep Blue Day", long
returning waves, and eight minutes of stars to carry it out. The same
starfield salt opens and closes the album — it ends under the stars it
began under.

Cue times are hardcoded from the 1983 CD edition; remasters differ by
seconds per track. The 20–30 s crossfades are the tolerance: drift of
a few seconds never lands on a hard edge. To retune for another
pressing, edit the durations here (each movement is labeled with its
track) — the show is just a :class:`Conductor` over library voices,
so nothing else changes.

This file is the worked example of a *cue-sheet show*: an album is a
Movement list whose durations are the track lengths. The stage
(``/stage``) reads ``duration`` (49:18) to advance the queue when the
record ends.
"""

from luminary.patterns.compose import Conductor, Movement
from luminary.patterns.palettes import CANDLE, NIGHT_SKY, SEA_GLASS, Palette
from luminary.patterns.primitives import AuroraVeils, NoiseGlow, RingWave, Starfield

# Album-local colorways (data, not logic — library palettes stay house-wide).
_SILVER = Palette(
    [(0.0, 0.05, 0.010, 240.0), (0.6, 0.35, 0.030, 220.0), (1.0, 0.70, 0.020, 200.0)]
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
    [(0.0, 0.06, 0.030, 70.0), (0.55, 0.42, 0.100, 78.0), (1.0, 0.80, 0.080, 90.0)]
)


class Apollo(Conductor):
    name = "apollo"
    description = "Cue-sheet show for Eno's Apollo (1983): pair with the album"

    def __init__(self) -> None:
        super().__init__(
            [
                # 1. Under Stars (4:29) — the launch vigil.
                Movement(
                    Starfield(density=0.030, twinkle_s=7.0, sky_l=0.026),
                    269.0,
                    fade=10.0,
                ),
                # 2. The Secret Place (3:31) — subterranean blue.
                Movement(
                    NoiseGlow(
                        palette=NIGHT_SKY,
                        scale=2.4,
                        speed=0.012,
                        contrast=2.0,
                        breathe_s=37.0,
                        seed=8,
                    ),
                    211.0,
                    fade=20.0,
                ),
                # 3. Matta (4:20) — something alien stirring.
                Movement(
                    AuroraVeils(speed=0.55, shimmer=0.20, border=0.52),
                    260.0,
                    fade=25.0,
                ),
                # 4. Signals (2:47) — radio pings walking the elevation rings.
                Movement(
                    RingWave(period=8.5, sigma_deg=5.0, l_gain=0.55, chroma=0.10),
                    167.0,
                    fade=15.0,
                ),
                # 5. An Ending (Ascent) (4:24) — the golden swell.
                Movement(
                    NoiseGlow(
                        palette=_ASCENT,
                        scale=1.5,
                        speed=0.017,
                        contrast=0.85,
                        breathe_s=44.0,
                        breathe_depth=0.20,
                        seed=15,
                    ),
                    264.0,
                    fade=30.0,
                ),
                # 6. Under Stars II (3:23) — the same stars, denser dark.
                Movement(
                    Starfield(density=0.040, twinkle_s=6.0, sky_l=0.024),
                    203.0,
                    fade=25.0,
                ),
                # 7. Drift (3:05).
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
                ),
                # 8. Silver Morning (2:40).
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
                ),
                # 9. Deep Blue Day (3:58) — lagoon light under pedal steel.
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
                ),
                # 10. Weightless (4:35) — floating, barely moving.
                Movement(
                    NoiseGlow(
                        palette=NIGHT_SKY,
                        scale=1.4,
                        speed=0.007,
                        contrast=1.3,
                        breathe_s=59.0,
                        seed=37,
                    ),
                    275.0,
                    fade=30.0,
                ),
                # 11. Always Returning (4:04) — long waves coming home.
                Movement(
                    RingWave(period=21.0, sigma_deg=10.0, palette=SEA_GLASS),
                    244.0,
                    fade=25.0,
                ),
                # 12. Stars (8:02) — the album ends under its opening sky.
                Movement(
                    Starfield(density=0.034, twinkle_s=8.5, star_l=0.55, sky_l=0.028),
                    482.0,
                    fade=30.0,
                ),
            ]
        )

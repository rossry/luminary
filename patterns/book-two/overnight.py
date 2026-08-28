"""Overnight: dusk to dawn — the whole of book two, conducted.

One name to queue when the sun goes down: a looping program of
chapters, each a book-two voice (or a whole nested show — the first
chapter *is* Nocturne, the same movement list, by import). Conductors
nest freely because a show is itself a Pattern: the outer conductor
hands each chapter movement-local time, and during a chapter
crossfade at most two chapters render (each of which may briefly be
mid-crossfade itself — worst case four leaf renders for a minute or
so every twenty).

``loop=True``: no ``duration``, so the stage plays it until skipped —
the intended overnight semantics. The loop seam is composed: the last
chapter's quiet starfield fades into Nocturne's opening embers.

One full pass is 3 h 40 m; with the seeded variety inside every
chapter (planet days, firefly swells, relay heats), no two passes
read the same.
"""

from luminary.patterns.compose import Conductor, Movement
from luminary.patterns.palettes import NIGHT_SKY, SEA_GLASS
from luminary.patterns.primitives import AuroraVeils, NoiseGlow, RingWave, Starfield
from luminary.patterns.repertoire import Fireflies, Relay, SmallPlanet, nocturne


class Overnight(Conductor):
    name = "overnight"
    description = "Dusk to dawn: book two as a looping program of chapters"

    def __init__(self) -> None:
        super().__init__(
            [
                # The composed hour, whole. (60 min)
                Movement(nocturne(), 3600.0, fade=25.0),
                # Four days and nights of the small planet. (40 min)
                Movement(SmallPlanet(), 2400.0, fade=60.0),
                # Five swells of firefly synchrony. (25 min)
                Movement(Fireflies(), 1500.0, fade=45.0),
                # Veils on their own, slower. (20 min)
                Movement(AuroraVeils(speed=0.8), 1200.0, fade=45.0),
                # The set break: thirty heats of relay. (10 min)
                Movement(Relay(), 600.0, fade=25.0),
                # Sea-glass weather to settle back down. (25 min)
                Movement(
                    NoiseGlow(
                        palette=SEA_GLASS,
                        scale=2.4,
                        speed=0.012,
                        contrast=1.8,
                        breathe_s=57.0,
                        seed=44,
                    ),
                    1500.0,
                    fade=45.0,
                ),
                # Rings tolling long. (15 min)
                Movement(
                    RingWave(period=18.0, sigma_deg=9.0, palette=NIGHT_SKY),
                    900.0,
                    fade=40.0,
                ),
                # Quiet stars, carrying into the loop seam. (25 min)
                Movement(
                    Starfield(density=0.024, twinkle_s=9.5, sky_l=0.024),
                    1500.0,
                    fade=60.0,
                ),
            ],
            loop=True,
        )

"""Overnight: dusk to dawn — the whole of book two, conducted.

One name to queue when the sun goes down: a looping program of
chapters, each a book-two voice (or a whole nested show — the first
chapter *is* Nocturne, the same movement list, by import). Conductors
nest freely because a show is itself a Pattern. ``loop=True``: no
``duration``, so the stage plays it until skipped, and the loop seam
is composed — the last chapter's quiet starfield fades into
Nocturne's opening embers, exactly, every pass (3 h 10 m each).
"""

from luminary.patterns.compose import Conductor, Movement
from luminary.patterns.palettes import SEA_GLASS
from luminary.patterns.primitives import AuroraVeils, NoiseGlow, RingWave, Starfield
from luminary.patterns.repertoire import TOLL, Fireflies, Relay, SmallPlanet, nocturne


class Overnight(Conductor):
    name = "overnight"
    description = "Dusk to dawn: book two as a looping program of chapters"
    notes = (
        "The all-night program: queue it and walk away. Nocturne, "
        "four days of the small planet, firefly synchrony, veils, a relay "
        "set-break, sea weather, long rings, and quiet stars that loop "
        "back into the embers. No two passes read the same."
    )

    def __init__(self) -> None:
        super().__init__(
            [
                Movement(
                    nocturne(),
                    1800.0,
                    fade=25.0,
                    title="nocturne",
                    notes=(
                        "The composed half hour, whole — seven movements "
                        "from dusk embers to starfall. See each chapter's "
                        "own notes as it plays."
                    ),
                ),
                Movement(
                    SmallPlanet(),
                    2400.0,
                    fade=60.0,
                    title="small-planet",
                    notes=(
                        "Four days and nights of a turning world: dawns, "
                        "weather, cities, an aurora winter, a phase-true "
                        "moon. Arrived — it simply turns."
                    ),
                ),
                Movement(
                    Fireflies(),
                    1500.0,
                    fade=45.0,
                    title="fireflies",
                    notes=(
                        "Five swells of meadow synchrony: scattered sparks "
                        "pull into unison and let go again. Watch for the "
                        "lock."
                    ),
                ),
                Movement(
                    AuroraVeils(speed=0.8),
                    1200.0,
                    fade=45.0,
                    title="veils",
                    notes="Aurora curtains on their own, slower — weather with nowhere to be.",
                ),
                Movement(
                    Relay(),
                    600.0,
                    fade=25.0,
                    title="relay",
                    notes=(
                        "The set break: thirty heats of bead races down the "
                        "actual wiring. Gold floods for the winners."
                    ),
                ),
                Movement(
                    NoiseGlow(
                        palette=SEA_GLASS,
                        scale=2.4,
                        speed=0.012,
                        contrast=1.8,
                        tide_s=57.0,
                        tide_depth=0.35,
                        breathe_s=0.0,
                        seed=44,
                    ),
                    1500.0,
                    fade=45.0,
                    title="weather",
                    notes=(
                        "Sea-glass banks settling the room back down, one "
                        "sphere-wide swell a minute."
                    ),
                ),
                Movement(
                    RingWave(period=18.0, sigma_deg=9.0, palette=TOLL),
                    900.0,
                    fade=40.0,
                    title="rings",
                    notes="Rings tolling long through night blue — eighteen seconds apex to rim.",
                ),
                Movement(
                    Starfield(density=0.024, twinkle_s=9.5, sky_l=0.024),
                    1500.0,
                    fade=60.0,
                    title="starlight",
                    notes=(
                        "Quiet stars carrying into the loop seam: they hand "
                        "the sky back to the embers, and the night begins "
                        "again."
                    ),
                ),
            ],
            loop=True,
        )

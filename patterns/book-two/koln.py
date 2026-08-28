"""Köln: for Keith Jarrett's *The Köln Concert* (1975).

Four parts timed to the canonical edition — Part I 26:02, Part IIa
14:54, Part IIb 18:13, Part IIc 6:56 (66:05 total). Name the file
``koln-concert.mp3`` in ``var/audio`` and the stage pairs them.

Part I is itself a suite — its cue sheet (minutes:seconds into the
track): 0:00 the vamp; 5:04 a sharper, exploratory scouting mode;
6:45 a fade-out to 6:55; 7:00 one brief re-entry; 7:14 the main theme
in earnest; 8:40 a sparse wandering interlude; 9:41 the theme
revisited, carrying to the end. Queued as chapters it expands one
level at a time: ``koln/part-i`` first, then ``koln/part-i/vamp`` and
its siblings when Part I reaches the head.
"""

from luminary.patterns.compose import Conductor, Layered, Movement
from luminary.patterns.palettes import CANDLE, Palette
from luminary.patterns.primitives import Candles, Motif, NoiseGlow, RingWave, Starfield
from luminary.patterns.repertoire import Fireflies

# The vamp: gospel-warm golds for the driving second part.
_VAMP = Palette(
    [(0.0, 0.025, 0.020, 45.0), (0.55, 0.32, 0.120, 52.0), (1.0, 0.66, 0.110, 75.0)]
)


def _vamp_banks(gain: float = 0.90, **over: float) -> NoiseGlow:
    """The candlelit vamp world — Part I's home key."""
    kwargs = dict(
        scale=2.0,
        speed=0.050,
        contrast=1.2,
        gain_from=gain,
        tide_s=37.0,
        tide_depth=0.35,
        breathe_s=0.0,
        seed=61,
    )
    kwargs.update(over)
    return NoiseGlow(palette=CANDLE, **kwargs)


def _theme(cycle_s: float, peak_l: float) -> Motif:
    """The singing right hand: a five-note phrase over the vamp."""
    return Motif(
        count=5,
        cycle_s=cycle_s,
        note_frac=0.62,
        pool_deg=6.5,
        peak_l=peak_l,
        hue=75.0,
        chroma=0.08,
        attack=0.10,
        decay=0.70,
    )


def _part_i() -> Conductor:
    """Part I as movements on the user's cue sheet (seconds)."""
    return Conductor(
        [
            Movement(
                _vamp_banks(),
                304.0,  # 0:00-5:04
                fade=10.0,
                title="vamp",
                notes=(
                    "Warm banks wandering and never settling — an "
                    "improvisation with no destination, only momentum. "
                    "When the left hand locks in, watch the tide."
                ),
            ),
            Movement(
                Fireflies(
                    count=11,
                    interval_s=2.4,
                    rate=0.85,
                    sync_period=1.0e9,  # scouts never fall into unison
                    flash_attack=0.06,
                    flash_decay=0.35,
                    spot_deg=4.0,
                    wander_deg=24.0,
                    wander_s=13.0,
                    meadow_l=0.026,
                    base_hue=52.0,
                    glow_hue_shift=22.0,
                ),
                101.0,  # 5:04-6:45
                fade=5.0,
                title="scouting",
                notes=(
                    "The mode sharpens: quick amber points probing the "
                    "dark, each on its own line, none agreeing — the "
                    "right hand looking for the way in."
                ),
            ),
            Movement(
                Layered(
                    _vamp_banks(gain=0.14, tide_s=0.0),
                    Motif(
                        count=1,
                        cycle_s=60.0,
                        phase_s=15.0,  # 7:00 on the record: one re-entry
                        note_frac=0.10,
                        pool_deg=10.0,
                        peak_l=0.50,
                        hue=68.0,
                        chroma=0.09,
                        attack=0.35,
                        decay=2.2,
                    ),
                ),
                29.0,  # 6:45-7:14 (the fade lands 6:45-6:55)
                fade=10.0,
                title="the-breath",
                notes=(
                    "The room dims to almost nothing and holds its "
                    "breath; one warm pulse at the middle — he touches "
                    "the theme once, and waits."
                ),
            ),
            Movement(
                Layered(_vamp_banks(gain=0.95), _theme(9.6, 0.55)),
                86.0,  # 7:14-8:40
                fade=6.0,
                title="the-theme",
                notes=(
                    "In earnest: the vamp back at full warmth and the "
                    "five-note phrase singing over it, around and "
                    "around."
                ),
            ),
            Movement(
                Fireflies(
                    count=6,
                    interval_s=4.2,
                    rate=0.70,
                    sync_period=1.0e9,
                    flash_attack=0.10,
                    flash_decay=0.80,
                    spot_deg=4.5,
                    wander_deg=20.0,
                    wander_s=22.0,
                    meadow_l=0.022,
                    base_hue=48.0,
                    glow_hue_shift=20.0,
                ),
                61.0,  # 8:40-9:41
                fade=10.0,
                title="wandering",
                notes=(
                    "A sparse interlude: a few soft lights drifting far "
                    "apart, thinking it over."
                ),
            ),
            Movement(
                Layered(
                    _vamp_banks(gain=0.85, gain_to=1.0, arc_s=981.0),
                    _theme(11.0, 0.50),
                ),
                981.0,  # 9:41-26:02
                fade=12.0,
                title="revisited",
                notes=(
                    "The theme returns settled and stays — the long "
                    "unfolding, the banks slowly filling out underneath "
                    "for the rest of the side."
                ),
            ),
        ]
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
                # Part I (26:02) — the long unfolding, as its own suite.
                Movement(
                    _part_i(),
                    1562.0,
                    fade=10.0,
                    title="part-i",
                    notes=(
                        "The suite: vamp, scouting, one held breath, the "
                        "theme in earnest, a wandering interlude, and "
                        "the theme revisited for the rest of the side."
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

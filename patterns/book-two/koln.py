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

**Nothing here holds still for sixteen minutes.** The four part
lengths and Part I's six cue times are the record's; everything
*inside* them is this show's reading, and every stretch over about six
minutes is broken into scenes that go somewhere. Part I's "revisited"
is the long unfolding in three breaths — settling, the long climb,
coming to rest. Part IIa is the drive in two — the figure, then the
ecstasy that burns out of it — with each ring colored by when it
launched, so fifteen minutes of pulse is also one continuous walk from
deep amber up into white-gold and back down. Part IIb is the ballad's
congregation gathering, holding, and letting go. Part IIc plays the
one written tune of the night and then brings the house lights up
under it, which is what the record actually does.

Those inner divisions are dramaturgy, not a second cue sheet: retime
them freely, and the part boundaries stay put.
"""

from luminary.patterns.compose import Conductor, Layered, Movement
from luminary.patterns.palettes import CANDLE, Palette
from luminary.patterns.primitives import Candles, Motif, NoiseGlow, RingWave, Starfield
from luminary.patterns.repertoire import Fireflies

# Part IIa's drive, as one colour journey split at the seam between its
# two scenes: _RISE ends on exactly the stop _BURN starts from, so the
# rings walk deep amber -> gold -> white-gold -> warm amber across the
# whole fifteen minutes without a jump where the scenes change.
_DRIVE_RISE = Palette(
    [(0.0, 0.28, 0.110, 38.0), (0.5, 0.52, 0.120, 55.0), (1.0, 0.70, 0.110, 72.0)]
)
_DRIVE_BURN = Palette(
    [
        (0.0, 0.70, 0.110, 72.0),
        (0.45, 0.82, 0.070, 85.0),
        (0.78, 0.74, 0.100, 68.0),
        (1.0, 0.44, 0.120, 42.0),
    ]
)

_ENCORE = "koln-encore"  # Part IIc: one sky, under two different rooms


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


def _revisited() -> Conductor:
    """9:41 to the end of the side (16:21), in three breaths.

    The theme comes back settled, the side gathers itself into the long
    climb everyone remembers, and then it comes down and finishes
    quiet. One `Layered(banks, theme)` held flat for sixteen minutes is
    the one thing this stretch is definitely not.
    """
    return Conductor(
        [
            Movement(
                Layered(
                    _vamp_banks(
                        gain=0.72,
                        gain_to=1.00,
                        arc_s=300.0,
                        tide_s=41.0,
                        tide_depth=0.40,
                    ),
                    _theme(11.0, 0.46),
                ),
                300.0,
                fade=0.0,  # the outer movement's crossfade is the entry
                title="settling",
                notes=(
                    "The theme returns and, for the first time all side, "
                    "stops looking for anything. Five notes, unhurried, "
                    "over banks that have finally agreed where they are."
                ),
            ),
            Movement(
                Layered(
                    _vamp_banks(
                        gain=0.95,
                        gain_to=1.25,
                        arc_s=420.0,
                        tide_s=33.0,
                        tide_depth=0.38,
                        tide2_s=57.0,
                        tide2_depth=0.26,
                    ),
                    _theme(9.2, 0.60),
                ),
                420.0,
                fade=14.0,
                title="the-long-climb",
                notes=(
                    "Seven minutes of the side filling out underneath the "
                    "phrase — the tide deepening, a second swell crossing "
                    "it, the theme coming round faster and brighter each "
                    "time. Nobody decides this happens; it just keeps "
                    "being more true."
                ),
            ),
            Movement(
                Layered(
                    _vamp_banks(gain=1.25, gain_to=0.70, arc_s=261.0, tide_s=47.0),
                    _theme(13.5, 0.40),
                ),
                261.0,
                fade=16.0,
                title="coming-to-rest",
                notes=(
                    "And then it lets the side down. The phrase slows and "
                    "dims, the banks give back what they gathered, and the "
                    "first half ends quiet enough that you notice the room "
                    "again."
                ),
            ),
        ]
    )


def _the_drive() -> Conductor:
    """Part IIa (14:54): the pulse, and what it turns into.

    Rings launch faster than they descend, so two or three always share
    the sphere — the ostinato you cannot get out from under. The second
    scene tightens the launch cadence and lets the colour burn through
    white-gold and back down.
    """
    return Conductor(
        [
            Movement(
                RingWave(
                    period=9.5,
                    sigma_deg=7.0,
                    launch_s=4.6,
                    start_at=4.0,
                    gain_from=0.62,
                    gain_to=0.92,
                    arc_s=450.0,
                    meander=_DRIVE_RISE,
                    meander_s=450.0,
                ),
                450.0,
                fade=0.0,
                title="the-figure",
                notes=(
                    "The pulse: gold rings walking apex to rim, a new one "
                    "launched before the last is halfway down, so there are "
                    "always two or three on the sphere at once. Each is "
                    "coloured by when it left — over seven and a half "
                    "minutes they climb out of deep amber into gold, and "
                    "they get stronger the whole way."
                ),
            ),
            Movement(
                RingWave(
                    period=9.0,
                    sigma_deg=7.5,
                    launch_s=3.4,
                    gain_from=0.92,
                    gain_to=1.0,
                    arc_s=444.0,
                    meander=_DRIVE_BURN,
                    meander_s=444.0,
                ),
                444.0,
                fade=20.0,
                title="the-ecstasy",
                notes=(
                    "The same figure, and it will not stop. Rings launch "
                    "half a second sooner, the sphere is never not carrying "
                    "three of them, and the colour burns up through "
                    "white-gold at the top of the part — then walks back "
                    "down into amber, spent, without ever once dropping "
                    "the pulse."
                ),
            ),
        ]
    )


def _the_ballad() -> Conductor:
    """Part IIb (18:13): the congregation assembles, stays, and thins.

    Candles have three arcs and this uses all of them — how many are
    lit, how wide their pools burn, and how hot their cores sit — so
    the tender stretch is a gathering, then a held room, then people
    quietly leaving, rather than one slider crossing eighteen minutes.
    """
    # count sets the render cost: Candles evaluates an (n_lights x count)
    # pool matrix, and the ballad's three scenes are the one place in the
    # repertoire where two Candles render at once (mid-crossfade). 52
    # wide pools read as a full congregation and keep that seam affordable.
    common = dict(
        count=52,
        flicker_s=5.0,
        flutter=0.14,
        vary=0.85,
        ignite_flare=0.45,
        edge=0.05,
        floor_pos=0.045,
        salt="koln-ballad",
    )
    return Conductor(
        [
            Movement(
                Candles(
                    fill_from=0.10,
                    fill_to=0.62,
                    arc_s=400.0,
                    fill_gamma=0.72,
                    spot_deg=6.0,
                    spot_to=7.6,
                    **common,
                ),
                400.0,
                fade=0.0,
                title="the-gathering",
                notes=(
                    "The tender stretch opens with almost nobody there. A "
                    "few flames catch in the first seconds — each flaring "
                    "as it lights, none of them alike — and then the room "
                    "fills for six minutes in no hurry at all."
                ),
            ),
            Movement(
                Candles(
                    fill_from=0.62,
                    fill_to=0.86,
                    arc_s=380.0,
                    spot_deg=7.6,
                    spot_to=9.0,
                    pos_max=0.78,
                    pos_to=0.88,
                    **common,
                ),
                380.0,
                fade=10.0,  # the scenes are parameter-continuous: no long blend needed
                title="the-tender",
                notes=(
                    "The most beautiful playing on the record, and the "
                    "flames answer it by getting *warmer* rather than more "
                    "numerous: the pools widen, the cores climb the "
                    "palette, and a few candles gutter almost out and come "
                    "back. Arrived — this is what the whole side was for."
                ),
            ),
            Movement(
                Candles(
                    fill_from=0.86,
                    fill_to=0.40,
                    arc_s=313.0,
                    spot_deg=9.0,
                    pos_max=0.88,
                    die_frac=0.10,
                    **common,
                ),
                313.0,
                fade=10.0,
                title="letting-go",
                notes=(
                    "Nobody blows anything out. The newest flames simply "
                    "stop being there, a few quietly gutter and stay gone, "
                    "and the ones that were lit first are the ones still "
                    "burning when it ends."
                ),
            ),
        ]
    )


def _the_encore() -> Conductor:
    """Part IIc (6:56): the one written tune, and then the room.

    It is a live record and it ends the way live records end. The stars
    thin through the tune; underneath them a warm room comes up over
    the last minute and a quarter, and the sky is still there when the
    lights reach full.
    """
    return Conductor(
        [
            Movement(
                Starfield(
                    density=0.028,
                    star_l=0.62,
                    star_hue=70.0,
                    fill_from=0.90,
                    fill_to=0.52,
                    arc_s=340.0,
                    twinkle_s=7.0,
                    tint=0.55,
                    flutter=0.08,
                    sparse_boost=0.35,
                    swell=0.15,
                    churn=0.16,
                    salt=_ENCORE,
                ),
                340.0,
                fade=0.0,
                title="the-tune",
                notes=(
                    "The one written tune of the night, played like a "
                    "goodnight. Warm stars over the dark, thinning gently "
                    "for five and a half minutes — the newest letting go "
                    "first, the deep ones burning brighter as the sky "
                    "empties around them."
                ),
            ),
            Movement(
                Layered(
                    NoiseGlow(
                        palette=CANDLE,
                        scale=1.7,
                        speed=0.014,
                        contrast=1.25,
                        octaves=2,  # a slow warm floor under stars: cheap is fine
                        warp_amount=0.7,
                        gain_from=0.06,
                        gain_to=0.62,
                        arc_s=76.0,
                        tide_s=44.0,
                        tide_depth=0.22,
                        breathe_s=0.0,
                        seed=67,
                    ),
                    Starfield(
                        density=0.028,
                        star_l=0.62,
                        star_hue=70.0,
                        fill_from=0.52,
                        fill_to=0.44,
                        arc_s=76.0,
                        twinkle_s=7.0,
                        tint=0.55,
                        flutter=0.08,
                        sparse_boost=0.35,
                        churn=0.16,
                        salt=_ENCORE,
                    ),
                ),
                76.0,
                fade=22.0,
                title="the-lights-come-up",
                notes=(
                    "And then the room. A warm floor rises under the stars "
                    "over the last minute and a quarter — the house coming "
                    "back while the applause runs — and the sky is still up "
                    "there when the lights reach full. Nothing is switched "
                    "off; the night just stops being the only thing lit."
                ),
            ),
        ]
    )


def _part_i() -> Conductor:
    """Part I as movements on the user's cue sheet (seconds)."""
    return Conductor(
        [
            Movement(
                _vamp_banks(gain=0.62, gain_to=1.0, arc_s=304.0, tide_s=43.0),
                304.0,  # 0:00-5:04
                fade=10.0,
                title="vamp",
                notes=(
                    "Warm banks wandering and never settling — an "
                    "improvisation with no destination, only momentum, "
                    "coming up out of near-nothing over the whole five "
                    "minutes. When the left hand locks in, watch the tide."
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
                Layered(
                    _vamp_banks(gain=0.80, gain_to=1.05, arc_s=86.0),
                    _theme(9.6, 0.55),
                ),
                86.0,  # 7:14-8:40
                fade=6.0,
                title="the-theme",
                notes=(
                    "In earnest: the vamp back at full warmth and the "
                    "five-note phrase singing over it, around and "
                    "around, gaining a little every time it comes."
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
                _revisited(),
                981.0,  # 9:41-26:02
                fade=12.0,
                title="revisited",
                notes=(
                    "The theme returns settled and the side takes sixteen "
                    "minutes to finish: it settles, it climbs a long way, "
                    "and it comes to rest."
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
                    _the_drive(),
                    894.0,
                    fade=18.0,
                    title="part-iia",
                    notes=(
                        "Fifteen minutes of pulse that never lets up: the "
                        "figure establishing, then the ecstasy it turns "
                        "into. One long walk up through gold and back."
                    ),
                ),
                # Part IIb (18:13) — the lyrical heart.
                Movement(
                    _the_ballad(),
                    1093.0,
                    fade=22.0,
                    title="part-iib",
                    notes=(
                        "The tender stretch: a congregation gathering for "
                        "six minutes, holding and warming for six more, "
                        "and quietly thinning for the last five."
                    ),
                ),
                # Part IIc (6:56) — the encore.
                Movement(
                    _the_encore(),
                    416.0,
                    fade=16.0,
                    title="part-iic",
                    notes=(
                        "The encore — the one written tune of the night, "
                        "played like a goodnight — and then the house "
                        "lights coming up under the stars."
                    ),
                ),
            ]
        )

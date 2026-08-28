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

**Every track travels.** The durations are the album's; the arcs are
this show's reading of it. Each scene's parameters run over ``arc_s``
set to that track's own length, so no movement is the same at its end
as at its beginning — the vigil sky fills before the launch, the
signals are acquired, the morning goes pewter to pearl, and the stars
at the close let go of all but their deepest. One track needs two
scenes and gets them: "An Ending (Ascent)" is both words in its title,
so it is a nested pair — the climb, then the letting down.

Continuity, deliberately: tracks 1, 6 and 12 share a ``salt``, so they
are literally the same stars. The album ends under the sky it began
under, and it is the same sky, thinned.
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
# Signals: each ping is colored by WHEN it launched, so the sequence
# walks from a cold unlocked blue up into a warm, acquired gold — the
# signal being found over the length of the track.
_ACQUIRE = Palette(
    [
        (0.0, 0.30, 0.080, 250.0),
        (0.45, 0.55, 0.090, 215.0),
        (0.78, 0.70, 0.070, 150.0),
        (1.0, 0.76, 0.110, 92.0),
    ]
)
# Always Returning: the meander that comes home. Its last stop IS its
# first, so the final long wave arrives in the color the first one did.
_RETURNING = Palette(
    [
        (0.0, 0.50, 0.120, 175.0),
        (0.34, 0.66, 0.075, 212.0),
        (0.67, 0.60, 0.095, 246.0),
        (1.0, 0.50, 0.120, 175.0),
    ]
)

_VIGIL = "apollo-vigil"  # tracks 1, 6, 12: the same stars, three times


def _ascent() -> Conductor:
    """Track 5 as the two halves of its own title.

    An Ending (Ascent): the climb, then the letting down. The album's
    heart is the one place a single arc will not do — a rise that never
    settles is a fanfare, and this is not a fanfare.
    """
    return Conductor(
        [
            Movement(
                NoiseGlow(
                    palette=_ASCENT,
                    scale=1.5,
                    speed=0.017,
                    contrast=1.05,
                    gain_from=0.32,
                    gain_to=1.30,
                    arc_s=176.0,
                    breathe_s=44.0,
                    breathe_depth=0.12,
                    seed=15,
                ),
                176.0,
                fade=0.0,  # the outer movement's 30 s crossfade is the entry
                title="the-ascent",
                notes=(
                    "The golden swell, climbing for three minutes without "
                    "once stopping to admire itself. Let it get as bright "
                    "as the room can bear."
                ),
            ),
            Movement(
                NoiseGlow(
                    palette=_ASCENT,
                    scale=1.5,
                    speed=0.017,
                    contrast=1.05,
                    gain_from=1.30,
                    gain_to=0.82,
                    arc_s=88.0,
                    breathe_s=44.0,
                    breathe_depth=0.12,
                    seed=15,
                ),
                88.0,
                fade=20.0,
                title="the-ending",
                notes=(
                    "And the other word in the title. It does not resolve "
                    "and it does not crash — it simply stops needing to "
                    "climb, and lets itself down into the vigil again."
                ),
            ),
        ]
    )


class Apollo(Conductor):
    name = "apollo"
    description = "Cue-sheet show for Eno's Apollo (1983): pair with the album"
    audio = "apollo.mp3"
    notes = (
        "The record, played by the sphere: twelve tracks, twelve scenes, "
        "49:18. Load the album into var/audio and queue them together — "
        "the crossfades absorb pressing drift. Every track goes somewhere "
        "over its own length, and it ends under the stars it began under — "
        "the same stars, thinned."
    )

    def __init__(self) -> None:
        super().__init__(
            [
                # 1. Under Stars (4:29)
                Movement(
                    Starfield(
                        density=0.032,
                        twinkle_s=7.0,
                        sky_l=0.026,
                        fill_from=0.42,
                        fill_to=1.0,
                        arc_s=269.0,
                        sparse_boost=0.40,
                        swell=0.20,
                        tint=0.90,
                        flutter=0.09,
                        churn=0.18,
                        meteor_rate=0.35,
                        salt=_VIGIL,
                    ),
                    269.0,
                    fade=10.0,
                    title="under-stars",
                    notes=(
                        "The launch vigil, and the vigil is the sky arriving. "
                        "A handful of stars to begin with, burning near full "
                        "because there is nothing to share the dark with — "
                        "then more, and more, until the whole firmament is up "
                        "and waiting. Going: toward a full sky."
                    ),
                ),
                # 2. The Secret Place (3:31)
                Movement(
                    NoiseGlow(
                        palette=_GROTTO,
                        scale=2.4,
                        speed=0.012,
                        contrast=1.35,
                        gain_from=0.42,
                        gain_to=1.05,
                        arc_s=211.0,
                        tide_s=41.0,
                        tide_depth=0.30,
                        tide2_s=67.0,
                        tide2_depth=0.24,
                        tide2_angle=118.0,
                        breathe_s=0.0,
                        seed=8,
                    ),
                    211.0,
                    fade=20.0,
                    title="the-secret-place",
                    notes=(
                        "Underground blue, rising out of half-light for the "
                        "whole length of the track — the room is bigger every "
                        "time you look. Two slow tides cross each other "
                        "through it, so no two swells arrive the same way."
                    ),
                ),
                # 3. Matta (4:20)
                Movement(
                    AuroraVeils(
                        speed=0.55,
                        shimmer=0.22,
                        border=0.52,
                        crest_at=0.55,
                        activity_floor=0.30,
                        crest_width=0.30,
                        arc_s=260.0,
                        gain=1.15,
                        surge_s=31.0,
                        white_hot=0.86,
                        hot_hue=188.0,
                    ),
                    260.0,
                    fade=25.0,
                    title="matta",
                    notes=(
                        "Something alien stirring above — curtains that are "
                        "not weather. It gathers for two and a half minutes, "
                        "breaks up in surges that race the sphere with cold "
                        "white burning through the cores, and then withdraws "
                        "without ever explaining itself."
                    ),
                ),
                # 4. Signals (2:47)
                Movement(
                    RingWave(
                        period=8.5,
                        sigma_deg=5.0,
                        launch_s=4.2,
                        start_at=6.0,
                        gain_from=0.35,
                        gain_to=1.0,
                        arc_s=167.0,
                        meander=_ACQUIRE,
                        meander_s=167.0,
                    ),
                    167.0,
                    fade=15.0,
                    title="signals",
                    notes=(
                        "Radio pings walking the sphere, apex to rim, two "
                        "always in the air at once. Faint and cold blue at "
                        "first, then stronger, and every ping a little warmer "
                        "than the last one — by the end they are gold and "
                        "unmistakable. Something has been acquired."
                    ),
                ),
                # 5. An Ending (Ascent) (4:24) — the album's heart, in two.
                Movement(
                    _ascent(),
                    264.0,
                    fade=30.0,
                    title="an-ending",
                    notes=(
                        "The golden swell: three minutes of climb, then a "
                        "minute of letting down. Both words of the title, in "
                        "that order."
                    ),
                ),
                # 6. Under Stars II (3:23)
                Movement(
                    Starfield(
                        density=0.040,
                        twinkle_s=6.0,
                        sky_l=0.024,
                        fill_from=1.0,
                        fill_to=0.74,
                        arc_s=203.0,
                        swell=0.15,
                        sparse_boost=0.30,
                        tint=0.85,
                        flutter=0.08,
                        churn=0.16,
                        salt=_VIGIL,
                    ),
                    203.0,
                    fade=25.0,
                    title="under-stars-ii",
                    notes=(
                        "The same stars — the same salt, so these are "
                        "literally the ones from before the climb — but the "
                        "vigil has changed. The newest arrivals start letting "
                        "go, the deep ones hold and go on rising. Coming "
                        "from somewhere."
                    ),
                ),
                # 7. Drift (3:05)
                Movement(
                    NoiseGlow(
                        palette=SEA_GLASS,
                        scale=2.0,
                        speed=0.010,
                        contrast=1.7,
                        gain_from=1.0,
                        gain_to=0.80,
                        arc_s=185.0,
                        tide_s=185.0,
                        tide_depth=0.32,
                        breathe_s=51.0,
                        seed=23,
                    ),
                    185.0,
                    fade=25.0,
                    title="drift",
                    notes=(
                        "Weightless green-blue banks, barely moving. Nothing "
                        "to hold onto — one single swell crosses the whole "
                        "sphere over the whole track, the only event there "
                        "is, and you will not catch it moving."
                    ),
                ),
                # 8. Silver Morning (2:40)
                Movement(
                    NoiseGlow(
                        palette=_SILVER,
                        scale=1.8,
                        speed=0.020,
                        contrast=1.2,
                        gain_from=0.48,
                        gain_to=1.20,
                        arc_s=160.0,
                        breathe_s=31.0,
                        seed=29,
                    ),
                    160.0,
                    fade=20.0,
                    title="silver-morning",
                    notes=(
                        "First light with no color in it yet: pewter, then "
                        "pearl. The whole track is that one sentence — it "
                        "starts at the first word and arrives at the last."
                    ),
                ),
                # 9. Deep Blue Day (3:58)
                Movement(
                    NoiseGlow(
                        palette=_LAGOON,
                        scale=2.2,
                        speed=0.024,
                        contrast=1.1,
                        gain_from=0.82,
                        gain_to=1.12,
                        arc_s=238.0,
                        tide_s=44.0,
                        tide_depth=0.28,
                        tide2_s=71.0,
                        tide2_depth=0.22,
                        tide2_angle=104.0,
                        breathe_s=26.0,
                        seed=31,
                    ),
                    238.0,
                    fade=20.0,
                    title="deep-blue-day",
                    notes=(
                        "Lagoon light under the pedal steel — the one track "
                        "that smiles. Two tides cross in the shallows and "
                        "sand shows through where they meet; the water "
                        "warms all the way through the afternoon."
                    ),
                ),
                # 10. Weightless (4:35)
                Movement(
                    NoiseGlow(
                        palette=NIGHT_SKY,
                        scale=1.4,
                        speed=0.007,
                        contrast=1.0,
                        gain_from=1.40,
                        gain_to=1.02,
                        arc_s=275.0,
                        tide_s=61.0,
                        tide_depth=0.30,
                        tide2_s=97.0,
                        tide2_depth=0.22,
                        tide2_angle=126.0,
                        breathe_s=0.0,
                        seed=37,
                    ),
                    275.0,
                    fade=30.0,
                    title="weightless",
                    notes=(
                        "Floating in the big blue-black, two long swells the "
                        "only gravity — and they are the only thing keeping "
                        "score, because over four and a half minutes the "
                        "light quietly gives up a third of itself and you "
                        "never see it happen."
                    ),
                ),
                # 11. Always Returning (4:04)
                Movement(
                    RingWave(
                        period=21.0,
                        sigma_deg=10.0,
                        launch_s=10.5,
                        gain_from=0.72,
                        gain_to=1.0,
                        arc_s=244.0,
                        meander=_RETURNING,
                        meander_s=244.0,
                    ),
                    244.0,
                    fade=25.0,
                    title="always-returning",
                    notes=(
                        "Long waves coming home, twenty-one seconds apex to "
                        "rim, two always on the sphere. Each one is colored "
                        "by when it launched, and the palette they walk ends "
                        "exactly where it started — the last wave of the "
                        "track arrives in the color the first one did. They "
                        "know the way."
                    ),
                ),
                # 12. Stars (8:02)
                Movement(
                    Starfield(
                        density=0.034,
                        twinkle_s=8.5,
                        star_l=0.58,
                        sky_l=0.028,
                        fill_from=1.0,
                        fill_to=0.58,
                        arc_s=482.0,
                        swell=0.18,
                        sparse_boost=0.38,
                        tint=1.0,
                        flutter=0.08,
                        churn=0.22,
                        churn_life_s=11.0,
                        meteor_rate=0.45,
                        salt=_VIGIL,
                    ),
                    482.0,
                    fade=30.0,
                    title="stars",
                    notes=(
                        "Eight minutes of stars to carry it out, and they are "
                        "the ones from the launch vigil. The sky spends the "
                        "whole time letting go — youngest first, the deepest "
                        "holding to the end and burning brighter as the room "
                        "empties around them. It does not go dark. It ends "
                        "under its opening sky, thinned to the ones that "
                        "were always going to stay."
                    ),
                ),
            ]
        )

"""The shared pattern library: palettes, easing, fields, primitives.

These are the building blocks every book-two pattern and show composes
from, so they get direct unit coverage: perceptual blending takes hue
the short way, noise is deterministic everywhere, and primitives obey
the Pattern contract (stateless, finite, codec-safe) with a parameter
schema that fails loudly on typos.
"""

import numpy as np
import pytest

from luminary.geometry.lights import LightColumns
from luminary.patterns.easing import breath, env_ad, smoothstep, smootherstep, wrap01
from luminary.patterns.fields import _hash01, fbm, ring_field, value_noise, warp
from luminary.patterns.palettes import (
    AURORA,
    CANDLE,
    Palette,
    blend_oklch,
    oklch_to_vec,
    vec_to_oklch,
)
from luminary.patterns.primitives import (
    AuroraVeils,
    Candles,
    NoiseGlow,
    Primitive,
    RingWave,
    Starfield,
)


def make_lights(n=200, seed=0):
    ncols = max(int(c) for c in LightColumns) + 1
    rng = np.random.default_rng(seed)
    lights = np.zeros((n, ncols))
    lights[:, LightColumns.X] = rng.uniform(0.0, 240.0, n)
    lights[:, LightColumns.Y] = rng.uniform(0.0, 200.0, n)
    lights[:, LightColumns.PHI_S] = rng.uniform(0.0, 2.27, n)
    lights[:, LightColumns.THETA_S] = rng.uniform(-np.pi, np.pi, n)
    return lights


# ------------------------------------------------------------- palettes


def test_vec_roundtrip():
    lch = np.array([[0.5, 0.1, 30.0], [0.2, 0.0, 200.0], [0.9, 0.3, 359.0]])
    back = vec_to_oklch(oklch_to_vec(lch))
    assert np.allclose(back[:, :2], lch[:, :2], atol=1e-12)
    # Hue is undefined at C=0; check it only where chroma is real.
    assert np.allclose(back[[0, 2], 2], lch[[0, 2], 2], atol=1e-9)


def test_blend_takes_hue_the_short_way():
    a = np.array([[0.5, 0.2, 350.0]])
    b = np.array([[0.5, 0.2, 10.0]])
    mid = blend_oklch(a, b, 0.5)
    assert min(mid[0, 2], 360.0 - mid[0, 2]) < 1e-6  # through 0, not 180
    assert mid[0, 1] > 0.19  # chroma barely dips on a 20-degree arc


def test_blend_collapses_chroma_through_neutral():
    a = np.array([[0.5, 0.2, 0.0]])
    b = np.array([[0.5, 0.2, 180.0]])
    mid = blend_oklch(a, b, 0.5)
    assert mid[0, 1] < 1e-9  # complementary hues meet at gray
    assert abs(mid[0, 0] - 0.5) < 1e-12


def test_blend_weight_forms():
    a = np.array([[0.2, 0.1, 40.0], [0.2, 0.1, 40.0]])
    b = np.array([[0.8, 0.1, 40.0], [0.8, 0.1, 40.0]])
    assert np.allclose(blend_oklch(a, b, 0.0), a)
    assert np.allclose(blend_oklch(a, b, 1.0), b)
    per_light = blend_oklch(a, b, np.array([0.0, 1.0]))
    assert np.allclose(per_light[0], a[0]) and np.allclose(per_light[1], b[1])


def test_palette_sample_hits_stops_and_interpolates():
    pal = Palette([(0.0, 0.1, 0.05, 20.0), (1.0, 0.7, 0.15, 60.0)])
    ends = pal.sample(np.array([0.0, 1.0]))
    assert np.allclose(ends[0], [0.1, 0.05, 20.0], atol=1e-9)
    assert np.allclose(ends[1], [0.7, 0.15, 60.0], atol=1e-9)
    mid = pal.sample(np.array([0.5]))
    assert 0.1 < mid[0, 0] < 0.7
    out_of_range = pal.sample(np.array([-3.0, 7.0]))  # clipped, not wrapped
    assert np.allclose(out_of_range[0], ends[0]) and np.allclose(
        out_of_range[1], ends[1]
    )


def test_palette_validation():
    with pytest.raises(ValueError):
        Palette([(0.0, 0.5, 0.1, 0.0)])
    with pytest.raises(ValueError):
        Palette([(0.5, 0.5, 0.1, 0.0), (0.5, 0.6, 0.1, 0.0)])


def test_palette_shifted_and_dimmed():
    xs = np.linspace(0.0, 1.0, 7)
    base = CANDLE.sample(xs)
    shifted = CANDLE.shifted(90.0).sample(xs)
    assert np.allclose((shifted[:, 2] - base[:, 2]) % 360.0, 90.0, atol=1e-6)
    dimmed = CANDLE.dimmed(0.5).sample(xs)
    assert np.allclose(dimmed[:, 0], base[:, 0] * 0.5, atol=1e-9)
    assert np.all(dimmed[:, 1] <= base[:, 1] + 1e-9)


# --------------------------------------------------------------- easing


def test_easing_shapes_and_bounds():
    xs = np.linspace(-1.0, 2.0, 301)
    for fn in (lambda v: smoothstep(0.0, 1.0, v), lambda v: smootherstep(0.0, 1.0, v)):
        ys = fn(xs)
        assert ys[0] == 0.0 and ys[-1] == 1.0
        assert np.all(np.diff(ys) >= -1e-12)  # monotone
        assert abs(float(fn(0.5)) - 0.5) < 1e-12
    assert float(breath(0.0, 8.0)) == 0.0
    assert abs(float(breath(4.0, 8.0)) - 1.0) < 1e-12
    assert float(env_ad(-0.5, 1.0, 2.0)) == 0.0
    assert abs(float(env_ad(1.0, 1.0, 2.0)) - 1.0) < 1e-12
    assert float(env_ad(10.0, 1.0, 2.0)) < 0.02
    assert np.allclose(wrap01(np.array([-0.25, 1.25])), [0.75, 0.25])


# --------------------------------------------------------------- fields


def test_hash_deterministic_and_uniformish():
    ix = np.arange(10000, dtype=np.int64)
    iy = ix * 7 + 3
    a = _hash01(ix, iy, seed=42)
    b = _hash01(ix, iy, seed=42)
    assert np.array_equal(a, b)
    assert np.all((a >= 0.0) & (a < 1.0))
    assert abs(float(a.mean()) - 0.5) < 0.02
    assert not np.array_equal(a, _hash01(ix, iy, seed=43))
    # Large seeds wrap exactly instead of warning (uint64 semantics).
    big = _hash01(ix[:8], iy[:8], seed=0xFFFFFFFF)
    assert np.all((big >= 0.0) & (big < 1.0))


def test_value_noise_smooth_and_seeded():
    xs = np.linspace(0.0, 5.0, 400)
    ys = np.full_like(xs, 0.37)
    f = value_noise(xs, ys, seed=7)
    assert np.all((f >= 0.0) & (f < 1.0))
    assert np.max(np.abs(np.diff(f))) < 0.06  # smooth at this sampling
    assert np.array_equal(f, value_noise(xs, ys, seed=7))
    assert not np.array_equal(f, value_noise(xs, ys, seed=8))


def test_fbm_and_warp():
    rng = np.random.default_rng(1)
    x = rng.uniform(0.0, 4.0, 500)
    y = rng.uniform(0.0, 4.0, 500)
    f = fbm(x, y, seed=3, octaves=4)
    assert np.all((f >= 0.0) & (f < 1.0))
    assert float(f.std()) > 0.05  # actually textured
    wx, wy = warp(x, y, seed=3, amount=1.5)
    assert not np.allclose(wx, x) and not np.allclose(wy, y)
    assert np.max(np.abs(wx - x)) <= 0.75 + 1e-9  # bounded by amount/2


def test_ring_field_crest_and_spin():
    phi = np.linspace(0.0, np.radians(130.0), 200)
    az = np.zeros_like(phi)
    period = 4.0
    t = 1.0  # quarter descent
    intensity, hue = ring_field(phi, az, t, period)
    crest = float(phi[np.argmax(intensity)])
    assert abs(crest - 0.25 * np.radians(130.0)) < np.radians(1.5)
    assert float(np.max(intensity)) > 0.99
    # Hue is azimuth plus a per-wave spin: constant along this meridian,
    # and re-keyed on the next descent.
    assert float(np.ptp(hue)) < 1e-9
    _, hue2 = ring_field(phi, az, t + period, period)
    assert abs(float(hue[0]) - float(hue2[0])) > 1.0
    # Same wave, same spin: deterministic across calls.
    again = ring_field(phi, az, t, period)
    assert np.array_equal(again[0], intensity) and np.array_equal(again[1], hue)


# ----------------------------------------------------------- primitives


def test_primitive_param_schema():
    params = Starfield.params()
    assert "density" in params and "twinkle_s" in params
    assert "name" not in params and "render" not in params
    star = Starfield(density=0.5)
    assert star.density == 0.5 and star.param_values()["density"] == 0.5
    assert Starfield().density == Starfield.density  # defaults untouched
    info = star.info()
    assert info["params"]["density"] == 0.5


def test_primitive_rejects_unknown_params():
    with pytest.raises(TypeError, match="denstiy"):
        Starfield(denstiy=0.5)
    with pytest.raises(TypeError, match="parameters"):
        NoiseGlow(name="nope")  # name is reserved, not a parameter


def test_primitive_subclass_overrides_defaults():
    class Tuned(Starfield):
        density = 0.9

    assert Tuned.params()["density"] == 0.9
    assert Tuned().density == 0.9
    assert Tuned(density=0.1).density == 0.1


@pytest.mark.parametrize(
    "primitive",
    [
        Starfield(),
        Starfield(fill_from=0.1, fill_to=0.9, arc_s=200.0, meteor_rate=3.0),
        NoiseGlow(),
        NoiseGlow(gain_from=0.9, gain_to=0.3, arc_s=200.0, tide_s=40.0),
        AuroraVeils(),
        AuroraVeils(crest_at=0.6, arc_s=300.0),
        RingWave(),
        RingWave(palette=AURORA, gain_from=0.2, gain_to=1.0, arc_s=100.0),
        Candles(),
        Candles(fill_from=0.05, fill_to=0.9, arc_s=300.0),
        __import__("luminary.patterns.primitives", fromlist=["Embers"]).Embers(
            arc_s=400.0
        ),
    ],
    ids=[
        "starfield",
        "starfield-arc",
        "noiseglow",
        "noiseglow-arc",
        "auroraveils",
        "auroraveils-crest",
        "ringwave",
        "ringwave-arc",
        "candles",
        "candles-arc",
        "embers",
    ],
)
def test_primitives_obey_the_contract(primitive):
    lights = make_lights()
    frames = {}
    for t in (0.0, 3.7, 120.0):
        out = primitive.render(lights, t)
        assert out.shape == (lights.shape[0], 3)
        assert np.all(np.isfinite(out))
        assert np.all(out[:, 0] >= 0.0) and np.all(out[:, 0] <= 1.0)
        assert np.all(out[:, 1] >= 0.0) and np.all(out[:, 1] < 0.4)  # codec ceiling
        frames[t] = out
    # Stateless: revisiting a time reproduces it exactly (out of order).
    assert np.array_equal(primitive.render(lights, 3.7), frames[3.7])
    assert np.array_equal(primitive.render(lights, 0.0), frames[0.0])


def test_primitives_render_on_unfolded_nets_too():
    # No spherical columns: phi_theta falls back to planar stand-ins.
    lights = make_lights()
    lights[:, LightColumns.PHI_S] = np.nan
    lights[:, LightColumns.THETA_S] = np.nan
    for primitive in (AuroraVeils(), RingWave()):
        out = primitive.render(lights, 5.0)
        assert np.all(np.isfinite(out))


def test_starfield_density_zero_is_all_sky():
    lights = make_lights()
    out = Starfield(density=0.0).render(lights, 2.0)
    assert float(np.max(out[:, 0])) < 0.06  # nothing brighter than airglow
    star_lights = Starfield(density=1.0).render(lights, 1.6)
    assert float(np.max(star_lights[:, 0])) > 0.3  # somebody twinkles bright


def test_starfield_population_swells_by_seniority():
    """The fill arc: the sky populates without churn — every star of the
    sparse early sky is still there in the full one, and the population
    strictly grows (some stars stay; the fullness goes somewhere)."""
    lights = make_lights(n=1200, seed=2)
    sf = Starfield(fill_from=0.05, fill_to=1.0, arc_s=400.0, star_l=0.85)

    def bright(t):
        return set(np.flatnonzero(sf.render(lights, t)[:, 0] > 0.25).tolist())

    early, mid, late = bright(10.0), bright(200.0), bright(390.0)
    assert len(early) < len(mid) < len(late)
    assert early <= mid <= late  # seniority: arrivals only, no churn

    # Letting go runs in reverse: the late sky is a subset of the early
    # one, and never empties completely — the deepest stars hold.
    ebb = Starfield(fill_from=1.0, fill_to=0.08, arc_s=400.0, star_l=0.85)

    def bright_ebb(t):
        return set(np.flatnonzero(ebb.render(lights, t)[:, 0] > 0.25).tolist())

    assert bright_ebb(390.0) <= bright_ebb(10.0)
    assert 0 < len(bright_ebb(390.0)) < len(bright_ebb(10.0))


def test_embers_wind_is_visible_and_mortal():
    """The embers physics: sparks live in the cloud banks (never spread
    evenly); the gust front dims the cloud and the damage heals only
    slowly (still beaten down when the next gust comes); fanned coals
    hold their flare for seconds after the front passes; each pass
    consumes coals; the envelope swells before the long drain; dark_at
    fades the act out."""
    from luminary.patterns.fields import fbm, warp
    from luminary.patterns.primitives import Embers
    from luminary.patterns.util import plane_xy, seeded_random

    lights = make_lights(n=4000, seed=6)
    e = Embers(arc_s=240.0, swell_gain=1.25)
    n = lights.shape[0]
    u, v = plane_xy(lights)
    spark = seeded_random(f"{e.salt}-pick", n) < e.spark_density

    def cloud_field(t):
        uu = u * e.scale + t * e.drift
        vv = v * e.scale - t * e.drift * 0.71
        wu, wv = warp(uu, vv, e.seed, 1.1, octaves=2)
        return np.clip(fbm(wu, wv, e.seed + 10, octaves=3), 0.0, 1.0) ** e.contrast

    # Sparks are in the clouds: the field under lit sparks runs far
    # above the ambient field (stochastic density follows the banks).
    t0 = 30.0
    L0 = e.render(lights, t0)[:, 0]
    lit = spark & (L0 > 0.25)
    field = cloud_field(t0)
    assert lit.sum() > 12
    assert float(field[lit].mean()) > float(field.mean()) * 1.5

    # The gust front dims the cloud under it, and the wind helper is
    # the one source of the front (mid-sweep of gust 2 here).
    t = 2.0 * e.tide_s + e.sweep_s / 2.0
    wind, _passes, _since = e._wind(u, v, t)
    crest, calm = wind > 0.7, wind < 0.05
    L = e.render(lights, t)[:, 0]
    assert float(L[crest & ~spark].mean()) < float(L[calm & ~spark].mean()) * 0.9
    # Between gusts the FRONT is gone (sudden, not ambient)...
    quiet, _p, _s = e._wind(u, v, 2.0 * e.tide_s + e.sweep_s + 3.0)
    assert float(np.max(quiet)) < 1e-6
    # ...but the scar stays: the beaten-down cloud has healed only
    # partway by the eve of the next gust.
    hi = ~spark & (field > np.quantile(field, 0.75))
    before = float(e.render(lights, e.tide_s - 1.5)[hi, 0].mean())
    after = float(e.render(lights, e.tide_s + e.sweep_s + 4.0)[hi, 0].mean())
    eve = float(e.render(lights, 2.0 * e.tide_s - 1.5)[hi, 0].mean())
    assert after < before * 0.85  # the pass beat the cloud down
    assert eve < before * 0.95  # and it has NOT sprung back by the next

    # A fanned coal holds its flare for seconds after the front passes.
    a = np.radians(e.tide_angle)
    proj = 0.5 * (u * np.cos(a) + v * np.sin(a))
    tails = e.flare_s * (0.5 + 1.1 * seeded_random(f"{e.salt}-tail", n))
    life = seeded_random(f"{e.salt}-life", n)
    coals = np.flatnonzero(spark & (life > 0.8) & (field > 0.35) & (tails > 4.5))
    assert coals.size > 0
    i = int(coals[0])
    cross = 2.0 * e.tide_s + float(
        np.clip((proj[i] + 0.62) * e.sweep_s / 1.24, 0.0, e.sweep_s)
    )
    resting = float(e.render(lights, cross - 4.0)[i, 0])
    flared = float(e.render(lights, cross + 2.5)[i, 0])
    assert flared > resting * 1.3  # still flaring seconds after the pass

    def live(tt):
        return int(np.sum(e.render(lights, tt)[:, 0] * spark > 0.17))

    early, late = live(20.0), live(230.0)
    assert early > live(120.0) > late >= 0
    assert early > 20

    means = {
        tt: float(np.mean(e.render(lights, tt)[:, 0])) for tt in (3.0, 53.0, 230.0)
    }
    assert means[53.0] > means[3.0] * 1.2  # the defiant swell
    assert means[230.0] < means[53.0] * 0.5  # the long drain

    # The dying fall: past dark_at the whole scene fades toward dark.
    dying = Embers(arc_s=240.0, dark_at=186.0, dark_s=54.0, dark_floor=0.10)
    lit_now = float(np.mean(Embers(arc_s=240.0).render(lights, 245.0)[:, 0]))
    assert float(np.mean(dying.render(lights, 245.0)[:, 0])) < lit_now * 0.25


def test_motif_plays_its_phrase_and_rests():
    from luminary.patterns.primitives import Motif

    lights = make_lights(n=1200, seed=8)
    m = Motif()
    # During the phrase the anchors pulse in sequence; between cycles
    # the field rests near dark. Peak location advances with the notes.
    peaks = [
        float(m.render(lights, t)[:, 0].max()) for t in np.arange(0.1, m.cycle_s, 0.2)
    ]
    assert max(peaks) > 0.25
    assert min(peaks) < 0.1  # rests between notes/cycles
    a = m.render(lights, 2.2)
    m.render(lights, 500.0)
    assert np.array_equal(m.render(lights, 2.2), a)


def test_spiegel_is_mirror_symmetric():
    from luminary.patterns.registry import default_registry

    spiegel = default_registry().get("spiegel")
    n = 400
    ncols = max(int(c) for c in LightColumns) + 1
    rng = np.random.default_rng(12)
    phi = rng.uniform(0.05, 2.2, n)
    th = rng.uniform(0.0, np.pi, n)
    lights = np.zeros((2 * n, ncols))
    lights[:n, LightColumns.PHI_S] = phi
    lights[:n, LightColumns.THETA_S] = th
    lights[n:, LightColumns.PHI_S] = phi
    lights[n:, LightColumns.THETA_S] = -th  # the mirror pair
    for t in (3.0, 20.0, 47.0, 300.0):
        out = spiegel.render(lights, t)
        assert np.allclose(out[:n], out[n:], atol=1e-9), "mirror broken"
        assert np.all(np.isfinite(out)) and float(out[:, 1].max()) < 0.4


def test_starfield_meteors_burst_toward_full():
    lights = make_lights(n=1500, seed=4)
    sf = Starfield(meteor_rate=6.0)
    peak = max(float(sf.render(lights, t)[:, 0].max()) for t in np.arange(0, 90, 0.5))
    assert peak > 0.8  # a streak is a figure: it may burst near full
    quiet = Starfield(meteor_rate=0.0)
    calm = max(
        float(quiet.render(lights, t)[:, 0].max()) for t in np.arange(0, 30, 1.0)
    )
    assert calm < 0.75  # without meteors the sky keeps its lane


# ------------------------------------------------- composed: small planet


def test_small_planet_day_night_and_cities():
    from luminary.patterns.registry import default_registry

    planet = default_registry().get("small_planet")
    lights = make_lights(n=800, seed=3)
    t = 150.0  # quarter day: sun over azimuth 90°

    out = planet.render(lights, t)
    assert np.all(np.isfinite(out))
    assert np.all(out[:, 1] < 0.4)

    # The subsolar hemisphere carries the day; the antisolar side is night.
    phi = lights[:, LightColumns.PHI_S]
    th = lights[:, LightColumns.THETA_S]
    alpha = 2.0 * np.pi * t / planet.day_s
    insol = np.sin(phi) * np.cos(th - alpha)
    lit = float(np.mean(out[insol > 0.5, 0]))
    dark = float(np.mean(out[insol < -0.5, 0]))
    assert lit > 4.0 * dark
    assert dark < 0.08  # night is genuinely dark

    # Statics memoization is not state: interleaved times reproduce exactly.
    again = planet.render(lights, t)
    assert np.array_equal(out, again)

    # City lights are what glows on the dark side: with cities disabled,
    # the darkest hemisphere loses its bright outliers (moon aside).
    cls = type(planet)
    no_cities = cls(city_density=0.0, moon_s=1e9)  # park the moon far away
    with_cities = cls(moon_s=1e9)
    dark_mask = insol < -0.5
    bright_no = float(np.max(no_cities.render(lights, t)[dark_mask, 0]))
    bright_with = float(np.max(with_cities.render(lights, t)[dark_mask, 0]))
    assert bright_with > bright_no + 0.1


# ---------------------------------------------------- composed: fireflies


def test_fireflies_synchrony_breathes():
    from luminary.patterns.registry import default_registry

    flies = default_registry().get("fireflies")
    assert flies._coherence(0.0) == 0.0
    assert flies._coherence(flies.sync_period / 2.0) == 1.0

    lights = make_lights(n=900, seed=5)
    chaos_t, unison_t = 21.3, 21.3 + flies.sync_period / 2.0

    def slot_profile(t0):
        means, peaks = [], []
        for dt in np.arange(0.0, flies.interval_s, 0.26):
            out = flies.render(lights, t0 + dt)
            assert np.all(np.isfinite(out))
            assert np.all(out[:, 0] <= 1.0) and np.all(out[:, 1] < 0.4)
            means.append(float(np.mean(out[:, 0])))
            peaks.append(float(np.max(out[:, 0])))
        return means, peaks

    chaos_means, chaos_peaks = slot_profile(chaos_t)
    unison_means, _ = slot_profile(unison_t)

    # In chaos, flashes are scattered: the meadow-wide mean barely moves.
    # In unison, everyone flashes together: the mean visibly pulses.
    chaos_swing = max(chaos_means) / min(chaos_means)
    unison_swing = max(unison_means) / min(unison_means)
    assert chaos_swing < 1.8
    assert unison_swing > 2.0
    assert max(chaos_peaks) > 0.3  # individual flashes still read as events

    # A flash is a local pool, not a wash: even at the collective peak,
    # most of the meadow stays dark.
    brightest = flies.render(lights, unison_t + float(np.argmax(unison_means)) * 0.26)
    assert float(np.mean(brightest[:, 0] > 0.3)) < 0.3

    # Stateless across interleaved times.
    a = flies.render(lights, 33.3)
    flies.render(lights, 500.0)
    assert np.array_equal(flies.render(lights, 33.3), a)


# -------------------------------------------------------- composed: relay


def test_relay_races_the_strip_order():
    from luminary.patterns.registry import default_registry
    from luminary.patterns.util import seeded_random

    relay = default_registry().get("relay")
    # Four synthetic strips of 60 LEDs: lanes are (controller, channel).
    ncols = max(int(c) for c in LightColumns) + 1
    lights = np.zeros((4 * 60, ncols))
    lights[:, LightColumns.CHANNEL] = np.repeat(np.arange(4), 60)
    lights[:, LightColumns.INDEX] = np.tile(np.arange(60), 4)
    chan = lights[:, LightColumns.CHANNEL]

    # Mid-race: each lane carries one compact bead, not a wash.
    out = relay.render(lights, 6.0)
    assert np.all(np.isfinite(out)) and float(np.max(out[:, 1])) < 0.4
    for ch in range(4):
        bright = int(np.sum(out[chan == ch, 0] > 0.3))
        assert 0 < bright <= 16, f"lane {ch}: {bright} bright LEDs"

    # The winner's whole lane floods just after its drawn finish time.
    finish = relay.race_s * (0.62 + 0.33 * seeded_random(f"{relay.salt}-T-0", 4))
    winner = int(np.argmin(finish))
    flood = relay.render(lights, float(finish[winner]) + 0.25)
    assert float(np.min(flood[chan == winner, 0])) > 0.15
    assert float(np.mean(flood[chan != winner, 0])) < 0.15

    # The rest phase settles dark, and the whole thing is seekable.
    rest = relay.render(lights, relay.race_s + 3.0)
    assert float(np.max(rest[:, 0])) < 0.12
    a = relay.render(lights, 6.0)
    relay.render(lights, 1234.5)
    assert np.array_equal(relay.render(lights, 6.0), a)


def test_starfield_breathes_and_colors_its_stars():
    """First-stars physics: churn stars rise AND fall on their own
    clocks; tint spreads star color warm-to-blue; a sparse sky runs its
    lit stars brighter than a full one runs them."""
    from luminary.patterns.primitives import Starfield

    lights = make_lights(n=3000, seed=12)
    s = Starfield(
        density=0.035,
        star_l=0.88,
        fill_from=0.04,
        fill_to=1.0,
        arc_s=132.0,
        tint=1.0,
        flutter=0.10,
        sparse_boost=0.45,
        churn=0.30,
    )
    # An ephemeral: somewhere lit now that is dark a window later and
    # was dark a window before (rise and fall, not one-way).
    env_now = s._churn(40.0, 3000)
    i = int(np.flatnonzero(env_now > 0.9)[0])
    span = s.churn_life_s
    assert (
        s._churn(40.0 - 2.0 * span, 3000)[i] < 0.9
        or s._churn(40.0 + 2.0 * span, 3000)[i] < 0.9
    )
    # Tint: both warm and cool stars exist in one frame.
    f = s.render(lights, 100.0)
    hot = f[:, 0] > 0.3
    hues = f[hot, 2]
    assert ((hues < 90.0) | (hues > 330.0)).any() and (
        (hues > 180.0) & (hues < 300.0)
    ).any()
    # Sparse duty: the brightest star early (sky nearly empty) beats the
    # brightest at the same twinkle phase with no boost.
    plain = Starfield(
        density=0.035, star_l=0.88, fill_from=0.04, fill_to=1.0, arc_s=132.0
    )
    assert float(s.render(lights, 8.0)[:, 0].max()) > float(
        plain.render(lights, 8.0)[:, 0].max()
    )
    # Stateless.
    assert np.array_equal(s.render(lights, 77.7), s.render(lights, 77.7))


def test_starfall_empties_the_sky_one_streak_at_a_time():
    """The stars leave by falling: departures follow the one/few/wave/
    trickle schedule, a falling star leaves a streak, and the keep
    fraction never falls."""
    from luminary.patterns.primitives import Starfall
    from luminary.patterns.util import seeded_random

    lights = make_lights(n=3000, seed=13)
    sf = Starfall(
        density=0.035, star_l=0.70, sky_l=0.024, fall_delay=16.0, fall_span=181.0
    )
    pick = seeded_random(f"{sf.salt}-pick", 3000)
    star = pick < sf.density
    T = sf._departures(pick)[star]
    finite = np.sort(T[np.isfinite(T)])
    # The keepers: about the keep fraction of the population never falls.
    assert abs(1.0 - finite.size / star.sum() - sf.keep) < 0.06
    # The schedule has a shape: openers spaced out, the wave dense.
    gaps = np.diff(finite)
    openers = gaps[finite[:-1] < sf.fall_delay + 0.2 * sf.fall_span]
    wave = gaps[
        (finite[:-1] > sf.fall_delay + 0.4 * sf.fall_span)
        & (finite[:-1] < sf.fall_delay + 0.6 * sf.fall_span)
    ]
    assert float(np.median(openers)) > 3.0 * float(np.median(wave))
    # A streak: sampling right after one departure lights a trail well
    # beyond the star's own pixel.
    t_probe = float(finite[finite.size // 2]) + 0.5
    frame = sf.render(lights, t_probe)
    assert float(frame[:, 0].max()) > 0.7
    assert int((frame[:, 0] > 0.4).sum()) > 3
    # The sky really empties: far fewer lit stars late than early.
    early = int((sf.render(lights, 5.0)[:, 0] > 0.25).sum())
    late = int(
        (sf.render(lights, sf.fall_delay + sf.fall_span + 10.0)[:, 0] > 0.25).sum()
    )
    assert late < early * 0.35
    assert late >= 3  # the keepers hold
    assert np.array_equal(sf.render(lights, 99.9), sf.render(lights, 99.9))


def test_ringwave_launch_cadence_and_meander():
    """Rings launch on their own cadence (two share the sphere), the
    first too-dim toll is dropped, and each ring's color walks the
    meander palette — green early, warm red late."""
    from luminary.patterns.palettes import Palette
    from luminary.patterns.primitives import RingWave

    meander = Palette(
        [
            (0.0, 0.50, 0.13, 150.0),
            (0.33, 0.72, 0.06, 225.0),
            (0.62, 0.68, 0.07, 300.0),
            (1.0, 0.30, 0.11, 30.0),
        ]
    )
    lights = make_lights(n=1500, seed=14)
    r = RingWave(
        period=14.0,
        sigma_deg=6.0,
        launch_s=7.0,
        start_at=7.0,
        gain_from=0.22,
        gain_to=1.0,
        arc_s=110.0,
        meander=meander,
        meander_s=439.0,
    )
    # Before the first launch: nothing but the floor.
    assert float(r.render(lights, 3.0)[:, 0].max()) < 0.05

    # Mid-act: hue near the green start; late: warm red, and dimmer.
    def ring_hues(t):
        f = r.render(lights, t)
        m = f[:, 0] > 0.10
        return f[m, 2], f[:, 0].max()

    hues_early, _ = ring_hues(12.0)
    assert ((hues_early > 120.0) & (hues_early < 200.0)).all()
    hues_late, max_late = ring_hues(425.0)
    assert ((hues_late < 60.0) | (hues_late > 350.0)).all()
    _, max_mid = ring_hues(200.0)
    assert max_late < max_mid * 0.7  # the red end dims


def test_candles_anchor_seats_and_the_sighing_breath():
    """The gathering starts at the sculpture's anchor seats and the
    snuff wave takes every flame, leaving the warm floor."""
    from luminary.patterns.primitives import Candles
    from luminary.patterns.util import phi_theta

    anchors = ((54.0, 37.38), (-90.0, 37.38), (0.0, 90.0))
    lights = make_lights(n=3000, seed=15)
    c = Candles(
        anchors=anchors,
        fill_from=0.0,
        fill_to=1.0,
        arc_s=130.0,
        fill_gamma=0.75,
        spot_to=9.5,
        pos_to=1.0,
        flutter=0.16,
        snuff_at=138.0,
        snuff_s=13.0,
        floor_pos=0.05,
    )
    phi, th = phi_theta(lights)
    span = float(np.max(phi))
    sp = np.sin(phi)
    nl = np.column_stack([sp * np.cos(th), sp * np.sin(th), np.cos(phi)])

    def near(az_deg, ph_deg):
        scale = span / np.radians(c.anchor_span_deg)
        az, ph = np.radians(az_deg), np.radians(ph_deg) * scale
        ax = np.array([np.sin(ph) * np.cos(az), np.sin(ph) * np.sin(az), np.cos(ph)])
        return np.degrees(np.arccos(np.clip(nl @ ax, -1, 1))) < 6.0

    early = c.render(lights, 4.0)[:, 0]
    anchor_l = np.mean([early[near(a, p)].mean() for a, p in anchors])
    assert float(anchor_l) > float(early.mean()) * 1.8  # seats lead
    roar = float(c.render(lights, 135.0)[:, 0].mean())
    gone = c.render(lights, 156.0)[:, 0]
    assert roar > 0.25  # the roaring wave
    assert float(gone.max()) < 0.10  # the breath took every flame
    assert float(gone.mean()) > 0.012  # onto the warm smoke floor


def test_aurora_crest_is_hot_and_rayed():
    """The storm's crest runs far hotter than its floor, with fine
    spatial structure (rays), and never saturates flat."""
    from luminary.patterns.primitives import AuroraVeils

    lights = make_lights(n=3000, seed=16)
    v = AuroraVeils(
        speed=1.3,
        crest_at=0.45,
        activity_floor=0.5,
        arc_s=391.0,
        gain=1.35,
        surge_s=24.0,
    )
    calm = v.render(lights, 15.0)[:, 0]
    crest = v.render(lights, 176.0)[:, 0]
    assert float(np.quantile(crest, 0.95)) > float(np.quantile(calm, 0.95)) * 1.4
    assert float(crest.max()) > 0.7  # the cores burn toward white
    assert float(crest.mean()) < 0.42  # still a night sky, not a blast
    # Rays: real spatial variance among the lit region, not one wash.
    lit = crest > 0.15
    assert float(np.std(crest[lit])) > 0.08

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
    [Starfield(), NoiseGlow(), AuroraVeils(), RingWave(), RingWave(palette=AURORA)],
    ids=["starfield", "noiseglow", "auroraveils", "ringwave", "ringwave-palette"],
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

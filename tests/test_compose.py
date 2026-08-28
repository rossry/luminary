"""Conductor composition: movements, crossfades, and the Nocturne show.

The conductor must stay inside the pattern contract (stateless in
(lights, t), seekable at any time) while guaranteeing the performance
envelope: at most two child renders per frame, exactly one outside
fade windows. Probe patterns count their own render calls to pin that.
"""

import numpy as np
import pytest

from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern
from luminary.patterns.compose import Conductor, Movement
from luminary.patterns.easing import smoothstep
from luminary.patterns.palettes import blend_oklch
from luminary.patterns.registry import default_registry


class Probe(Pattern):
    """Solid-level pattern that records every (t) it renders."""

    name = "probe"
    description = "test probe"

    def __init__(self, level: float, hue: float = 40.0):
        self.level = level
        self.hue = hue
        self.calls: list = []

    def render(self, lights, t):
        self.calls.append(float(t))
        out = np.zeros((lights.shape[0], 3))
        out[:, 0] = self.level
        out[:, 1] = 0.1
        out[:, 2] = self.hue
        return out


def make_lights(n=16):
    ncols = max(int(c) for c in LightColumns) + 1
    return np.zeros((n, ncols))


def test_movement_validation():
    p = Probe(0.5)
    with pytest.raises(ValueError):
        Movement(p, 0.0)
    with pytest.raises(ValueError):
        Movement(p, 10.0, fade=-1.0)
    with pytest.raises(ValueError):
        Movement(p, 10.0, fade=11.0)  # fade must fit inside the movement
    with pytest.raises(ValueError):
        Conductor([])


def test_slot_selection_and_local_time():
    a, b, c = Probe(0.2), Probe(0.5), Probe(0.8)
    show = Conductor(
        [
            Movement(a, 10.0, fade=0.0),
            Movement(b, 5.0, fade=0.0),
            Movement(c, 5.0, fade=0.0),
        ]
    )
    assert show._slot(0.0) == (0, 0.0)
    assert show._slot(9.999) == (0, pytest.approx(9.999))
    assert show._slot(10.0) == (1, 0.0)  # boundary belongs to the new movement
    assert show._slot(14.5) == (1, pytest.approx(4.5))
    assert show._slot(15.0) == (2, 0.0)
    assert show._slot(99.0) == (2, pytest.approx(84.0))  # holds the last movement
    assert show.duration == 20.0 and show.total == 20.0


def test_one_render_outside_fades_two_inside():
    a, b = Probe(0.2), Probe(0.8)
    show = Conductor([Movement(a, 10.0, fade=0.0), Movement(b, 10.0, fade=4.0)])
    lights = make_lights()

    show.render(lights, 5.0)  # mid-movement A
    assert (len(a.calls), len(b.calls)) == (1, 0)

    show.render(lights, 12.0)  # inside B's fade window
    assert (len(a.calls), len(b.calls)) == (2, 1)
    assert a.calls[-1] == pytest.approx(12.0)  # A continues past its end
    assert b.calls[-1] == pytest.approx(2.0)  # B runs on movement-local time

    show.render(lights, 15.0)  # past the fade
    assert (len(a.calls), len(b.calls)) == (2, 2)


def test_crossfade_endpoints_and_midpoint():
    a, b = Probe(0.2, hue=350.0), Probe(0.8, hue=10.0)
    show = Conductor([Movement(a, 10.0, fade=0.0), Movement(b, 10.0, fade=4.0)])
    lights = make_lights()

    at_start = show.render(lights, 10.0)  # weight 0: entirely A, continued
    assert np.allclose(at_start[:, 0], 0.2) and np.allclose(at_start[:, 2], 350.0)

    mid = show.render(lights, 12.0)  # smoothstep(0.5) = 0.5 exactly
    expect = blend_oklch(a.render(lights, 12.0), b.render(lights, 2.0), 0.5)
    assert np.allclose(mid, expect)
    assert min(float(mid[0, 2]), 360.0 - float(mid[0, 2])) < 1e-6  # short way

    at_end = show.render(lights, 14.0)  # weight 1: entirely B
    assert np.allclose(at_end[:, 0], 0.8) and np.allclose(at_end[:, 2], 10.0)


def test_first_movement_fades_in_from_black():
    a = Probe(0.6)
    show = Conductor([Movement(a, 10.0, fade=4.0)])
    lights = make_lights()
    dark = show.render(lights, 0.0)
    assert np.allclose(dark[:, 0], 0.0) and np.allclose(dark[:, 1], 0.0)
    half = show.render(lights, 2.0)
    assert np.allclose(half[:, 0], 0.3)  # L halfway up
    assert np.allclose(half[:, 2], a.hue)  # hue held while rising from black


def test_loop_wraps_and_fades_from_the_last_movement():
    a, b = Probe(0.2), Probe(0.8)
    show = Conductor(
        [Movement(a, 10.0, fade=4.0), Movement(b, 5.0, fade=0.0)], loop=True
    )
    lights = make_lights()
    assert show.duration is None  # loops forever: no advance signal

    wrapped = show.render(lights, 15.5)  # == t 0.5, inside A's fade
    assert b.calls[-1] == pytest.approx(5.5)  # last movement continues over the seam
    assert a.calls[-1] == pytest.approx(0.5)
    expect = blend_oklch(
        b.render(lights, 5.5), a.render(lights, 0.5), float(smoothstep(0.0, 4.0, 0.5))
    )
    assert np.allclose(wrapped, expect)


def test_conductor_is_stateless_and_seekable():
    registry = default_registry()
    show = registry.get("nocturne")
    lights = make_lights(48)
    # Real coordinates so every movement has something to render.
    rng = np.random.default_rng(4)
    lights[:, LightColumns.X] = rng.uniform(0, 100, 48)
    lights[:, LightColumns.Y] = rng.uniform(0, 80, 48)
    lights[:, LightColumns.PHI_S] = rng.uniform(0, 2.2, 48)
    lights[:, LightColumns.THETA_S] = rng.uniform(-np.pi, np.pi, 48)
    a = show.render(lights, 500.0)
    show.render(lights, 3100.0)
    show.render(lights, 12.0)
    assert np.array_equal(show.render(lights, 500.0), a)


def test_nocturne_is_a_registered_hour():
    registry = default_registry()
    show = registry.get("nocturne")
    assert show.duration == 3600.0
    rows = show.schedule()
    assert len(rows) == 7
    assert rows[0]["start"] == 0.0
    starts = [row["start"] for row in rows]
    assert starts == sorted(starts)
    assert sum(row["duration"] for row in rows) == 3600.0

    lights = make_lights(60)
    rng = np.random.default_rng(9)
    lights[:, LightColumns.X] = rng.uniform(0, 240, 60)
    lights[:, LightColumns.Y] = rng.uniform(0, 200, 60)
    lights[:, LightColumns.PHI_S] = rng.uniform(0, 2.27, 60)
    lights[:, LightColumns.THETA_S] = rng.uniform(-np.pi, np.pi, 60)
    # Probe every movement boundary, mid-fade, and past the end.
    probes = [0.0, 6.0]
    for row in rows[1:]:
        probes += [row["start"] - 1.0, row["start"] + row["fade"] / 2.0]
    probes += [3599.0, 3660.0]
    for t in probes:
        out = show.render(lights, t)
        assert np.all(np.isfinite(out))
        assert np.all(out[:, 0] >= 0.0) and np.all(out[:, 0] <= 1.0)
        assert np.all(out[:, 1] >= 0.0) and np.all(out[:, 1] < 0.4)


def test_apollo_matches_the_1983_cue_sheet():
    registry = default_registry()
    show = registry.get("apollo")
    assert show.duration == 2958.0  # 49:18, the original edition
    rows = show.schedule()
    assert len(rows) == 12
    assert rows[4]["start"] == 907.0  # An Ending (Ascent) begins at 15:07
    assert rows[11]["start"] == 2476.0  # Stars begins at 41:16
    assert rows[11]["duration"] == 482.0

    lights = make_lights(40)
    rng = np.random.default_rng(11)
    lights[:, LightColumns.X] = rng.uniform(0, 240, 40)
    lights[:, LightColumns.Y] = rng.uniform(0, 200, 40)
    lights[:, LightColumns.PHI_S] = rng.uniform(0, 2.27, 40)
    lights[:, LightColumns.THETA_S] = rng.uniform(-np.pi, np.pi, 40)
    for t in (0.0, 907.0 + 15.0, 2476.0 + 240.0, 2957.0, 3000.0):
        out = show.render(lights, t)
        assert np.all(np.isfinite(out))
        assert np.all(out[:, 0] >= 0.0) and np.all(out[:, 0] <= 1.0)
        assert np.all(out[:, 1] >= 0.0) and np.all(out[:, 1] < 0.4)


def test_overnight_nests_the_repertoire():
    registry = default_registry()
    over = registry.get("overnight")
    noc = registry.get("nocturne")
    assert over.duration is None  # loops: the stage plays it until skipped
    assert over.total == 13200.0  # one 3h40m pass
    assert len(over.schedule()) == 8

    lights = make_lights(50)
    rng = np.random.default_rng(6)
    lights[:, LightColumns.X] = rng.uniform(0, 240, 50)
    lights[:, LightColumns.Y] = rng.uniform(0, 200, 50)
    lights[:, LightColumns.PHI_S] = rng.uniform(0, 2.27, 50)
    lights[:, LightColumns.THETA_S] = rng.uniform(-np.pi, np.pi, 50)
    lights[:, LightColumns.CHANNEL] = np.repeat(np.arange(5), 10)
    lights[:, LightColumns.INDEX] = np.tile(np.arange(10), 5)

    # Chapter 1 IS nocturne — the same movement list by import, so the
    # frames are bit-identical outside the outer crossfades.
    assert np.array_equal(over.render(lights, 1800.0), noc.render(lights, 1800.0))
    # The loop seam is exact: t and t + total render identically.
    assert np.array_equal(
        over.render(lights, 7.0), over.render(lights, 7.0 + over.total)
    )


def test_registry_finds_book_two_and_volumes():
    registry = default_registry()
    names = set(registry.patterns)
    # book-one (moved), conifer (moved), book-two (new) all discovered.
    assert {"aurora", "vespers", "life", "serpent"} <= names
    assert {"nocturne", "starlight", "weather", "veils", "ringfall"} <= names
    assert {"small_planet", "fireflies", "relay", "apollo", "overnight"} <= names
    assert not registry.errors, f"pattern load errors: {registry.errors}"

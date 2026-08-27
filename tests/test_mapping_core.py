"""Mapping core: plan derivation, the state machine, renderers, session."""

import numpy as np
import pytest

from luminary.geometry.lights import LightColumns
from luminary.geometry.net import Net
from luminary.geometry.pentagon import capture
from luminary.mapping import render as R
from luminary.mapping.plan import Plan
from luminary.mapping.session import SessionCore
from luminary.mapping.state import (
    Event,
    initial_state,
    resume_state,
    step,
)

CONTROLLERS = [3, 1, 4, 0, 6, 2, 5]


@pytest.fixture(scope="module")
def plan():
    return Plan.load()


@pytest.fixture(scope="module")
def net_lights(plan):
    from pathlib import Path

    configs = Path(__file__).resolve().parents[1] / "configs"
    return capture(Net.from_json_file(configs / f"{plan.net_name}.json"))


def test_plan_derivation(plan):
    # Production default: 4A-33 with the data-aux wiring — six boards
    # cover all 33 panels; the front unit (8) fields no board.
    assert plan.net_name == "4A-33" and plan.data_aux
    assert len(plan.units) == 6 and 8 not in plan.units
    assert plan.n_panels == 33
    for unit, panels in plan.panels.items():
        assert 0 < len(panels) <= 8
        for p in panels:
            # The six-red corner is a vertex of the face itself.
            assert p.corner_vertex in p.face
    # The three door-side faces ride the flanks: two on the screen-right
    # hex (9, board 2 in plan order), one on the left hex (7).
    assert plan.units[1] == 9
    assert plan.by_face[(3, 4, 8)].unit_vertex == 9
    assert plan.by_face[(4, 8, 14)].unit_vertex == 9
    assert plan.by_face[(3, 8, 13)].unit_vertex == 7
    # Their strip start corner is physical and does not move with aux.
    for face in [(3, 4, 8), (3, 8, 13), (4, 8, 14)]:
        assert plan.by_face[face].corner_vertex == 8


def test_plan_without_aux():
    base = Plan.load("4A-33", data_aux=False)
    assert len(base.units) == 7 and 8 in base.units
    assert len(base.panels[8]) == 3
    assert base.n_panels == 33


def test_state_machine_full_walk(plan):
    state = initial_state(plan, CONTROLLERS)
    assert state.stage == "ports"
    # Cycling never selects an assigned controller; enter assigns all.
    for _ in plan.units:
        state = step(state, plan, Event.RIGHT)
        state = step(state, plan, Event.ENTER)
    assert state.stage == "panels"
    assigned = [b.controller_id for b in state.boards.values()]
    # Six boards claim six of the seven probed controllers.
    assert len(assigned) == len(plan.units) == 6
    assert len(set(assigned)) == 6 and set(assigned) <= set(CONTROLLERS)

    # Map every panel; toggle density and winding on the first one.
    state = step(state, plan, Event.UP)
    state = step(state, plan, Event.DOWN)
    first_unit = plan.units[state.board_cursor]
    state = step(state, plan, Event.ENTER)
    rec = next(iter(state.boards[first_unit].channels.values()))
    assert rec.density == 360 and rec.winding == "cw"
    while state.stage != "done":
        state = step(state, plan, Event.ENTER)
    for unit in plan.units:
        assert len(state.boards[unit].channels) == len(plan.panels[unit])
    # Channels are unique per board.
    for board in state.boards.values():
        assert len(set(board.channels)) == len(board.channels)


def test_resume_lands_mid_sequence(plan):
    state = initial_state(plan, CONTROLLERS)
    for _ in range(3):
        state = step(state, plan, Event.ENTER)
    resumed = resume_state(plan, CONTROLLERS, dict(state.boards))
    assert resumed.stage == "ports"
    assert resumed.board_cursor == 3
    # Fully assigned boards resume into the panels stage.
    while state.stage == "ports":
        state = step(state, plan, Event.ENTER)
    resumed = resume_state(plan, CONTROLLERS, dict(state.boards))
    assert resumed.stage == "panels"
    assert resumed.board_cursor == 0 and resumed.panel_cursor == 0


def test_session_renders_both_streams(plan, net_lights):
    state = initial_state(plan, CONTROLLERS)
    core = SessionCore(plan, net_lights, state)
    got = {"wire": 0, "window": 0}
    core.window_sinks.append(
        lambda f: got.__setitem__("window", got["window"] + len(f))
    )
    core.wire_sinks.append(lambda f: got.__setitem__("wire", got["wire"] + len(f)))
    core.tick(0.4)
    assert got["window"] >= 1 and got["wire"] >= 1

    # Window pattern output is finite, in wire gamut, and stateless.
    pattern = core.window_engine.pattern
    a = pattern.render(net_lights.array, 4.2)
    b = pattern.render(net_lights.array, 4.2)
    assert np.array_equal(a, b)
    assert np.isfinite(a).all()
    assert a[:, 0].min() >= 0.0 and a[:, 0].max() <= 0.9
    assert a[:, 1].max() <= 0.34 + 1e-9

    # Advancing state rebuilds engines (fresh SESSION for consumers).
    before = core.wire_engine
    core.apply(Event.ENTER)
    assert core.wire_engine is not before


def test_wire_hypothesis_matches_records(plan, net_lights):
    state = initial_state(plan, CONTROLLERS)
    core = SessionCore(plan, net_lights, state)
    while core.state.stage == "ports":
        core.apply(Event.ENTER)
    core.apply(Event.UP)  # 360 density for the first panel
    core.apply(Event.ENTER)
    lights = core.wire_engine.lights
    first_unit = plan.units[0]
    cid = core.state.boards[first_unit].controller_id
    ch = next(iter(core.state.boards[first_unit].channels))
    rows = (
        (lights.ints(LightColumns.CONTROLLER) == cid)
        & (lights.ints(LightColumns.CHANNEL) == ch)
    ).sum()
    assert rows == 360


def test_wire_covers_every_controller_in_every_stage(plan, net_lights):
    """All probed controllers stay on the wire — the beads backdrop goes
    down the wire pre-mapping, and moving the selection cleans up the
    previously-selected board instead of stranding its last color."""
    core = SessionCore(plan, net_lights, initial_state(plan, CONTROLLERS))

    def wire_cids():
        return set(core.wire_engine.lights.ints(LightColumns.CONTROLLER))

    assert wire_cids() == set(CONTROLLERS)  # spare controller included
    first_candidate = core.state.candidate_controller
    core.apply(Event.RIGHT)  # deselect: old candidate falls back to beads
    assert wire_cids() == set(CONTROLLERS)
    cand_rows = core.wire_engine.lights.ints(LightColumns.CONTROLLER) == (
        first_candidate
    )
    assert set(core._wire_roles[cand_rows]) == {R.BEADS}
    while core.state.stage == "ports":
        core.apply(Event.ENTER)
    assert wire_cids() == set(CONTROLLERS)
    # Locked-but-waiting boards hold their steady color, not breathing.
    later_cid = core.state.boards[plan.units[-1]].controller_id
    later = core.wire_engine.lights.ints(LightColumns.CONTROLLER) == later_cid
    assert set(core._wire_roles[later]) == {R.SOLID}


def test_active_board_wire_details(plan, net_lights):
    """The strip under test plays the wheel on its first and last index
    quarters with a dark middle (density mismatches read as one half
    lit); every other unmapped strip previews its first 30 LEDs."""
    core = SessionCore(plan, net_lights, initial_state(plan, CONTROLLERS))
    while core.state.stage == "ports":
        core.apply(Event.ENTER)
    st = core.state
    lights = core.wire_engine.lights
    roles = core._wire_roles
    cid = st.boards[plan.units[st.board_cursor]].controller_id
    onboard = lights.ints(LightColumns.CONTROLLER) == cid
    chans = lights.ints(LightColumns.CHANNEL)
    cand = onboard & (chans == st.candidate_channel)
    n = int(cand.sum())
    assert n == st.candidate_density == 180
    assert (roles[cand] == R.WHEEL_FULL).sum() == 2 * (n // 4)
    assert (roles[cand] == R.OFF).sum() == n - 2 * (n // 4)
    preview_channels = [
        ch
        for ch in range(8)
        if ch != st.candidate_channel
        and (roles[onboard & (chans == ch)] == R.WHEEL_DIM).any()
    ]
    # Six panels on board 1: five wait behind the cursor panel.
    assert len(preview_channels) == 5
    for ch in preview_channels:
        m = onboard & (chans == ch)
        assert (roles[m] == R.WHEEL_DIM).sum() == 30
        assert (roles[m] == R.BEADS).sum() == int(m.sum()) - 30


def test_completed_board_rings_on_both_surfaces(plan, net_lights):
    core = SessionCore(plan, net_lights, initial_state(plan, CONTROLLERS))
    while core.state.stage == "ports":
        core.apply(Event.ENTER)
    for _ in plan.panels[plan.units[0]]:
        core.apply(Event.ENTER)
    assert (core._wire_roles == R.RING).sum() > 0
    ring = core._wire_roles == R.RING
    pattern = core.wire_engine.pattern
    peak = max(
        float(pattern.render(None, t)[ring, 0].max()) for t in np.arange(0, 7.0, 0.5)
    )
    assert peak > 0.4  # the ring visibly broadcasts on the wire
    assert (core._window_roles() == R.RING).sum() > 0


def test_finale_waves_black_then_spiral_wipe(plan, net_lights):
    """Completion: three quick waves over the still-running beads (the
    last wave clears them out behind its front), a beat of black, then
    the spiral show wipes in through phi with a soft border — anchored
    to the completion moment identically on both surfaces."""
    core = SessionCore(plan, net_lights, initial_state(plan, CONTROLLERS))
    core.tick(50.0)  # establish the session clock before finishing
    while core.state.stage != "done":
        core.apply(Event.ENTER)
    pat = core.window_engine.pattern
    assert isinstance(pat, R.FinalePattern)
    assert isinstance(core.wire_engine.pattern, R.FinalePattern)
    assert pat._t0 == core.wire_engine.pattern._t0 == 50.0
    assert pat._show.name == "spiral"

    phi = net_lights.array[:, LightColumns.PHI_S]
    t0 = 50.0
    waves_end = R.FINALE_WAVES * R.FINALE_WAVE_PERIOD

    # Mid-first-wave: a bright crest somewhere.
    a = pat.render(net_lights.array, t0 + 0.9)
    assert a[:, 0].max() > 0.4
    # Last wave, half descended: swept-past lights are beadless black.
    b = pat.render(net_lights.array, t0 + (R.FINALE_WAVES - 0.5) * R.FINALE_WAVE_PERIOD)
    behind = phi < 0.5 * np.radians(130.0) - np.radians(20.0)
    assert behind.any() and b[behind, 0].max() < 0.01
    # The black beat.
    c = pat.render(net_lights.array, t0 + waves_end + 0.5 * R.FINALE_BLACK)
    assert c.max() == 0.0
    # Mid-wipe, probed exactly: place the reveal edge at mid-phi — all
    # lights above it are fully revealed, all lights past its soft
    # border are still exactly black.
    wipe_start = t0 + waves_end + R.FINALE_BLACK
    soft = R._WIPE_SOFT
    span = pat._phi_hi - pat._phi_lo + 2 * soft
    mid = 0.5 * (pat._phi_lo + pat._phi_hi)
    frac = (mid - (pat._phi_lo - soft)) / span
    d = pat.render(net_lights.array, wipe_start + frac * R.FINALE_WIPE)
    below = phi > mid + soft + 1e-9  # past the soft border: masked
    above = phi < mid  # at or above the edge: fully revealed
    assert below.any() and d[below, 0].max() == 0.0
    assert above.any() and d[above, 0].max() > 0.1
    # After the wipe the show plays unmasked.
    late = wipe_start + R.FINALE_WIPE + 5.0
    e = pat.render(net_lights.array, late)
    assert np.allclose(e, np.nan_to_num(pat._show.render(net_lights.array, late)))


def test_ring_waves_rotate_and_wheel_has_three_spokes():
    # A ring of lights about an anchor at radius 30, plus a phi ramp.
    n = 360
    ang = 2 * np.pi * np.arange(n) / n
    xy = 30.0 * np.stack([np.cos(ang), np.sin(ang)], axis=1)
    edges = np.array([[0.0, 0.0, 50.0, 0.0]])
    phi = np.linspace(0.0, np.radians(130.0), n)
    ident = np.arange(n)

    def pattern(roles):
        return R.MappingPattern(
            roles=roles,
            ref=ident,
            net_xy=xy,
            edges=edges,
            net_anchor=np.zeros((n, 2)),
            net_hue=np.zeros(n),
            net_phi=phi,
        )

    out = pattern(np.full(n, R.WHEEL_FULL)).render(None, 1.234)
    # Hue is the plain angle about the anchor: continuous, position-only.
    assert np.allclose(out[:, 2], np.degrees(ang) % 360.0, atol=1.5)
    # Three dark spokes: the intensity field repeats every 120 degrees.
    assert np.allclose(out[:, 0], np.roll(out[:, 0], n // 3), atol=1e-9)
    assert out[:, 0].min() < 0.2 < 0.55 < out[:, 0].max()

    ring = pattern(np.full(n, R.RING))
    a = ring.render(None, 2.0)
    b = ring.render(None, 2.0 + 7.0)  # same descent phase, next wave
    lit = (a[:, 1] > 0.2) & (b[:, 1] > 0.2)
    assert lit.any()
    spin = (b[lit, 2] - a[lit, 2]) % 360.0
    # Every lit light rotated by the same seeded, nonzero angle.
    assert spin.std() < 1e-6 and 1.0 < spin.mean() < 359.0


def test_beads_are_short_lived():
    """A strut's bead lives about two seconds, then the strut goes dark
    until its lane's next cycle — beads are events, not permanent
    traffic."""
    edges = np.array([[0.0, 0.0, 50.0, 0.0]])
    xy = np.stack([np.linspace(0.0, 50.0, 40), np.zeros(40)], axis=1)
    field = R.BeadField(xy, edges)
    times = np.arange(0.0, 60.0, 0.05)
    lit = np.array([field(t).max() > 0.02 for t in times])
    # Two lanes, each alive <= ~2s per cycle and gated: well under half
    # the time lit overall; a typical stretch is one bead's ~2s life,
    # and even two overlapping lanes can't exceed twice that.
    assert 0.02 < lit.mean() < 0.55
    runs = np.diff(np.flatnonzero(np.diff(np.concatenate([[0], lit, [0]]))))[::2]
    assert np.median(runs) * 0.05 <= R._BEAD_LIFE + 0.2
    assert runs.max() * 0.05 <= 2 * R._BEAD_LIFE + 0.5


def test_wire_broadcasts_identically_to_window(plan, net_lights):
    """The parity contract, end to end: every wire light renders exactly
    the window's value at its reference net light whenever the two
    surfaces assign it the same role — and in the finale, where there
    are no roles, the gathered equality holds for every light at every
    phase."""
    core = SessionCore(plan, net_lights, initial_state(plan, CONTROLLERS))

    def check_matched(t):
        wp, ep = core.window_engine.pattern, core.wire_engine.pattern
        wo = wp.render(net_lights.array, t)
        eo = ep.render(core.wire_engine.lights.array, t)
        ref = core._wire_ref
        match = wp._roles[ref] == ep._roles
        assert match.any()
        assert np.array_equal(eo[match], wo[ref][match])
        return match

    check_matched(3.7)  # ports stage
    core.apply(Event.RIGHT)
    check_matched(4.1)  # after a deselection
    while core.state.stage == "ports":
        core.apply(Event.ENTER)
    match = check_matched(7.9)  # panels stage: solids, wheel, previews
    # The active strip's index-based roles are the only place window and
    # wire roles may differ (quarters and slivers land on different
    # lights); everything else matches.
    assert match.mean() > 0.8

    core.tick(30.0)
    while core.state.stage != "done":
        core.apply(Event.ENTER)
    wp, ep = core.window_engine.pattern, core.wire_engine.pattern
    for t in (30.9, 30.0 + 2.5 * R.FINALE_WAVE_PERIOD, 30.0 + 6.2, 90.0):
        wo = wp.render(net_lights.array, t)
        eo = ep.render(core.wire_engine.lights.array, t)
        assert np.array_equal(eo, wo[core._wire_ref])


def test_serpentine_path_and_refs(plan, net_lights):
    """The strip hypothesis follows the physical serpentine: it starts
    AND ends at the six-red corner (the path returns), reaches the far
    edge mid-strip, and its references cover the panel's capture lights;
    cw is the reversed traversal. The wheel anchors at the board vertex,
    so the aux panels continue board 2's wheel about vertex 9."""
    core = SessionCore(plan, net_lights, initial_state(plan, CONTROLLERS))
    p = plan.panels[plan.units[0]][0]
    xy = core._strip_path_xy(p, 180, "ccw")
    corner = np.asarray(p.corner_xy)
    d_corner = np.linalg.norm(xy - corner, axis=1)
    assert d_corner[0] < 5.0 and d_corner[-1] < 5.0  # returns to start
    assert d_corner.max() > 40.0  # reaches the far edge
    mid = np.argmax(d_corner)
    assert 0.25 * 180 < mid < 0.75 * 180
    # cw is the same path walked the other way.
    cw = core._strip_path_xy(p, 180, "cw")
    assert np.allclose(cw, xy[::-1])
    refs = core.strip_refs(p, 180, "ccw")
    panel_lights = set(np.flatnonzero(core._net_tri == p.tri_index))
    assert set(refs) <= panel_lights
    # Native density: an exact bijection onto the panel's lights (no
    # dark skipped-light holes in the mockup); double density covers
    # every light exactly twice.
    assert len(refs) == 180 and set(refs) == panel_lights
    refs360 = core.strip_refs(p, 360, "ccw")
    assert set(refs360) == panel_lights
    assert np.array_equal(core.strip_refs(p, 180, "cw"), refs[::-1])

    # Aux panels: anchored at their board's vertex, not their corner.
    aux = plan.by_face[(3, 4, 8)]
    m = core._net_tri == aux.tri_index
    anchor = core._net_anchor[m][0]
    own = plan.panels[9][0]  # a native panel of board 2 (unit 9)
    native = core._net_anchor[core._net_tri == own.tri_index][0]
    assert np.allclose(anchor, native)  # same wheel center: vertex 9
    assert not np.allclose(anchor, np.asarray(aux.corner_xy))

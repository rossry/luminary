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
    window = core._window_roles()
    assert (window["roles"] == R.RING).sum() > 0


def test_ring_waves_rotate_and_wheel_has_three_spokes():
    # A ring of lights about a corner at radius 30, plus a phi ramp.
    n = 360
    ang = 2 * np.pi * np.arange(n) / n
    xy = 30.0 * np.stack([np.cos(ang), np.sin(ang)], axis=1)
    edges = np.array([[0.0, 0.0, 50.0, 0.0]])
    phi = np.linspace(0.0, np.radians(130.0), n)

    wheel = R.MappingPattern(
        xy=xy,
        roles=np.full(n, R.WHEEL_FULL),
        edges=edges,
        corner_xy=np.zeros((n, 2)),
    )
    out = wheel.render(None, 1.234)
    # Hue is the plain angle about the corner: continuous, position-only.
    assert np.allclose(out[:, 2], np.degrees(ang) % 360.0, atol=1.5)
    # Three dark spokes: the intensity field repeats every 120 degrees.
    assert np.allclose(out[:, 0], np.roll(out[:, 0], n // 3), atol=1e-9)
    assert out[:, 0].min() < 0.2 < 0.55 < out[:, 0].max()

    ring = R.MappingPattern(
        xy=xy,
        roles=np.full(n, R.RING),
        edges=edges,
        phi_s=phi,
    )
    a = ring.render(None, 2.0)
    b = ring.render(None, 2.0 + 7.0)  # same descent phase, next wave
    lit = (a[:, 1] > 0.2) & (b[:, 1] > 0.2)
    assert lit.any()
    spin = (b[lit, 2] - a[lit, 2]) % 360.0
    # Every lit light rotated by the same seeded, nonzero angle.
    assert spin.std() < 1e-6 and 1.0 < spin.mean() < 359.0

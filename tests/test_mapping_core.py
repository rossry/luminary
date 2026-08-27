"""Mapping core: plan derivation, the state machine, renderers, session."""

import numpy as np
import pytest

from luminary.geometry.lights import LightColumns
from luminary.geometry.net import Net
from luminary.geometry.pentagon import capture
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
def net_lights():
    from pathlib import Path

    configs = Path(__file__).resolve().parents[1] / "configs"
    return capture(Net.from_json_file(configs / "4A-37.json"))


def test_plan_derivation(plan):
    # Seven 8-channel data units cover all 37 panels, none overloaded.
    assert len(plan.units) == 7
    assert plan.n_panels == 37
    for unit, panels in plan.panels.items():
        assert 0 < len(panels) <= 8
        for p in panels:
            # The six-red corner is a vertex of the face itself.
            assert p.corner_vertex in p.face
    # The front data unit (vertex 8) serves exactly the three arc faces.
    assert len(plan.panels[8]) == 3


def test_state_machine_full_walk(plan):
    state = initial_state(plan, CONTROLLERS)
    assert state.stage == "ports"
    # Cycling never selects an assigned controller; enter assigns all.
    for _ in plan.units:
        state = step(state, plan, Event.RIGHT)
        state = step(state, plan, Event.ENTER)
    assert state.stage == "panels"
    assigned = [b.controller_id for b in state.boards.values()]
    assert sorted(assigned) == sorted(CONTROLLERS)

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

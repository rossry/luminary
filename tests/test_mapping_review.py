"""Re-walking a mapping that is already right, and density per strip.

Two behaviours an operator depends on at the installation:

* the default run starts at the beginning but pre-filled from the saved
  records, so confirming an unchanged mapping is enter-enter-enter rather
  than re-deciding every panel;
* ``up`` sets the density of the *strip* — board x channel — because that is
  what is physically plugged in, so it does not follow a panel that moves.
"""

from __future__ import annotations

import pytest

from luminary.mapping.plan import Plan
from luminary.mapping.state import (
    BoardRecord,
    ChannelRecord,
    Event,
    initial_state,
    resume_state,
    step,
)


@pytest.fixture(scope="module")
def plan():
    return Plan.load("4A-33")


def _complete(plan, density=180):
    return {
        unit: BoardRecord(
            unit_vertex=unit,
            controller_id=controller,
            channels={
                ch: ChannelRecord(face=p.face, winding="ccw", density=density)
                for ch, p in enumerate(plan.panels[unit])
            },
        )
        for controller, unit in enumerate(plan.units)
    }


def _enter_through(state, plan, limit=200):
    """Press enter until the sequence ends; -> (final state, presses)."""
    presses = 0
    while state.stage != "done" and presses < limit:
        state = step(state, plan, Event.ENTER)
        presses += 1
    return state, presses


def test_default_starts_at_the_beginning_not_at_the_first_gap(plan):
    records = _complete(plan)

    state = initial_state(plan, list(range(len(plan.units))), records)

    assert state.stage == "ports"
    assert state.board_cursor == 0
    # Pre-filled: the first enter re-confirms what was saved.
    assert state.candidate_controller == records[plan.units[0]].controller_id


def test_a_correct_mapping_is_all_enters_and_unchanged(plan):
    records = _complete(plan)
    state = initial_state(plan, list(range(len(plan.units))), records)

    final, presses = _enter_through(state, plan)

    assert final.stage == "done"
    # One enter per board (ports) plus one per panel (panels).
    assert presses == len(plan.units) + plan.n_panels
    for unit, saved in records.items():
        assert final.boards[unit].controller_id == saved.controller_id
        assert {
            ch: (r.face, r.winding, r.density)
            for ch, r in final.boards[unit].channels.items()
        } == {ch: (r.face, r.winding, r.density) for ch, r in saved.channels.items()}


def test_continue_still_skips_to_the_first_unrecorded_slot(plan):
    """--continue keeps its old meaning."""
    records = _complete(plan)
    unit = plan.units[-1]
    channels = dict(records[unit].channels)
    channels.pop(max(channels))
    records[unit] = BoardRecord(unit, records[unit].controller_id, channels)

    state = resume_state(plan, list(range(len(plan.units))), records)

    assert state.stage == "panels"
    assert plan.units[state.board_cursor] == unit
    assert not state.review


def test_empty_records_still_walk_from_the_start(plan):
    state = initial_state(plan, list(range(len(plan.units))))

    assert state.stage == "ports"
    assert state.board_cursor == 0


# ------------------------------------------------------------------- density


def _at_first_panel(plan, records=None):
    state = initial_state(plan, list(range(len(plan.units))), records)
    for _ in range(len(plan.units)):  # clear the ports stage
        state = step(state, plan, Event.ENTER)
    assert state.stage == "panels"
    return state


def test_up_sets_the_density_of_the_selected_strip(plan):
    state = _at_first_panel(plan)
    channel = state.candidate_channel

    state = step(state, plan, Event.UP)

    unit = plan.units[state.board_cursor]
    assert state.candidate_density == 360
    assert state.boards[unit].densities[channel] == 360


def test_density_follows_the_channel_not_the_panel(plan):
    """Select another channel and the density shown is that strip's."""
    state = _at_first_panel(plan)
    first = state.candidate_channel
    state = step(state, plan, Event.UP)  # this strip is 360
    assert state.candidate_density == 360

    state = step(state, plan, Event.RIGHT)  # a different strip
    assert state.candidate_channel != first
    assert state.candidate_density == 180

    state = step(state, plan, Event.LEFT)  # back to the first strip
    assert state.candidate_channel == first
    assert state.candidate_density == 360


def test_a_moved_panel_leaves_its_density_behind_on_the_old_strip(plan):
    """The strip keeps its density; the panel does not carry it away."""
    state = _at_first_panel(plan)
    original = state.candidate_channel
    state = step(state, plan, Event.UP)  # strip `original` is 360
    state = step(state, plan, Event.RIGHT)  # move the panel elsewhere
    moved_to = state.candidate_channel
    state = step(state, plan, Event.ENTER)  # record it there

    unit = plan.units[state.board_cursor if state.stage == "panels" else 0]
    boards = state.boards[plan.units[0]]
    assert boards.densities[original] == 360, "the strip kept its density"
    assert boards.channels[moved_to].density == 180, "the panel took 180 with it"
    assert original not in boards.channels, "no stale copy on the old channel"


def test_recorded_density_is_offered_again_on_review(plan):
    records = _complete(plan, density=360)

    state = _at_first_panel(plan, records)

    assert state.candidate_density == 360

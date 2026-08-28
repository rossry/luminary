"""Mapping records -> deployed geometry (spec §7.3.1, closes §19.6).

The design capture puts every light on controller 0; these assert that the
recorded wiring is what decides identity, and that a mapping which cannot
drive an installation is refused rather than silently producing a geometry
with holes in it.
"""

from __future__ import annotations

import numpy as np
import pytest

from luminary.geometry.lights import LightColumns
from luminary.geometry.net import Net
from luminary.geometry.pentagon.adapters import capture
from luminary.geometry.pentagon.mapped import (
    MappingIncompleteError,
    capture_mapped,
)
from luminary.mapping.plan import Plan
from luminary.mapping.state import BoardRecord, ChannelRecord
from luminary.statedir import runtime_state_dir

CONFIG = "4A-33"


@pytest.fixture(scope="module")
def plan():
    return Plan.load(CONFIG)


@pytest.fixture(scope="module")
def net():
    from pathlib import Path

    configs = Path(__file__).resolve().parents[1] / "configs"
    return Net.from_json_file(configs / f"{CONFIG}.json")


@pytest.fixture(scope="module")
def net_lights(net):
    return capture(net)


def _full_mapping(plan, density=180, winding="ccw"):
    """Every unit locked to a controller, every panel on its own channel."""
    boards = {}
    for controller, unit in enumerate(plan.units):
        channels = {
            channel: ChannelRecord(face=panel.face, winding=winding, density=density)
            for channel, panel in enumerate(plan.panels[unit])
        }
        boards[unit] = BoardRecord(
            unit_vertex=unit, controller_id=controller, channels=channels
        )
    return boards


def test_a_full_mapping_spans_every_board(plan, net, net_lights):
    boards = _full_mapping(plan)

    lights = capture_mapped(net, plan, boards, net_lights=net_lights)

    assert lights.controllers == list(range(len(plan.units)))
    # One light per beam per panel, and no beam lost or duplicated overall.
    assert lights.n == net_lights.n
    per_board = {
        controller: len(lights.active_rows_for_controller(controller))
        for controller in lights.controllers
    }
    for controller, unit in enumerate(plan.units):
        assert per_board[controller] == 180 * len(plan.panels[unit])


def test_each_panel_lands_on_its_own_channel(plan, net, net_lights):
    boards = _full_mapping(plan)

    lights = capture_mapped(net, plan, boards, net_lights=net_lights)

    controllers = lights.ints(LightColumns.CONTROLLER)
    channels = lights.ints(LightColumns.CHANNEL)
    indices = lights.ints(LightColumns.INDEX)
    for controller, unit in enumerate(plan.units):
        rows = controllers == controller
        assert sorted(set(channels[rows])) == list(range(len(plan.panels[unit])))
        for channel in set(channels[rows]):
            strip = np.sort(indices[rows & (channels == channel)])
            # Indices run 0..n-1 with no gaps: the firmware addresses a strip
            # by position, so a hole would silently shift every later LED.
            assert strip.tolist() == list(range(strip.size))


def test_double_density_doubles_that_strip_only(plan, net, net_lights):
    boards = _full_mapping(plan)
    unit = plan.units[0]
    channels = dict(boards[unit].channels)
    channels[0] = ChannelRecord(face=channels[0].face, winding="ccw", density=360)
    boards[unit] = BoardRecord(unit, boards[unit].controller_id, channels)

    lights = capture_mapped(net, plan, boards, net_lights=net_lights)

    assert lights.n == net_lights.n + 180
    controllers = lights.ints(LightColumns.CONTROLLER)
    chans = lights.ints(LightColumns.CHANNEL)
    assert int(((controllers == 0) & (chans == 0)).sum()) == 360
    assert int(((controllers == 0) & (chans == 1)).sum()) == 180


def test_winding_reverses_the_strip(plan, net, net_lights):
    ccw = capture_mapped(net, plan, _full_mapping(plan), net_lights=net_lights)
    cw = capture_mapped(
        net, plan, _full_mapping(plan, winding="cw"), net_lights=net_lights
    )

    def strip(lights):
        rows = (lights.ints(LightColumns.CONTROLLER) == 0) & (
            lights.ints(LightColumns.CHANNEL) == 0
        )
        order = np.argsort(lights.ints(LightColumns.INDEX)[rows])
        return lights.array[rows][order][:, LightColumns.X]

    assert np.allclose(strip(ccw), strip(cw)[::-1])


def test_an_unlocked_board_is_refused(plan, net, net_lights):
    boards = _full_mapping(plan)
    unit = plan.units[0]
    boards[unit] = BoardRecord(unit, None, boards[unit].channels)

    with pytest.raises(MappingIncompleteError, match="no controller locked"):
        capture_mapped(net, plan, boards, net_lights=net_lights)


def test_a_half_mapped_board_is_refused(plan, net, net_lights):
    boards = _full_mapping(plan)
    unit = plan.units[0]
    channels = dict(boards[unit].channels)
    channels.pop(max(channels))
    boards[unit] = BoardRecord(unit, boards[unit].controller_id, channels)

    with pytest.raises(MappingIncompleteError, match="panels mapped"):
        capture_mapped(net, plan, boards, net_lights=net_lights)


def test_partial_builds_what_is_mapped(plan, net, net_lights):
    """Mid-commissioning: drive what exists, leave the rest dark."""
    boards = _full_mapping(plan)
    for unit in plan.units[3:]:
        boards[unit] = BoardRecord(unit, None, {})

    lights = capture_mapped(net, plan, boards, net_lights=net_lights, strict=False)

    assert lights.controllers == [0, 1, 2]
    assert lights.n < net_lights.n


def test_two_boards_on_one_controller_are_refused(plan, net, net_lights):
    boards = _full_mapping(plan)
    unit = plan.units[1]
    boards[unit] = BoardRecord(unit, 0, boards[unit].channels)

    with pytest.raises(MappingIncompleteError, match="claimed by units"):
        capture_mapped(net, plan, boards, net_lights=net_lights)


def test_every_board_fits_the_firmware_light_ceiling(plan, net, net_lights):
    """MAX_ACTIVE_LIGHTS is 4096; above it a board refuses the SESSION."""
    boards = _full_mapping(plan, density=360)

    lights = capture_mapped(net, plan, boards, net_lights=net_lights)

    for controller in lights.controllers:
        assert len(lights.active_rows_for_controller(controller)) <= 4096


def test_each_board_is_one_contiguous_block_sliceable_by_channel(plan, net, net_lights):
    """No dict lookup or reordering on the frame path.

    Canonical order is (controller, channel, index), so a board's lights are a
    single contiguous run, ascending by channel, each channel's indices 0..n-1
    in order. The SESSION handshake declares those per-channel lengths, so the
    board can hold one flat buffer, apply keyframe/dead-reckoning across it,
    and slice it into channels by offset alone.
    """
    lights = capture_mapped(net, plan, _full_mapping(plan), net_lights=net_lights)

    for controller in lights.controllers:
        rows = lights.active_rows_for_controller(controller)
        assert np.all(np.diff(rows) == 1), "board's lights are not one block"

        channels = lights.ints(LightColumns.CHANNEL)[rows]
        assert np.all(np.diff(channels) >= 0), "channels are not in order"

        indices = lights.ints(LightColumns.INDEX)[rows]
        offset = 0
        for channel, strip in sorted(lights.channel_strips(controller).items()):
            length = int(strip["length"])
            run = indices[offset : offset + length]
            assert np.array_equal(run, np.arange(length)), (
                f"controller {controller} channel {channel} is not a 0..n-1 run "
                "at its declared offset"
            )
            assert np.all(channels[offset : offset + length] == channel)
            offset += length
        assert offset == rows.size, "declared lengths do not cover the block"

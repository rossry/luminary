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


def _polygon_area(poly):
    pts = np.asarray(poly, dtype=float)
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))


def _strip_rows(lights, controller, channel):
    rows = np.flatnonzero(
        (lights.ints(LightColumns.CONTROLLER) == controller)
        & (lights.ints(LightColumns.CHANNEL) == channel)
    )
    return rows[np.argsort(lights.ints(LightColumns.INDEX)[rows])]


def _one_dense_strip(plan, density=360):
    boards = _full_mapping(plan)
    unit = plan.units[0]
    channels = dict(boards[unit].channels)
    channels[0] = ChannelRecord(face=channels[0].face, winding="ccw", density=density)
    boards[unit] = BoardRecord(unit, boards[unit].controller_id, channels)
    return boards


def test_double_density_subdivides_beams_into_distinct_lights(plan, net, net_lights):
    """Twice the beams, each lit by one LED — not two LEDs on one beam.

    Coincident lights would render identically forever, so distinct positions
    are the property that matters.
    """
    lights = capture_mapped(net, plan, _one_dense_strip(plan), net_lights=net_lights)
    rows = _strip_rows(lights, 0, 0)

    assert rows.size == 360
    xy = lights.array[np.ix_(rows, [LightColumns.X, LightColumns.Y])]
    assert len({tuple(np.round(p, 9)) for p in xy}) == 360


def test_subdivided_beams_halve_the_display_shape(plan, net, net_lights):
    """Each half-beam gets its own slice of the polygon, not a copy."""
    lights = capture_mapped(net, plan, _one_dense_strip(plan), net_lights=net_lights)

    halves = [_polygon_area(lights.display[r]) for r in _strip_rows(lights, 0, 0)]
    natives = [_polygon_area(lights.display[r]) for r in _strip_rows(lights, 0, 1)]

    assert np.mean(halves) == pytest.approx(np.mean(natives) / 2, rel=0.05)


def test_subdivided_lights_keep_a_folded_3d_position(plan, net, net_lights):
    """A half-beam's centre is a new point; its fold must be recomputed."""
    lights = capture_mapped(net, plan, _one_dense_strip(plan), net_lights=net_lights)
    rows = _strip_rows(lights, 0, 0)

    p3 = lights.array[np.ix_(rows, [LightColumns.X3, LightColumns.Y3, LightColumns.Z3])]
    assert np.isfinite(p3).all()
    assert len({tuple(np.round(p, 9)) for p in p3}) == 360


def test_native_density_still_inherits_the_whole_beam(plan, net, net_lights):
    """No subdivision when the strip maps one-for-one."""
    lights = capture_mapped(net, plan, _full_mapping(plan), net_lights=net_lights)
    rows = _strip_rows(lights, 0, 0)

    source = {
        tuple(np.round(np.asarray(d, dtype=float).ravel(), 9))
        for d in net_lights.display
        if d
    }
    for row in rows:
        shape = tuple(np.round(np.asarray(lights.display[row], dtype=float).ravel(), 9))
        assert shape in source


def test_interpolate_dense_halves_the_wire_cost_of_dense_strips(plan, net, net_lights):
    """A 360-LED strip costs 180 lights on the wire; the board fills in."""
    boards = _one_dense_strip(plan)

    plain = capture_mapped(net, plan, boards, net_lights=net_lights)
    lean = capture_mapped(
        net, plan, boards, net_lights=net_lights, interpolate_dense=True
    )

    assert lean.n == plain.n, "the same physical LEDs either way"
    plain_active = len(plain.active_rows_for_controller(0))
    lean_active = len(lean.active_rows_for_controller(0))
    # 360 -> 181 ACTIVE on that strip (the last light stays ACTIVE so every
    # interpolated one is bounded); the other five strips are untouched.
    assert plain_active - lean_active == 179


def test_native_strips_are_untouched_by_interpolate_dense(plan, net, net_lights):
    """There is nothing to subdivide at native density, so nothing changes."""
    boards = _full_mapping(plan)

    plain = capture_mapped(net, plan, boards, net_lights=net_lights)
    lean = capture_mapped(
        net, plan, boards, net_lights=net_lights, interpolate_dense=True
    )

    for controller in plain.controllers:
        assert len(lean.active_rows_for_controller(controller)) == len(
            plain.active_rows_for_controller(controller)
        )


def test_interpolated_strips_still_load_and_validate(plan, net, net_lights, tmp_path):
    """Every INTERPOLATED light needs ACTIVE neighbours on both sides —
    the geometry loader enforces it, so a round trip is the check."""
    lights = capture_mapped(
        net,
        plan,
        _one_dense_strip(plan),
        net_lights=net_lights,
        interpolate_dense=True,
    )
    path = tmp_path / "interp.lights.json"
    lights.save(path)

    from luminary.geometry.lights import LightsGeometry as LG

    reloaded = LG.load(path)
    assert reloaded.n == lights.n
    # Weights were derived for the interpolated lights.
    interp = (
        reloaded.array[:, LightColumns.KIND]
        != reloaded.array[reloaded.control_mask][0, LightColumns.KIND]
    )
    assert interp.sum() > 0


def test_an_absent_board_contributes_no_lights(plan, net, net_lights):
    """Pressing x during mapping means "not here": the geometry builds
    without it rather than refusing, and its lights simply do not exist."""
    boards = _full_mapping(plan)
    missing = plan.units[0]
    boards[missing] = BoardRecord(
        unit_vertex=missing, controller_id=None, channels={}, absent=True
    )

    lights = capture_mapped(net, plan, boards, net_lights=net_lights)

    assert lights.controllers == [1, 2, 3, 4, 5]
    assert lights.n == net_lights.n - 180 * len(plan.panels[missing])


def test_an_absent_panel_contributes_no_lights(plan, net, net_lights):
    boards = _full_mapping(plan)
    unit = plan.units[0]
    gone = plan.panels[unit][0].face
    channels = {
        ch: rec for ch, rec in boards[unit].channels.items() if rec.face != gone
    }
    boards[unit] = BoardRecord(
        unit_vertex=unit,
        controller_id=boards[unit].controller_id,
        channels=channels,
        absent_faces=(gone,),
    )

    lights = capture_mapped(net, plan, boards, net_lights=net_lights)

    assert lights.n == net_lights.n - 180
    assert 0 in lights.controllers, "the rest of the board still drives"


def test_a_gap_that_was_never_decided_is_still_refused(plan, net, net_lights):
    """Absent is a decision; unmapped is not. Only the former builds."""
    boards = _full_mapping(plan)
    unit = plan.units[0]
    channels = dict(boards[unit].channels)
    channels.pop(max(channels))
    boards[unit] = BoardRecord(unit, boards[unit].controller_id, channels)

    with pytest.raises(MappingIncompleteError, match="panels mapped"):
        capture_mapped(net, plan, boards, net_lights=net_lights)

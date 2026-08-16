"""Lights geometry (spec §6): schema, sorting, weights, validation, IO."""

import numpy as np
import pytest

from luminary.geometry.lights import (
    Kind,
    LightColumns,
    LightsGeometry,
    LightsGeometryError,
    LightSpec,
    SpaceSpec,
)


def _spec(controller=0, channel=0, index=0, kind="active", pos=(0.0, 0.0), **kw):
    return LightSpec(
        controller=controller,
        channel=channel,
        index=index,
        kind=kind,
        pos=list(pos),
        **kw,
    )


def test_sorting_and_columns():
    specs = [
        _spec(channel=1, index=0, pos=(1, 0)),
        _spec(channel=0, index=1, pos=(2, 0)),
        _spec(channel=0, index=0, pos=(3, 4)),
    ]
    lg = LightsGeometry.from_specs(specs, SpaceSpec())
    channels = lg.ints(LightColumns.CHANNEL).tolist()
    indices = lg.ints(LightColumns.INDEX).tolist()
    assert channels == [0, 0, 1] and indices == [0, 1, 0]  # canonical sort §6.4
    assert lg.array[0, LightColumns.R] == pytest.approx(5.0)
    assert lg.array[0, LightColumns.Z3] == 0.0


def test_duplicate_identity_rejected():
    specs = [_spec(index=0), _spec(index=0, pos=(1, 1))]
    with pytest.raises(LightsGeometryError, match="Duplicate light identity"):
        LightsGeometry.from_specs(specs, SpaceSpec())


def test_interpolation_weights_by_arc_length():
    # Uneven spacing: interp light closer to its left neighbor.
    specs = [
        _spec(index=0, pos=(0, 0)),
        _spec(index=1, kind="interpolated", pos=(1, 0)),
        _spec(index=2, pos=(10, 0)),
    ]
    lg = LightsGeometry.from_specs(specs, SpaceSpec())
    w = lg.array[1, LightColumns.WEIGHT]
    assert w == pytest.approx(0.1)


def test_interpolated_missing_pos_is_lerped():
    specs = [
        _spec(index=0, pos=(0, 0)),
        LightSpec(controller=0, channel=0, index=1, kind="interpolated"),
        _spec(index=2, pos=(10, 0)),
    ]
    lg = LightsGeometry.from_specs(specs, SpaceSpec())
    assert lg.array[1, LightColumns.X] == pytest.approx(5.0)
    assert lg.array[1, LightColumns.WEIGHT] == pytest.approx(0.5)


def test_interpolated_without_bounding_active_rejected():
    specs = [
        _spec(index=0, kind="interpolated", pos=(0, 0)),
        _spec(index=1, pos=(1, 0)),
    ]
    with pytest.raises(LightsGeometryError, match="bounding active"):
        LightsGeometry.from_specs(specs, SpaceSpec())


def test_active_without_pos_rejected():
    specs = [LightSpec(controller=0, channel=0, index=0, kind="active")]
    with pytest.raises(LightsGeometryError, match="no pos"):
        LightsGeometry.from_specs(specs, SpaceSpec())


def test_roundtrip_via_file_dict():
    specs = [
        _spec(index=0, pos=(0, 0), dir=[0, 1, 0], normal=[0, 1, 0]),
        _spec(index=1, kind="interpolated", pos=(5, 0)),
        _spec(
            index=2, pos=(10, 0), extent=[10, 20, 0], display=[[0, 0], [1, 0], [1, 1]]
        ),
        _spec(channel=3, index=0, kind="inactive", pos=(0, 5)),
    ]
    lg = LightsGeometry.from_specs(specs, SpaceSpec(), source={"type": "test"})
    lg2 = LightsGeometry.load(lg.to_file_dict())
    np.testing.assert_allclose(lg2.array, lg.array, equal_nan=True)
    assert lg2.display == lg.display
    assert lg2.source == {"type": "test"}


def test_channel_strips_fills_gaps_as_inactive():
    specs = [
        _spec(index=0, pos=(0, 0)),
        _spec(index=3, pos=(3, 0)),  # gap at 1, 2
    ]
    lg = LightsGeometry.from_specs(specs, SpaceSpec())
    strips = lg.channel_strips(0)
    assert int(strips[0]["length"]) == 4
    kinds = strips[0]["kinds"].tolist()
    assert kinds == [Kind.ACTIVE, Kind.INACTIVE, Kind.INACTIVE, Kind.ACTIVE]


def test_xyz_authoritative_requires_projection():
    doc = {
        "schema": "luminary.lights/1",
        "space": {"authoritative": ["xyz"]},
        "lights": [{"controller": 0, "channel": 0, "index": 0, "pos": [1, 2, 3]}],
    }
    with pytest.raises(LightsGeometryError, match="projection is required"):
        LightsGeometry.load(doc)
    doc["space"]["projection"] = "orthographic_xz"
    lg = LightsGeometry.load(doc)
    assert lg.array[0, LightColumns.X] == 1.0
    assert lg.array[0, LightColumns.Y] == 3.0  # xz projection

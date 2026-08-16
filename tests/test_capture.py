"""Scaffold model and from-scaffold capture (spec §5, §7.2)."""

import numpy as np
import pytest

from luminary.geometry.capture import CaptureParams, capture
from luminary.geometry.capture.from_scan import CameraSpec, ScanBundle
from luminary.geometry.lights import Kind, LightColumns
from luminary.geometry.scaffold import Scaffold, ScaffoldError

SQUARE = {
    "schema": "luminary.scaffold/1",
    "space": {"authoritative": ["xy"]},
    "lines": [
        {"id": "a", "p1": [0, 0], "p2": [100, 0], "tags": ["bottom"]},
        {"id": "b", "p1": [100, 0], "p2": [100, 100]},
        {"id": "c", "p1": [100, 100], "p2": [0, 100]},
        {"id": "d", "p1": [0, 100], "p2": [0, 0]},
    ],
    "meta": {"name": "square"},
}


def test_scaffold_defaults():
    s = Scaffold.load(SQUARE)
    assert s.n_lines == 4
    # Default midpoint is the chord midpoint.
    np.testing.assert_allclose(s.mid_xy[0], [50, 0])
    # Default normal: +90deg CCW of p1->p2 (spec §5.3.2). Line a runs +x,
    # so its normal is +y.
    np.testing.assert_allclose(s.normals[0, 0], [0, 1, 0], atol=1e-12)
    # Line b runs +y, normal -x.
    np.testing.assert_allclose(s.normals[1, 1], [-1, 0, 0], atol=1e-12)


def test_scaffold_rejects_degenerate_line():
    bad = dict(SQUARE, lines=[{"p1": [1, 1], "p2": [1, 1]}])
    with pytest.raises(ScaffoldError, match="coincident endpoints"):
        Scaffold.load(bad)


def test_scaffold_roundtrip(tmp_path):
    s = Scaffold.load(SQUARE)
    path = tmp_path / "square.scaffold.json"
    s.save(path)
    s2 = Scaffold.load(path)
    np.testing.assert_allclose(s2.p1_xy, s.p1_xy)
    np.testing.assert_allclose(s2.normals, s.normals)


def test_capture_deterministic_and_counted():
    s = Scaffold.load(SQUARE)
    params = CaptureParams(count_per_line=5)
    lg1 = capture(s, params)
    lg2 = capture(s, params)
    np.testing.assert_array_equal(lg1.array, lg2.array)
    assert lg1.n == 20
    assert np.all(lg1.control_mask)  # no interpolation policy -> all active


def test_capture_spacing():
    s = Scaffold.load(SQUARE)
    lg = capture(s, CaptureParams(spacing=25.0))
    # 100-unit lines at 25 spacing -> 5 lights per line.
    assert lg.n == 20


def test_capture_direction_is_line_normal_and_extent():
    s = Scaffold.load(SQUARE)
    lg = capture(s, CaptureParams(count_per_line=3, throw_distance=7.0, channels=4))
    row = 0  # channel 0 = line "a", first light at (0,0), normal +y
    np.testing.assert_allclose(
        lg.array[row, LightColumns.DX : LightColumns.DZ + 1], [0, 1, 0], atol=1e-12
    )
    np.testing.assert_allclose(
        lg.array[row, LightColumns.EX : LightColumns.EZ + 1],
        [0, 7, 0],
        atol=1e-12,
    )


def test_capture_channel_map_and_interpolation_policy():
    s = Scaffold.load(SQUARE)
    params = CaptureParams(
        count_per_line=7,
        channel_map={"bottom": 5, "c": 5},
        interpolate_every=3,
        channels=2,
    )
    lg = capture(s, params)
    channels = set(lg.ints(LightColumns.CHANNEL).tolist())
    assert 5 in channels  # explicit map honored (id and tag)
    kinds = lg.ints(LightColumns.KIND)
    channel_col = lg.ints(LightColumns.CHANNEL)
    for ch in sorted(set(channel_col.tolist())):
        strip_kinds = kinds[channel_col == ch]
        assert strip_kinds[0] == Kind.ACTIVE
        assert strip_kinds[-1] == Kind.ACTIVE  # endpoints forced active
        assert np.any(strip_kinds == Kind.INTERPOLATED)


def test_capture_bent_line_passes_through_midpoint():
    doc = dict(
        SQUARE,
        lines=[{"p1": [0, 0], "p2": [100, 0], "midpoint": [50, 20]}],
    )
    s = Scaffold.load(doc)
    lg = capture(s, CaptureParams(count_per_line=3))
    # Middle light sits exactly on the declared midpoint (spec §7.2.2).
    np.testing.assert_allclose(
        lg.array[1, [LightColumns.X, LightColumns.Y]], [50, 20], atol=1e-9
    )


def test_scan_capture_is_a_stub():
    s = Scaffold.load(SQUARE)
    bundle = ScanBundle(camera=CameraSpec(intrinsics=[1] * 9, pose=[1] * 16), frames=[])
    from luminary.geometry.capture import from_scan

    with pytest.raises(NotImplementedError, match="spec §7.4"):
        from_scan.capture(s, bundle)

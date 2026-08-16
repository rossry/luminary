"""Coordinate conversions (spec §4): round trips and derivation rules."""

import numpy as np
import pytest

from luminary.geometry import coords


def test_xy_polar_roundtrip():
    rng = np.random.default_rng(1)
    xy = rng.normal(size=(200, 2)) * 100
    back = coords.polar_to_xy(coords.xy_to_polar(xy))
    np.testing.assert_allclose(back, xy, atol=1e-9)


def test_xyz_spherical_roundtrip():
    rng = np.random.default_rng(2)
    xyz = rng.normal(size=(200, 3)) * 50
    back = coords.spherical_to_xyz(coords.xyz_to_spherical(xyz))
    np.testing.assert_allclose(back, xyz, atol=1e-9)


def test_spherical_origin_is_finite():
    sph = coords.xyz_to_spherical(np.zeros((1, 3)))
    assert np.all(np.isfinite(sph))


def test_projections():
    xyz = np.array([[1.0, 2.0, 3.0]])
    np.testing.assert_allclose(coords.project(xyz, "orthographic_xy"), [[1, 2]])
    np.testing.assert_allclose(coords.project(xyz, "orthographic_xz"), [[1, 3]])
    np.testing.assert_allclose(coords.project(xyz, "orthographic_yz"), [[2, 3]])
    with pytest.raises(ValueError, match="Unknown projection"):
        coords.project(xyz, "mercator")


def test_derive_all_planar():
    xy = np.array([[3.0, 4.0]])
    block = coords.derive_all(xy, None)
    assert block.shape == (1, 10)
    assert block[0, 2] == pytest.approx(5.0)  # r
    assert block[0, 6] == 0.0  # z3 defaults to 0 (spec §4.1.2)
    assert np.all(np.isfinite(block))


def test_derive_all_spatial_requires_projection():
    xyz = np.array([[1.0, 2.0, 3.0]])
    with pytest.raises(ValueError, match="projection is required"):
        coords.derive_all(None, xyz)
    block = coords.derive_all(None, xyz, "orthographic_xy")
    assert block[0, 0] == 1.0 and block[0, 1] == 2.0

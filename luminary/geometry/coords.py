"""Vectorized coordinate-system conversions (spec §4).

Four coordinate spaces (spec §4.1): XY projection, XYZ spatial, r-theta
polar (of XY), and rho/theta/phi spherical (of XYZ). A geometry file declares
which space is authoritative; everything else is derived here, in one place
(spec §4.3.1). All functions operate on (n, k) float arrays with no per-row
Python loops. Angles are radians in memory; degrees exist only at file
boundaries (spec §4.3.2).

Spherical convention: theta_s is the azimuth atan2(y, x); phi_s is the
inclination from the +Z axis (arccos(z / rho)).
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

import numpy as np


def xy_to_polar(xy: np.ndarray) -> np.ndarray:
    """(n,2) [x,y] -> (n,2) [r, theta]."""
    r = np.hypot(xy[:, 0], xy[:, 1])
    theta = np.arctan2(xy[:, 1], xy[:, 0])
    return np.stack([r, theta], axis=1)


def polar_to_xy(rtheta: np.ndarray) -> np.ndarray:
    """(n,2) [r, theta] -> (n,2) [x, y]."""
    x = rtheta[:, 0] * np.cos(rtheta[:, 1])
    y = rtheta[:, 0] * np.sin(rtheta[:, 1])
    return np.stack([x, y], axis=1)


def xyz_to_spherical(xyz: np.ndarray) -> np.ndarray:
    """(n,3) [x,y,z] -> (n,3) [rho, theta_s (azimuth), phi_s (inclination)]."""
    rho = np.sqrt(np.sum(xyz**2, axis=1))
    theta_s = np.arctan2(xyz[:, 1], xyz[:, 0])
    with np.errstate(invalid="ignore", divide="ignore"):
        cos_phi = np.where(rho > 0, xyz[:, 2] / np.where(rho > 0, rho, 1.0), 1.0)
    phi_s = np.arccos(np.clip(cos_phi, -1.0, 1.0))
    return np.stack([rho, theta_s, phi_s], axis=1)


def spherical_to_xyz(sph: np.ndarray) -> np.ndarray:
    """(n,3) [rho, theta_s, phi_s] -> (n,3) [x, y, z]."""
    rho, theta_s, phi_s = sph[:, 0], sph[:, 1], sph[:, 2]
    sin_phi = np.sin(phi_s)
    return np.stack(
        [
            rho * sin_phi * np.cos(theta_s),
            rho * sin_phi * np.sin(theta_s),
            rho * np.cos(phi_s),
        ],
        axis=1,
    )


def _project_orthographic_xy(xyz: np.ndarray) -> np.ndarray:
    out: np.ndarray = xyz[:, 0:2].copy()
    return out


def _project_orthographic_xz(xyz: np.ndarray) -> np.ndarray:
    out: np.ndarray = xyz[:, [0, 2]].copy()
    return out


def _project_orthographic_yz(xyz: np.ndarray) -> np.ndarray:
    out: np.ndarray = xyz[:, [1, 2]].copy()
    return out


def _project_spherical_equirect(xyz: np.ndarray) -> np.ndarray:
    sph = xyz_to_spherical(xyz)
    return np.stack([sph[:, 1], sph[:, 2]], axis=1)


PROJECTIONS: Dict[str, Callable[[np.ndarray], np.ndarray]] = {
    "orthographic_xy": _project_orthographic_xy,
    "orthographic_xz": _project_orthographic_xz,
    "orthographic_yz": _project_orthographic_yz,
    "spherical_equirect": _project_spherical_equirect,
}


def project(xyz: np.ndarray, name: str) -> np.ndarray:
    """Project (n,3) spatial points to the (n,2) XY drawing plane (spec §4.2)."""
    if name not in PROJECTIONS:
        raise ValueError(
            f"Unknown projection '{name}'; available: {sorted(PROJECTIONS)}"
        )
    return PROJECTIONS[name](xyz)


def derive_all(
    xy: Optional[np.ndarray],
    xyz: Optional[np.ndarray],
    projection: Optional[str] = None,
) -> np.ndarray:
    """Derive the full 10-column coordinate block from authoritative inputs.

    Returns (n,10): [X, Y, R, THETA, X3, Y3, Z3, RHO, THETA_S, PHI_S].
    Exactly the rule of spec §4.1.2: planar inputs get z3=0; spatial inputs
    get their XY from the declared projection. Underivable columns are NaN.
    """
    if xy is None and xyz is None:
        raise ValueError("At least one of xy or xyz must be provided")

    if xyz is None:
        assert xy is not None
        xyz = np.concatenate([xy, np.zeros((xy.shape[0], 1))], axis=1)
    if xy is None:
        if projection is None:
            raise ValueError("projection is required when only xyz is authoritative")
        xy = project(xyz, projection)

    n = xy.shape[0]
    if xyz.shape[0] != n:
        raise ValueError(f"xy has {n} rows but xyz has {xyz.shape[0]}")

    block = np.full((n, 10), np.nan, dtype=np.float64)
    block[:, 0:2] = xy
    block[:, 2:4] = xy_to_polar(xy)
    block[:, 4:7] = xyz
    block[:, 7:10] = xyz_to_spherical(xyz)
    return block

"""Vectorized helpers for pattern authors (spec §9.4).

Use these instead of hardcoding column indices or seeding module-level RNGs:
patterns must stay pure functions of (lights, t) (spec §9.1.3).
"""

from __future__ import annotations

import zlib
from typing import Union

import numpy as np

from luminary.geometry.lights import LightColumns


def column(lights: np.ndarray, col: LightColumns) -> np.ndarray:
    """One named column of the lights array."""
    return lights[:, col]


def x(lights: np.ndarray) -> np.ndarray:
    return lights[:, LightColumns.X]


def y(lights: np.ndarray) -> np.ndarray:
    return lights[:, LightColumns.Y]


def r(lights: np.ndarray) -> np.ndarray:
    return lights[:, LightColumns.R]


def theta(lights: np.ndarray) -> np.ndarray:
    return lights[:, LightColumns.THETA]


def seeded_random(salt: Union[int, str], n: int) -> np.ndarray:
    """Deterministic uniform [0,1) array, stable across processes.

    For per-entity constants (star positions, phase offsets): the salt — not
    wall-clock, not object identity — fully determines the values, keeping
    render() a pure function (spec §9.1.3).
    """
    seed = zlib.crc32(str(salt).encode())
    out: np.ndarray = np.random.default_rng(seed).random(n)
    return out


def phi_theta(lights: np.ndarray) -> tuple:
    """(phi, theta) in radians for every light, always finite.

    On a folded geometry these are the true spherical coordinates
    (PHI_S polar-from-apex, THETA_S azimuth). On an unfolded net they
    are NaN, so this substitutes a planar stand-in — normalized radius
    from the drawing's center mapped to [0, ~130°] and the planar
    azimuth — letting one spherical pattern serve both without every
    author re-inventing the fallback.
    """
    phi = lights[:, LightColumns.PHI_S].copy()
    th = lights[:, LightColumns.THETA_S].copy()
    bad = ~np.isfinite(phi)
    if bad.any():
        px = lights[:, LightColumns.X]
        py = lights[:, LightColumns.Y]
        cx, cy = float(np.mean(px)), float(np.mean(py))
        rr = np.hypot(px - cx, py - cy)
        scale = float(rr.max()) or 1.0
        phi = np.where(bad, (rr / scale) * np.radians(130.0), phi)
        th = np.where(~np.isfinite(th), np.arctan2(px - cx, -(py - cy)), th)
    return phi, th


def plane_xy(lights: np.ndarray) -> tuple:
    """Drawing-plane coordinates centered on the layout, long axis ~[-1, 1].

    Geometry-agnostic (works on any net or fold) and scale-free, so a
    pattern tuned on one sphere reads the same on another.
    """
    px = lights[:, LightColumns.X]
    py = lights[:, LightColumns.Y]
    cx = 0.5 * (float(np.min(px)) + float(np.max(px)))
    cy = 0.5 * (float(np.min(py)) + float(np.max(py)))
    scale = max(
        1e-6,
        0.5 * (float(np.max(px)) - float(np.min(px))),
        0.5 * (float(np.max(py)) - float(np.min(py))),
    )
    return (px - cx) / scale, (py - cy) / scale


def wrap_hue(h: np.ndarray) -> np.ndarray:
    """Wrap hue degrees into [0, 360)."""
    out: np.ndarray = np.mod(h, 360.0)
    return out


def nan_to_black(oklch: np.ndarray) -> np.ndarray:
    """Replace NaN rows (lights with missing coordinates) with black."""
    out: np.ndarray = np.nan_to_num(oklch, nan=0.0)
    return out

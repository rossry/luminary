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


def wrap_hue(h: np.ndarray) -> np.ndarray:
    """Wrap hue degrees into [0, 360)."""
    out: np.ndarray = np.mod(h, 360.0)
    return out


def nan_to_black(oklch: np.ndarray) -> np.ndarray:
    """Replace NaN rows (lights with missing coordinates) with black."""
    out: np.ndarray = np.nan_to_num(oklch, nan=0.0)
    return out

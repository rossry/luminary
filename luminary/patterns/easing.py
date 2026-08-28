"""Easing and envelopes: nothing in a good pattern moves linearly.

Small, vectorized, pure — the temporal counterpart of palettes.py.
Every function accepts scalars or arrays and returns float64.
"""

from __future__ import annotations

from typing import Union

import numpy as np

ScalarOrArray = Union[float, np.ndarray]


def smoothstep(edge0: float, edge1: float, x: ScalarOrArray) -> np.ndarray:
    """0 -> 1 across [edge0, edge1] with zero end slopes."""
    t = np.clip((np.asarray(x, dtype=np.float64) - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def smootherstep(edge0: float, edge1: float, x: ScalarOrArray) -> np.ndarray:
    """Like smoothstep with zero end curvature too — for slow reveals."""
    t = np.clip((np.asarray(x, dtype=np.float64) - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def ease_sin(x: ScalarOrArray) -> np.ndarray:
    """Half-cosine ease of [0,1] onto [0,1]."""
    t = np.clip(np.asarray(x, dtype=np.float64), 0.0, 1.0)
    return 0.5 - 0.5 * np.cos(np.pi * t)


def breath(t: ScalarOrArray, period: float) -> np.ndarray:
    """A calm 0..1..0 breathing cycle of the given period."""
    return 0.5 - 0.5 * np.cos(2.0 * np.pi * np.asarray(t, dtype=np.float64) / period)


def env_ad(t: ScalarOrArray, attack: float, decay: float) -> np.ndarray:
    """Attack/decay envelope: 0 at t<=0, eases to 1 over ``attack``,
    then exponentially decays with time constant ``decay``."""
    tt = np.asarray(t, dtype=np.float64)
    rising = smoothstep(0.0, attack, tt)
    falling = np.exp(-np.maximum(tt - attack, 0.0) / decay)
    return np.where(tt <= 0.0, 0.0, rising * falling)


def wrap01(x: ScalarOrArray) -> np.ndarray:
    """Fractional part, safe for negatives."""
    xx = np.asarray(x, dtype=np.float64)
    return xx - np.floor(xx)

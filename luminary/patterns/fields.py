"""Coherent fields: the workhorse math behind organic-looking patterns.

Randomness is for seeding structure; per-frame texture comes from
*coherent* noise — smooth fields sampled at light positions and pushed
through a palette. This module provides deterministic, vectorized value
noise (integer-hash based, identical on every platform — no
transcendental-hash tricks), fractal sums, domain warping, and the
shared ``ring_field`` used by both the mapping visuals and show
patterns (one implementation, per invariant §2.9).

Everything is a pure function; seeds are salts, never RNG state.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np

from luminary.patterns.util import seeded_random

_M1 = np.uint64(0x9E3779B97F4A7C15)
_M2 = np.uint64(0xC2B2AE3D27D4EB4F)
_M3 = np.uint64(0x165667B19E3779F9)


def _hash01(ix: np.ndarray, iy: np.ndarray, seed: int) -> np.ndarray:
    """Uniform [0,1) per integer lattice point — uint64 mix, exact and
    identical everywhere (wrapping arithmetic, no floats until the
    end)."""
    # The seed term is mixed in Python int space: numpy warns on uint64
    # *scalar* overflow even though the wrap is exactly what we want.
    salt = np.uint64(((seed & 0xFFFFFFFF) * int(_M3)) & 0xFFFFFFFFFFFFFFFF)
    h = ix.astype(np.uint64) * _M1 ^ iy.astype(np.uint64) * _M2 ^ salt
    h ^= h >> np.uint64(33)
    h *= _M2
    h ^= h >> np.uint64(29)
    h *= _M1
    h ^= h >> np.uint64(32)
    return (h >> np.uint64(40)).astype(np.float64) / float(1 << 24)


def value_noise(x: np.ndarray, y: np.ndarray, seed: int = 0) -> np.ndarray:
    """Smooth [0,1) noise over the plane, feature size ~1 unit."""
    xx = np.asarray(x, dtype=np.float64)
    yy = np.asarray(y, dtype=np.float64)
    ix = np.floor(xx).astype(np.int64)
    iy = np.floor(yy).astype(np.int64)
    fx = xx - ix
    fy = yy - iy
    ux = fx * fx * (3.0 - 2.0 * fx)
    uy = fy * fy * (3.0 - 2.0 * fy)
    a = _hash01(ix, iy, seed)
    b = _hash01(ix + 1, iy, seed)
    c = _hash01(ix, iy + 1, seed)
    d = _hash01(ix + 1, iy + 1, seed)
    out: np.ndarray = a + (b - a) * ux + (c - a) * uy + (a - b - c + d) * ux * uy
    return out


def fbm(
    x: np.ndarray,
    y: np.ndarray,
    seed: int = 0,
    octaves: int = 4,
    lacunarity: float = 2.0,
    gain: float = 0.5,
) -> np.ndarray:
    """Fractal sum of value noise, normalized back to [0,1)."""
    total = np.zeros(np.broadcast(x, y).shape, dtype=np.float64)
    amp = 1.0
    freq = 1.0
    norm = 0.0
    for octave in range(octaves):
        total += amp * value_noise(x * freq, y * freq, seed + 101 * octave)
        norm += amp
        amp *= gain
        freq *= lacunarity
    return total / norm


def warp(
    x: np.ndarray,
    y: np.ndarray,
    seed: int = 0,
    amount: float = 1.0,
    octaves: int = 3,
) -> Tuple[np.ndarray, np.ndarray]:
    """Domain-warped coordinates — the single cheapest way to make a
    noise field look alive instead of procedural."""
    wx = fbm(x + 17.31, y, seed + 1, octaves=octaves) - 0.5
    wy = fbm(x, y + 41.77, seed + 2, octaves=octaves) - 0.5
    return x + amount * wx, y + amount * wy


def ring_field(
    phi: np.ndarray,
    az_deg: np.ndarray,
    t: float,
    period: float,
    spin_salt: str = "map-ring",
    descent_deg: float = 130.0,
    sigma_deg: float = 6.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """(intensity, hue) of the descending elevation ring.

    THE ring: a crest sweeping apex-to-rim in ``phi`` every ``period``
    seconds, hue varying with azimuth and spun to a fresh seeded angle
    every descent. Shared by the mapping visuals (stage-C ring, the
    finale waves) and show patterns — one implementation of the motif
    (invariant §2.9); consumers differ only in styling and composition.
    """
    wave = int(t // period)
    phase = (t % period) / period
    target = phase * np.radians(descent_deg)
    diff = phi - target
    intensity = np.exp(-(diff**2) / (2 * np.radians(sigma_deg) ** 2))
    spin = 360.0 * float(seeded_random(f"{spin_salt}-{wave}", 1)[0])
    hue = (az_deg + spin) % 360.0
    return intensity, hue

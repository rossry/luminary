"""Palettes: constrained color as data, blended perceptually (spec §9.4).

The craft rule (patterns/README "color" notes): a pattern owns two or
three related hues and an accent, not the wheel. This module makes that
the path of least resistance — a :class:`Palette` is a handful of OKLCH
stops sampled by a scalar field, and every blend happens in the OKLab
vector plane (hue as a *direction*, chroma as its length), so mixes
take the short way around the wheel and low-chroma colors mix without
hue garbage.

All functions are vectorized and pure; palettes are immutable and safe
to share between pattern instances (statelessness, spec §9.1.3).
"""

from __future__ import annotations

from typing import Sequence, Tuple, Union

import numpy as np

Stop = Tuple[float, float, float, float]  # (x, L, C, H-degrees)


def oklch_to_vec(oklch: np.ndarray) -> np.ndarray:
    """(n,3) OKLCH -> (n,3) [L, C*cos(H), C*sin(H)] — the blend space."""
    out = np.empty_like(oklch, dtype=np.float64)
    h = np.radians(oklch[:, 2])
    out[:, 0] = oklch[:, 0]
    out[:, 1] = oklch[:, 1] * np.cos(h)
    out[:, 2] = oklch[:, 1] * np.sin(h)
    return out


def vec_to_oklch(vec: np.ndarray) -> np.ndarray:
    """Inverse of :func:`oklch_to_vec`."""
    out = np.empty_like(vec, dtype=np.float64)
    out[:, 0] = vec[:, 0]
    out[:, 1] = np.hypot(vec[:, 1], vec[:, 2])
    out[:, 2] = np.degrees(np.arctan2(vec[:, 2], vec[:, 1])) % 360.0
    return out


def blend_oklch(
    a: np.ndarray, b: np.ndarray, w: Union[float, np.ndarray]
) -> np.ndarray:
    """Per-light perceptual blend of two OKLCH frames.

    ``w`` is 0..1 (scalar or (n,) array): 0 -> a, 1 -> b. Blending in
    the OKLab vector plane takes hue the short way around and lets
    chroma collapse through neutral instead of sweeping the wheel —
    this is THE crossfade used by the conductor, so every composed
    transition behaves identically.
    """
    weight = np.asarray(w, dtype=np.float64)
    if weight.ndim == 1:
        weight = weight[:, None]
    mixed = oklch_to_vec(a) * (1.0 - weight) + oklch_to_vec(b) * weight
    return vec_to_oklch(mixed)


class Palette:
    """A few OKLCH stops on [0, 1], sampled by any scalar field.

    ``sample(x)`` maps each value in ``x`` (clipped to [0,1]) to a
    piecewise-linear blend of the stops, interpolated in the OKLab
    vector plane. Construction precomputes the stop vectors, so
    sampling is pure arithmetic per frame.
    """

    def __init__(self, stops: Sequence[Stop]) -> None:
        if len(stops) < 2:
            raise ValueError("a palette needs at least two stops")
        xs = np.asarray([s[0] for s in stops], dtype=np.float64)
        if not np.all(np.diff(xs) > 0):
            raise ValueError("palette stops must be in increasing x order")
        lch = np.asarray([[s[1], s[2], s[3]] for s in stops], dtype=np.float64)
        self._xs = xs
        self._vecs = oklch_to_vec(lch)

    def sample(self, x: np.ndarray) -> np.ndarray:
        """(n,) field values -> (n,3) OKLCH."""
        xx = np.clip(np.asarray(x, dtype=np.float64), self._xs[0], self._xs[-1])
        hi = np.clip(np.searchsorted(self._xs, xx, side="right"), 1, len(self._xs) - 1)
        lo = hi - 1
        span = self._xs[hi] - self._xs[lo]
        f = ((xx - self._xs[lo]) / span)[:, None]
        mixed = self._vecs[lo] * (1.0 - f) + self._vecs[hi] * f
        return vec_to_oklch(mixed)

    def shifted(self, dh: float) -> "Palette":
        """The same palette with every hue rotated by ``dh`` degrees —
        the cheap way to re-key a movement without re-tuning it."""
        lch = vec_to_oklch(self._vecs)
        stops = [
            (float(x), float(l), float(c), float((h + dh) % 360.0))
            for x, (l, c, h) in zip(self._xs, lch)
        ]
        return Palette(stops)

    def dimmed(self, gain: float) -> "Palette":
        """The same palette with L scaled by ``gain`` (chroma follows
        at half strength so dim colors do not read oversaturated)."""
        lch = vec_to_oklch(self._vecs)
        stops = [
            (
                float(x),
                float(l * gain),
                float(c * (0.5 + 0.5 * gain)),
                float(h),
            )
            for x, (l, c, h) in zip(self._xs, lch)
        ]
        return Palette(stops)


# A few tuned houses palettes for the sphere (L modest — darkness is
# the canvas; C well under the codec's 0.4 ceiling).
NIGHT_SKY = Palette(
    [(0.0, 0.02, 0.01, 260.0), (0.6, 0.10, 0.04, 250.0), (1.0, 0.55, 0.09, 230.0)]
)
CANDLE = Palette(
    [(0.0, 0.02, 0.02, 40.0), (0.5, 0.28, 0.11, 55.0), (1.0, 0.72, 0.13, 85.0)]
)
AURORA = Palette(
    [
        (0.0, 0.03, 0.02, 200.0),
        (0.45, 0.30, 0.13, 160.0),
        (0.8, 0.55, 0.15, 130.0),
        (1.0, 0.62, 0.13, 300.0),
    ]
)
EMBER = Palette(
    [(0.0, 0.01, 0.01, 25.0), (0.55, 0.22, 0.13, 30.0), (1.0, 0.60, 0.15, 55.0)]
)
SEA_GLASS = Palette(
    [(0.0, 0.03, 0.02, 220.0), (0.55, 0.26, 0.10, 195.0), (1.0, 0.60, 0.12, 170.0)]
)

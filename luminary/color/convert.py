"""Vectorized color conversions: OKLCH / OKLab / linear sRGB / sRGB8 (spec §8).

This module is the hot-path color pipeline: every function takes and returns
(n,3) float arrays and contains no Python loops. The matrices are Björn
Ottosson's OKLab constants, normative in spec §8.4 and mirrored bit-for-bit
by the firmware's fixed-point tables and the web client's JS.

Hue is degrees at this API boundary (patterns speak degrees); radians never
appear in stored color values.
"""

from __future__ import annotations

import numpy as np

C_MAX = 0.4  # chroma ceiling used by quantization (spec §11.4.1)

# OKLab -> LMS' (decode direction, spec §8.4.1)
_OKLAB_TO_LMS = np.array(
    [
        [1.0, 0.3963377774, 0.2158037573],
        [1.0, -0.1055613458, -0.0638541728],
        [1.0, -0.0894841775, -1.2914855480],
    ]
)

# LMS -> linear sRGB (decode direction, spec §8.4.1)
_LMS_TO_LRGB = np.array(
    [
        [4.0767416621, -3.3077115913, 0.2309699292],
        [-1.2684380046, 2.6097574011, -0.3413193965],
        [-0.0041960863, -0.7034186147, 1.7076147010],
    ]
)

# linear sRGB -> LMS (encode direction; documented inverse, spec §8.4.2)
_LRGB_TO_LMS = np.array(
    [
        [0.4122214708, 0.5363325363, 0.0514459929],
        [0.2119034982, 0.6806995451, 0.1073969566],
        [0.0883024619, 0.2817188376, 0.6299787005],
    ]
)

# LMS' -> OKLab (encode direction)
_LMS_TO_OKLAB = np.array(
    [
        [0.2104542553, 0.7936177850, -0.0040720468],
        [1.9779984951, -2.4285922050, 0.4505937099],
        [0.0259040371, 0.7827717662, -0.8086757660],
    ]
)


def oklch_to_oklab(oklch: np.ndarray) -> np.ndarray:
    """(n,3) [L, C, H(deg)] -> (n,3) [L, a, b]."""
    h_rad = np.deg2rad(oklch[:, 2])
    return np.stack(
        [
            oklch[:, 0],
            oklch[:, 1] * np.cos(h_rad),
            oklch[:, 1] * np.sin(h_rad),
        ],
        axis=1,
    )


def oklab_to_oklch(oklab: np.ndarray) -> np.ndarray:
    """(n,3) [L, a, b] -> (n,3) [L, C, H(deg) in [0,360)]."""
    c = np.hypot(oklab[:, 1], oklab[:, 2])
    h = np.rad2deg(np.arctan2(oklab[:, 2], oklab[:, 1])) % 360.0
    return np.stack([oklab[:, 0], c, h], axis=1)


def oklab_to_linear_srgb(oklab: np.ndarray) -> np.ndarray:
    """(n,3) OKLab -> (n,3) linear sRGB (may be out of [0,1] gamut)."""
    lms_prime = oklab @ _OKLAB_TO_LMS.T
    lms = lms_prime**3
    out: np.ndarray = lms @ _LMS_TO_LRGB.T
    return out


def linear_srgb_to_oklab(lrgb: np.ndarray) -> np.ndarray:
    """(n,3) linear sRGB -> (n,3) OKLab."""
    lms = lrgb @ _LRGB_TO_LMS.T
    lms_prime = np.cbrt(lms)
    out: np.ndarray = lms_prime @ _LMS_TO_OKLAB.T
    return out


def linear_to_srgb(linear: np.ndarray) -> np.ndarray:
    """Gamma-encode linear sRGB (any shape), clamped to [0,1] (spec §8.4.2)."""
    linear = np.clip(linear, 0.0, 1.0)
    return np.where(
        linear <= 0.0031308,
        12.92 * linear,
        1.055 * np.power(linear, 1.0 / 2.4) - 0.055,
    )


def srgb_to_linear(srgb: np.ndarray) -> np.ndarray:
    """Decode gamma sRGB (any shape, values in [0,1]) to linear."""
    return np.where(
        srgb <= 0.04045,
        srgb / 12.92,
        np.power((srgb + 0.055) / 1.055, 2.4),
    )


def linear_to_srgb8(linear: np.ndarray) -> np.ndarray:
    """Linear sRGB -> gamma-encoded uint8 (spec §8.4.2)."""
    out: np.ndarray = np.rint(255.0 * linear_to_srgb(linear)).astype(np.uint8)
    return out


def srgb8_to_linear(srgb8: np.ndarray) -> np.ndarray:
    """uint8 sRGB -> linear float."""
    out: np.ndarray = srgb_to_linear(srgb8.astype(np.float64) / 255.0)
    return out


def in_gamut(lrgb: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    """(n,3) linear sRGB -> (n,) bool: all channels within [0,1]."""
    out: np.ndarray = np.all((lrgb >= -eps) & (lrgb <= 1.0 + eps), axis=1)
    return out


def gamut_clip_oklab(oklab: np.ndarray, iterations: int = 12) -> np.ndarray:
    """Map out-of-gamut OKLab colors to sRGB gamut by reducing chroma.

    Deterministic and documented (spec §8.3.1): L and hue are held fixed
    (after clamping L to [0,1]); (a,b) are scaled by the largest factor in
    [0,1] that lands inside the gamut, found by vectorized bisection.
    """
    out: np.ndarray = oklab.copy()
    out[:, 0] = np.clip(out[:, 0], 0.0, 1.0)
    bad = ~in_gamut(oklab_to_linear_srgb(out))
    if not np.any(bad):
        return out

    ab = out[bad, 1:3]
    lightness = out[bad, 0:1]
    lo = np.zeros(ab.shape[0])
    hi = np.ones(ab.shape[0])
    for _ in range(iterations):
        mid = 0.5 * (lo + hi)
        candidate = np.concatenate([lightness, ab * mid[:, None]], axis=1)
        ok = in_gamut(oklab_to_linear_srgb(candidate))
        lo = np.where(ok, mid, lo)
        hi = np.where(ok, hi, mid)
    out[bad, 1:3] = ab * lo[:, None]
    result: np.ndarray = out
    return result


def oklch_to_srgb8(oklch: np.ndarray, clip: bool = True) -> np.ndarray:
    """(n,3) OKLCH -> (n,3) uint8 sRGB; the canonical output chain (spec §8.2.3)."""
    oklab = oklch_to_oklab(oklch)
    if clip:
        oklab = gamut_clip_oklab(oklab)
    return linear_to_srgb8(oklab_to_linear_srgb(oklab))


def srgb8_to_oklch(srgb8: np.ndarray) -> np.ndarray:
    """(n,3) uint8 sRGB -> (n,3) OKLCH."""
    return oklab_to_oklch(linear_srgb_to_oklab(srgb8_to_linear(srgb8)))

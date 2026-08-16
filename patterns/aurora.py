"""Aurora: curtains of polar light drifting over a night sky.

Medium notes: built for dark-adapted viewing — a near-black indigo sky
(L floor a few wire-LSBs above zero) under slow curtains whose lower
border is sharp and whose tops fade tall. The hue ramp is the physical
one (green core -> teal -> violet fringe) walked continuously in OKLCH,
which keeps every intermediate step luminous instead of muddy. All
motion is slow phase drift on incommensurate periods, so dead reckoning
tracks it cheaply and the sky never visibly repeats.
"""

import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern
from luminary.patterns.util import seeded_random


def _smoothstep(v: np.ndarray, lo: float, hi: float) -> np.ndarray:
    u = np.clip((v - lo) / (hi - lo), 0.0, 1.0)
    out: np.ndarray = u * u * (3.0 - 2.0 * u)
    return out


class AuroraPattern(Pattern):
    name = "aurora"
    description = "Slow curtains of auroral light: green cores, violet fringes"

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        x_raw = lights[:, LightColumns.X]
        y_raw = lights[:, LightColumns.Y]
        x_min, x_max = float(np.min(x_raw)), float(np.max(x_raw))
        y_min, y_max = float(np.min(y_raw)), float(np.max(y_raw))
        xn = (x_raw - 0.5 * (x_min + x_max)) / max(1e-6, 0.5 * (x_max - x_min))
        # SVG y grows downward; h is height above the bottom edge, 0..1.
        h = (y_max - y_raw) / max(1e-6, y_max - y_min)

        # Curtain sheets: broad ridge functions of x whose positions drift
        # and sway on incommensurate clocks.
        curtain = np.zeros_like(xn)
        for k, (freq, amp, sway, drift, weight) in enumerate(
            [
                (1.4, 0.55, 0.171, 0.026, 1.00),
                (2.5, 0.42, 0.113, -0.034, 0.70),
                (3.9, 0.30, 0.067, 0.051, 0.45),
            ]
        ):
            phase = (
                xn * freq
                + amp * np.sin(xn * (freq * 0.61) + t * sway + k * 2.1)
                + t * drift * freq
            )
            ridge = 0.5 + 0.5 * np.cos(phase * np.pi)
            curtain += weight * ridge**3
        curtain = curtain / 1.6 + 0.10  # faint airglow between curtains

        # Vertical profile: sharp lower border arcing slowly, long fade up.
        border = 0.10 + 0.08 * np.sin(xn * 1.3 + t * 0.11) + 0.03 * np.sin(t * 0.043)
        u = h - border
        vertical = _smoothstep(u, -0.03, 0.07) * np.exp(-np.maximum(u, 0.0) / 0.62)

        # Fine shimmer rippling along the curtains.
        shimmer = 1.0 + 0.13 * np.sin(
            xn * 17.0 - t * 2.1 + 3.0 * np.sin(xn * 6.7 + t * 0.53)
        )

        intensity = np.clip(curtain * vertical * shimmer, 0.0, 1.15)

        # Sparse background stars with slow hashed twinkle.
        n = lights.shape[0]
        star_pick = seeded_random("aurora-star", n)
        star_phase = seeded_random("aurora-star-phase", n)
        is_star = star_pick < 0.02
        twinkle = 0.5 + 0.5 * np.sin(
            2.0 * np.pi * (t / (5.0 + 4.0 * star_phase) + star_phase)
        )
        stars = np.where(is_star, 0.10 * twinkle**2, 0.0)

        # Sky base -> curtain color, all in OKLCH.
        fringe = _smoothstep(u, 0.10, 0.55)  # how far up the ray we are
        out = np.zeros((n, 3))
        out[:, 0] = np.clip(0.045 + 0.70 * intensity**0.95 + stars, 0.0, 0.92)
        out[:, 1] = np.clip(
            0.055 + 0.30 * _smoothstep(intensity, 0.03, 0.60) * (1.0 - 0.25 * fringe),
            0.0,
            0.34,
        )
        # Green core sweeping through teal and blue to a violet fringe.
        hue = 145.0 + 148.0 * fringe**1.5 + 6.0 * np.sin(xn * 2.0 + t * 0.07)
        sky_hue = 272.0
        blend = _smoothstep(intensity, 0.015, 0.22)
        out[:, 2] = (sky_hue + (hue - sky_hue) * blend) % 360.0
        return out

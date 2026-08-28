"""Sanctum: the structure itself breathing — a five-fold ceremony.

Medium notes: this one is *of* the pentagon rather than projected onto
it. The five-lobed angular mask is phase-locked to the arm directions
(lobe centers at -90 + 36 + k*72 degrees, the layer-2 star points), and
each 13-second breath carries a ring of candle-gold from the inner
pentagon out to the tips, where a cool silver answer glows on the
exhale. Slow standing waves are nearly free on the wire; the piece
reads as architecture meditating, not as animation played on it.
"""

import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern

_BREATH = 13.0  # seconds per breath
_LOBE0 = np.radians(-54.0)  # first star-point direction (up-right arm)


def _smoothstep(v: np.ndarray, lo: float, hi: float) -> np.ndarray:
    u = np.clip((v - lo) / (hi - lo), 0.0, 1.0)
    out: np.ndarray = u * u * (3.0 - 2.0 * u)
    return out


class SanctumPattern(Pattern):
    name = "sanctum"
    description = "Five-fold breathing: candle-gold rising, silver answering"

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        x_raw = lights[:, LightColumns.X]
        y_raw = lights[:, LightColumns.Y]
        cx = 0.5 * (float(np.min(x_raw)) + float(np.max(x_raw)))
        cy = 0.5 * (float(np.min(y_raw)) + float(np.max(y_raw)))
        dx, dy = x_raw - cx, y_raw - cy
        rn = np.hypot(dx, dy)
        rn = rn / max(1e-6, float(np.max(rn)))
        th = np.arctan2(dy, dx)

        # Breath: eased inhale/exhale, plus its inverse for the answer.
        phase = 2.0 * np.pi * t / _BREATH
        breath = (0.5 - 0.5 * np.cos(phase)) ** 1.1
        exhale = (0.5 + 0.5 * np.cos(phase)) ** 1.8

        # Five lobes locked to the star points; slow secondary shimmer
        # rotating against them keeps the mandala alive.
        lobes = 0.55 + 0.45 * np.cos(5.0 * (th - _LOBE0))
        weave = 0.85 + 0.15 * np.cos(10.0 * th + 2.0 * np.pi * t / 41.0)
        mask = np.clip(lobes, 0.0, 1.0) ** 1.3 * weave

        # A ring of light that each breath carries from the core outward,
        # over a faint steady skeleton so the mandala never fully sleeps.
        ring_center = 0.16 + 0.70 * breath
        ring = np.exp(-((rn - ring_center) ** 2) / (2.0 * 0.19**2))
        # Standing radial wave gives the ring internal structure.
        grain = 0.85 + 0.15 * np.cos(rn * 2.0 * np.pi * 2.6 - 2.0 * np.pi * t / 29.0)
        glow = np.clip((0.14 + 0.98 * ring) * mask * grain, 0.0, 1.1)

        # Inner sanctum: a steady candle at the pentagon ring.
        candle_flicker = 0.06 * np.sin(2.0 * np.pi * 0.73 * t) + 0.04 * np.sin(
            2.0 * np.pi * 1.13 * t + 1.7
        )
        sanctum = np.exp(-((rn - 0.185) ** 2) / (2.0 * 0.055**2)) * (
            0.62 + candle_flicker
        )

        # The tips answer in silver-blue on the exhale.
        tips = _smoothstep(rn, 0.74, 0.92) * mask * exhale * 1.5

        out = np.zeros((lights.shape[0], 3))
        warm = np.clip(glow * 0.9 + sanctum, 0.0, 1.1)
        cool = np.clip(tips, 0.0, 1.0)
        out[:, 0] = np.clip(0.045 + 0.55 * warm + 0.34 * cool, 0.0, 0.88)
        out[:, 1] = np.clip(
            0.06
            + 0.16 * _smoothstep(warm, 0.05, 0.8)
            + 0.06 * cool
            - 0.05 * _smoothstep(warm, 0.9, 1.1),
            0.0,
            0.26,
        )
        # Indigo field; candle-gold where warm; slide toward silver-blue
        # where the cool answer dominates.
        base_h = 268.0
        warm_h = 80.0
        dominance = np.clip(warm * 1.2 - cool, 0.0, 1.0)
        w_blend = _smoothstep(dominance, 0.03, 0.35)
        # +172° arc: indigo -> magenta -> red -> gold (the candle-warm way).
        hue = base_h + ((warm_h - base_h + 360.0) % 360.0) * w_blend
        c_blend = _smoothstep(cool - warm, 0.02, 0.4)
        hue = hue + (232.0 - base_h) * c_blend * (1.0 - w_blend)
        out[:, 2] = hue % 360.0
        return out

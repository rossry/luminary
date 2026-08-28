"""Tidepool: bioluminescence answering a slow midnight swell.

Medium notes: the piece becomes still black water. A broad swell (one
soft ridge of slightly-lifted blue) crosses on a ~19 s period along a
slowly precessing axis; in its wake, plankton bloom — soft cyan glows a
couple of facets wide, placed by hashed anchors and timed to when the
crest passed each anchor, flaring fast and decaying over seconds. Which
blooms exist in a given sweep is a closed-form function of the cycle
number, so the water is stateless yet never twice the same. Working at
bloom scale (several beams per glow) rather than single-light scale is
what makes it read as water instead of static. A magenta jelly drifts
through on rare slots, pulsing.
"""

import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern
from luminary.patterns.util import seeded_random

_SWEEP = 19.0  # seconds per swell crossing
_SPAN = 1.65  # swell travels s in [-_SPAN, +_SPAN]
_BLOOMS = 26  # bloom anchors per sweep cycle
_JELLY_SLOT = 45.0


def _smoothstep(v: np.ndarray, lo: float, hi: float) -> np.ndarray:
    u = np.clip((v - lo) / (hi - lo), 0.0, 1.0)
    out: np.ndarray = u * u * (3.0 - 2.0 * u)
    return out


class TidepoolPattern(Pattern):
    name = "tidepool"
    description = "A slow swell over black water; plankton bloom in its wake"

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n = lights.shape[0]
        x_raw = lights[:, LightColumns.X]
        y_raw = lights[:, LightColumns.Y]
        x_min, x_max = float(np.min(x_raw)), float(np.max(x_raw))
        y_min, y_max = float(np.min(y_raw)), float(np.max(y_raw))
        xn = (x_raw - 0.5 * (x_min + x_max)) / max(1e-6, 0.5 * (x_max - x_min))
        yn = (y_raw - 0.5 * (y_min + y_max)) / max(1e-6, 0.5 * (y_max - y_min))

        # Swell along a slowly precessing axis.
        psi = 2.0 * np.pi * t / 210.0
        cpsi, spsi = np.cos(psi), np.sin(psi)
        s = xn * cpsi + yn * spsi
        v = 2.0 * _SPAN / _SWEEP
        cycle = int(t / _SWEEP)
        crest = -_SPAN + v * (t - cycle * _SWEEP)
        swell = np.exp(-((s - crest) ** 2) / (2.0 * 0.42**2))

        # Plankton blooms: hashed anchors per sweep cycle, each flaring
        # when the crest passes it (plus a personal delay), glowing a
        # couple of facets wide and decaying over seconds.
        bloom = np.zeros(n)
        bloom_hue_w = np.zeros(n)
        for c in (cycle - 1, cycle):
            if c < 0:
                continue
            br = seeded_random(f"tide-bloom-{c}", _BLOOMS * 5).reshape(_BLOOMS, 5)
            ax = (br[:, 0] * 2.0 - 1.0) * 0.95
            ay = (br[:, 1] * 2.0 - 1.0) * 0.80
            s_anchor = ax * cpsi + ay * spsi
            t_hit = c * _SWEEP + (s_anchor + _SPAN) / v + br[:, 2] * 2.2
            rel = t - t_hit
            envelope = np.where(
                rel >= 0.0,
                np.minimum(rel / 0.28, 1.0) ** 2
                * np.exp(-np.maximum(rel - 0.28, 0.0) / 2.3),
                0.0,
            ) * (0.45 + 0.55 * br[:, 3])
            live = envelope > 1e-3
            if not np.any(live):
                continue
            d2 = (xn[:, None] - ax[None, live]) ** 2 + (
                yn[:, None] - ay[None, live]
            ) ** 2
            g = np.exp(-d2 / (2.0 * 0.058**2)) * envelope[None, live]
            bloom = bloom + g.sum(axis=1)
            bloom_hue_w = bloom_hue_w + (g * br[None, live, 4]).sum(axis=1)
        bloom = np.clip(bloom, 0.0, 1.2)
        hue_scatter = np.where(bloom > 1e-6, bloom_hue_w / np.maximum(bloom, 1e-6), 0.5)

        # A jelly on rare slots: soft pulsing disk drifting upward.
        jslot = int(t / _JELLY_SLOT)
        jelly = np.zeros(n)
        jr = seeded_random(f"tide-jelly-{jslot}", 4)
        if jr[0] < 0.65:
            jt = (t - jslot * _JELLY_SLOT) / _JELLY_SLOT
            jx = (jr[1] * 2.0 - 1.0) * 0.55
            jy = 0.75 - 1.4 * jt  # upward in SVG coords means y decreasing
            d2j = (xn - jx) ** 2 + (yn - jy) ** 2
            pulsebeat = 0.55 + 0.45 * np.sin(2.0 * np.pi * t / 3.4 + jr[2] * 6.28)
            fade = np.sin(np.pi * np.clip(jt, 0.0, 1.0))
            jelly = np.exp(-d2j / (2.0 * 0.20**2)) * pulsebeat * fade

        out = np.zeros((n, 3))
        depth = 0.5 * (yn + 1.0)  # deeper toward the bottom of the piece
        out[:, 0] = np.clip(
            0.036 + 0.014 * depth + 0.11 * swell + 0.66 * bloom + 0.26 * jelly,
            0.0,
            0.88,
        )
        out[:, 1] = np.clip(
            0.055 + 0.045 * swell + 0.28 * _smoothstep(bloom, 0.03, 0.6) + 0.11 * jelly,
            0.0,
            0.34,
        )
        base_h = 227.0 - 16.0 * depth - 30.0 * swell  # swell lifts toward teal
        flare_h = 168.0 + 34.0 * hue_scatter
        fb = _smoothstep(bloom, 0.02, 0.30)
        hue = base_h + (flare_h - base_h) * fb
        jb = _smoothstep(jelly, 0.05, 0.5) * (1.0 - fb)
        hue = hue + ((318.0 - hue + 540.0) % 360.0 - 180.0) * jb
        out[:, 2] = hue % 360.0
        return out

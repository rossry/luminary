"""Gentle whole-surface breathing with a soft radial falloff."""

import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern


def _ease(v: np.ndarray) -> np.ndarray:
    return 3.0 * v**2 - 2.0 * v**3


class BreathePattern(Pattern):
    name = "breathe"
    description = "Gentle breathing with pulsing luminance"

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        x = lights[:, LightColumns.X]
        y = lights[:, LightColumns.Y]
        cx, cy = np.mean(x), np.mean(y)
        r = np.hypot(x - cx, y - cy)
        r_max = max(float(np.max(r)), 1e-6)

        breath = _ease(0.5 * (1.0 + np.sin(2.0 * np.pi * 0.18 * t)))
        chroma_pulse = 0.5 * (1.0 + np.sin(2.0 * np.pi * 0.11 * t + 1.2))
        spatial = 1.0 - 0.3 * (r / r_max)

        out = np.zeros((lights.shape[0], 3))
        out[:, 0] = np.clip((0.25 + 0.6 * breath) * spatial, 0.0, 1.0)
        out[:, 1] = 0.06 + 0.14 * chroma_pulse
        out[:, 2] = (30.0 + 20.0 * breath + 10.0 * (r / r_max)) % 360.0
        return out

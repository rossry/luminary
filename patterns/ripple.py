"""Expanding circular waves from the geometry's center."""

import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern


class RipplePattern(Pattern):
    name = "ripple"
    description = "Expanding circular waves with rotating hue"

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        x = lights[:, LightColumns.X]
        y = lights[:, LightColumns.Y]
        cx, cy = np.mean(x), np.mean(y)
        r = np.hypot(x - cx, y - cy)
        r_max = max(float(np.max(r)), 1e-6)

        period = 3.0  # seconds between wave launches
        speed = r_max / 2.4  # cross the geometry in ~2.4 s
        width = r_max * 0.12

        intensity = np.zeros_like(r)
        for wave in range(3):
            phase = (t - wave * period / 3.0) % period
            wave_r = phase * speed
            d = np.abs(r - wave_r)
            intensity += np.exp(-d / width) * np.exp(-wave_r / (1.5 * r_max))
        intensity = np.clip(intensity, 0.0, 1.0)

        out = np.zeros((lights.shape[0], 3))
        out[:, 0] = 0.15 + 0.55 * intensity
        out[:, 1] = 0.15 + 0.25 * intensity
        out[:, 2] = (r / r_max * 120.0 + t * 40.0) % 360.0
        return out

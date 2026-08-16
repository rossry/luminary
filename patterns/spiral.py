"""Rotating logarithmic spiral arms with a radial color gradient."""

import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern


class SpiralPattern(Pattern):
    name = "spiral"
    description = "Three rotating spiral arms with radial gradient"

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        x = lights[:, LightColumns.X]
        y = lights[:, LightColumns.Y]
        cx, cy = np.mean(x), np.mean(y)
        dx, dy = x - cx, y - cy
        r = np.hypot(dx, dy)
        theta = np.arctan2(dy, dx)
        r_max = max(float(np.max(r)), 1e-6)

        n_arms = 3
        tightness = 2.2
        rotation = np.radians(45.0) * t
        arm_width = 0.35  # radians of angular falloff

        log_r = np.log(np.maximum(r / r_max, 1e-3))
        intensity = np.zeros_like(r)
        for arm in range(n_arms):
            arm_angle = arm * 2.0 * np.pi / n_arms + rotation + tightness * log_r
            diff = np.abs((theta - arm_angle + np.pi) % (2.0 * np.pi) - np.pi)
            intensity += np.exp(-diff / arm_width)
        intensity = np.clip(intensity, 0.0, 1.0)

        out = np.zeros((lights.shape[0], 3))
        out[:, 0] = 0.12 + 0.6 * intensity
        out[:, 1] = 0.1 + 0.28 * intensity
        out[:, 2] = (r / r_max * 200.0 + t * 25.0) % 360.0
        return out

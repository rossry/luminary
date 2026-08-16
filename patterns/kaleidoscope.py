"""Kaleidoscope: radially symmetric rotating geometric shapes."""

import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern


class KaleidoscopePattern(Pattern):
    name = "kaleidoscope"
    description = "Six-fold mirrored rotating shapes, like a kaleidoscope"

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        x = lights[:, LightColumns.X]
        y = lights[:, LightColumns.Y]
        cx, cy = np.mean(x), np.mean(y)
        dx, dy = x - cx, y - cy
        r = np.hypot(dx, dy)
        theta = np.arctan2(dy, dx)
        r_max = max(float(np.max(r)), 1e-6)
        scale = r_max / 130.0  # original constants were tuned for r ~ 130

        num_segments = 6
        segment_angle = 2.0 * np.pi / num_segments
        theta_rotated = theta + t * 0.3
        theta_folded = np.abs((theta_rotated % segment_angle) - segment_angle / 2)
        x_sym = r * np.cos(theta_folded)
        y_sym = r * np.sin(theta_folded)

        total = np.zeros_like(r)

        # Radial stripes at mid-radius
        stripes = np.sin(theta_folded * 8 + t * 2.0) * 0.5 + 0.5
        total += 0.4 * np.exp(-((r - 50 * scale) ** 2) / (800 * scale**2)) * stripes

        # Concentric circles with angular modulation
        for i in range(4):
            radius = (30 + i * 25) * scale
            thickness = 8 * scale
            circle = np.exp(-((r - radius) ** 2) / thickness**2)
            circle *= 0.6 + 0.4 * np.sin(theta_folded * (3 + i) + t * (1.5 + i * 0.5))
            total += 0.3 * circle

        # Triangular/diamond interference in folded space
        tri1 = np.sin(x_sym * 0.08 / scale + t * 1.2) * np.cos(
            y_sym * 0.06 / scale + t * 0.8
        )
        tri2 = np.sin((x_sym * 0.05 + y_sym * 0.07) / scale + t * 1.8)
        total += 0.5 * ((tri1 + tri2) * 0.5 + 0.5) * np.exp(-r / (100 * scale))

        # Center star burst
        total += (
            0.6
            * np.exp(-r / (20 * scale))
            * (np.sin(theta_folded * 12 + t * 3.0) * 0.5 + 0.5)
        )

        total = np.clip(total, 0.0, 1.0)

        out = np.zeros((lights.shape[0], 3))
        out[:, 0] = 0.1 + 0.6 * total
        out[:, 1] = 0.05 + 0.4 * total
        segment_hue = (theta_rotated / segment_angle) * 60.0
        out[:, 2] = (segment_hue + r * 0.5 / scale + t * 30.0 + total * 90.0) % 360.0

        dark = total < 0.1
        out[dark, 0] = np.maximum(out[dark, 0], 0.02)
        out[dark, 1] = 0.01
        return out

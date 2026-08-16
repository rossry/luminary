"""Linear traveling waves interfering across the geometry."""

import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern


class WavePattern(Pattern):
    name = "wave"
    description = "Interfering linear waves in three directions"

    _DIRECTIONS = np.array(
        [
            [1.0, 0.35],
            [-0.4, 1.0],
            [0.9, -0.8],
        ]
    )
    _WAVELENGTH_FRACTIONS = np.array([0.45, 0.28, 0.7])  # of geometry size

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        x = lights[:, LightColumns.X]
        y = lights[:, LightColumns.Y]
        span = max(float(np.max(x) - np.min(x)), float(np.max(y) - np.min(y)), 1e-6)

        total = np.zeros_like(x)
        for i, direction in enumerate(self._DIRECTIONS):
            unit = direction / np.linalg.norm(direction)
            wavelength = self._WAVELENGTH_FRACTIONS[i] * span
            k = 2.0 * np.pi / wavelength
            speed = 0.25 * span  # units per second
            phase = k * (x * unit[0] + y * unit[1]) - k * speed * t
            total += np.sin(phase + i * 1.3)
        normalized = (total / 3.0 + 1.0) / 2.0
        contrast = normalized**2.0

        out = np.zeros((lights.shape[0], 3))
        out[:, 0] = 0.1 + 0.65 * contrast
        out[:, 1] = 0.12 + 0.24 * contrast
        out[:, 2] = (200.0 + 120.0 * normalized + t * 15.0) % 360.0
        return out

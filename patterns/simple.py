"""Rotating hue wheel — the minimal reference pattern."""

import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern


class SimplePattern(Pattern):
    name = "simple"
    description = "Rotating hue wheel around the origin"

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        theta = lights[:, LightColumns.THETA]
        out = np.zeros((lights.shape[0], 3))
        out[:, 0] = 0.6
        out[:, 1] = 0.3
        out[:, 2] = (np.degrees(theta) + t * 60.0) % 360.0
        return out

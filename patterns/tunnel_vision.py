"""Tunnel vision: concentric rings racing toward (or away from) a center."""

import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern


class TunnelVisionPattern(Pattern):
    name = "tunnel_vision"
    description = "Concentric rings racing toward center, reversing each minute"

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        x = lights[:, LightColumns.X]
        y = lights[:, LightColumns.Y]
        cx = np.mean(x)
        cy = np.max(y) - (np.max(y) - np.min(y)) * 0.375
        r = np.hypot(x - cx, y - cy)
        r_max = max(float(np.max(r)), 1e-6)
        scale = r_max / 150.0  # original constants tuned for r ~ 150

        speed = 25.0 * scale
        spacing = 35.0 * scale
        width = 15.0 * scale
        num_rings = 12
        max_radius = r_max * 1.2

        # Direction flips every 60 s; deterministic (was a random init offset).
        going_inward = (int(t / 60.0) % 2) == 0

        total = np.zeros_like(r)
        cycle = num_rings * spacing
        for ring in range(num_rings):
            offset = (t * speed + ring * spacing) % cycle
            if going_inward:
                ring_radius = max_radius - offset
                if ring_radius < 0:
                    ring_radius += cycle
                fade = np.clip(ring_radius / (r_max * 0.4), 0.2, 1.0)
            else:
                ring_radius = offset - max_radius * 0.3
                if ring_radius > max_radius:
                    ring_radius -= cycle
                fade = np.clip((max_radius - ring_radius) / (r_max * 0.4), 0.2, 1.0)
            if -spacing < ring_radius < max_radius + spacing:
                intensity = np.exp(-((r - ring_radius) ** 2) / width**2) * fade
                intensity *= 0.7 + 0.5 * np.sin(ring * 1.8 + t * 2.0)
                total += intensity

        total = np.clip(total, 0.0, 1.0)

        out = np.zeros((lights.shape[0], 3))
        out[:, 0] = 0.08 + 0.7 * total
        out[:, 1] = 0.1 + 0.35 * total
        out[:, 2] = (r * 0.8 / scale + t * 60.0 + total * 120.0) % 360.0

        invisible = total <= 0.05
        out[invisible, 0] = 0.02
        out[invisible, 1] = 0.0
        return out

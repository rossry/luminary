"""Electric plasma storm: layered interference plus deterministic lightning.

Reworked from the 2.0 version, whose Poisson lightning spawner mutated
instance state across frames. Here lightning is a pure function of t: time is
divided into fixed slots, and each slot's bolt (whether it fires, when, where,
and its jagged path) is derived from seeded randomness keyed by the slot
number (spec §9.1.3) — so any frame can be recomputed in isolation.
"""

import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern
from luminary.patterns.util import seeded_random

_SLOT_SECONDS = 1.7
_BOLT_SECONDS = 0.45
_BOLT_PROBABILITY = 0.6
_JAG_SEGMENTS = 8


def _bolt_for_slot(slot: int) -> dict:
    """Deterministic bolt parameters for a time slot (or no bolt)."""
    rand = seeded_random(f"plasma-bolt-{slot}", 6 + (_JAG_SEGMENTS - 1))
    if rand[0] > _BOLT_PROBABILITY:
        return {"active": False}
    start_time = slot * _SLOT_SECONDS + rand[1] * (_SLOT_SECONDS - _BOLT_SECONDS)
    # Endpoints in normalized [-1,1] space; bias to cross the middle.
    p0 = np.array([rand[2] * 2.0 - 1.0, 1.0])
    p1 = np.array([rand[3] * 2.0 - 1.0, -1.0])
    u = np.linspace(0.0, 1.0, _JAG_SEGMENTS + 1)
    points = p0[None, :] + u[:, None] * (p1 - p0)[None, :]
    chord = p1 - p0
    perp = np.array([-chord[1], chord[0]])
    perp = perp / max(np.linalg.norm(perp), 1e-6)
    deviations = (rand[6:] * 2.0 - 1.0) * 0.15
    points[1:-1] += perp[None, :] * deviations[:, None]
    return {"active": True, "start": start_time, "points": points}


def _polyline_distance(x: np.ndarray, y: np.ndarray, points: np.ndarray) -> np.ndarray:
    """Min distance from each (x,y) to a polyline, vectorized per segment."""
    best = np.full(x.shape, np.inf)
    for a, b in zip(points[:-1], points[1:]):
        ab = b - a
        denominator = float(ab @ ab)
        ap_x, ap_y = x - a[0], y - a[1]
        s = np.clip((ap_x * ab[0] + ap_y * ab[1]) / max(denominator, 1e-9), 0.0, 1.0)
        d = np.hypot(ap_x - s * ab[0], ap_y - s * ab[1])
        best = np.minimum(best, d)
    return best


class PlasmaStormPattern(Pattern):
    name = "plasma_storm"
    description = "Electric interference plasma with deterministic lightning"

    _LAYERS = 6

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        x_raw = lights[:, LightColumns.X]
        y_raw = lights[:, LightColumns.Y]
        x_min, x_max = float(np.min(x_raw)), float(np.max(x_raw))
        y_min, y_max = float(np.min(y_raw)), float(np.max(y_raw))
        x = (x_raw - 0.5 * (x_min + x_max)) / max(1e-6, 0.5 * (x_max - x_min))
        y = (y_raw - 0.5 * (y_min + y_max)) / max(1e-6, 0.5 * (y_max - y_min))

        # Multi-layer sine interference with per-layer seeded parameters.
        plasma = np.zeros_like(x)
        for layer in range(self._LAYERS):
            params = seeded_random(f"plasma-layer-{layer}", 4)
            freq = 2.0 + params[0] * 6.0
            angle = params[1] * 2.0 * np.pi
            phase_speed = 0.4 + params[2] * 1.6
            phase0 = params[3] * 2.0 * np.pi
            axis = x * np.cos(angle) + y * np.sin(angle)
            plasma += np.sin(freq * axis + phase0 + t * phase_speed)
        plasma = (plasma / self._LAYERS + 1.0) / 2.0
        plasma_intensity = plasma**3.0  # high contrast

        # Lightning: check the current and previous slots for an active bolt.
        bolt_intensity = np.zeros_like(x)
        slot = int(t / _SLOT_SECONDS)
        for candidate in (slot - 1, slot):
            if candidate < 0:
                continue
            bolt = _bolt_for_slot(candidate)
            if not bolt["active"]:
                continue
            rel = t - bolt["start"]
            if not 0.0 <= rel <= _BOLT_SECONDS:
                continue
            # Double-flash temporal envelope.
            envelope = np.exp(-rel * 12.0) + 0.7 * np.exp(-(((rel - 0.18) * 10.0) ** 2))
            dist = _polyline_distance(x, y, bolt["points"])
            bolt_intensity += envelope * np.exp(-dist / 0.05)
        bolt_intensity = np.clip(bolt_intensity, 0.0, 1.5)

        out = np.zeros((lights.shape[0], 3))
        out[:, 0] = np.clip(
            0.06 + 0.5 * plasma_intensity + 0.6 * bolt_intensity, 0, 0.98
        )
        out[:, 1] = np.clip(
            0.12 + 0.28 * plasma_intensity - 0.25 * np.minimum(bolt_intensity, 1.0),
            0.0,
            0.4,
        )
        out[:, 2] = (
            250.0 + 40.0 * plasma - 30.0 * np.minimum(bolt_intensity, 1.0)
        ) % 360.0
        return out

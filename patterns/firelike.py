"""Organic flowing contour shapes with slowly wandering warm colors."""

import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern
from luminary.patterns.util import seeded_random


def _rotate(x: np.ndarray, y: np.ndarray, ang: float) -> tuple:
    ca, sa = np.cos(ang), np.sin(ang)
    return x * ca - y * sa, x * sa + y * ca


def _sd_ellipse(x, y, cx, cy, rx, ry, ang=0.0):
    xp, yp = x - cx, y - cy
    ca, sa = np.cos(ang), np.sin(ang)
    xr = ca * xp + sa * yp
    yr = -sa * xp + ca * yp
    return np.sqrt((xr / (rx + 1e-6)) ** 2 + (yr / (ry + 1e-6)) ** 2) - 1.0


def _sd_circle(x, y, cx, cy, radius):
    return np.hypot(x - cx, y - cy) - radius


def _contour(sd, width):
    return np.exp(-np.abs(sd) / (width + 1e-6))


class FireLikePattern(Pattern):
    name = "firelike"
    description = "Organic flowing contour shapes with warm drifting colors"

    # Deterministic replacement for the old per-instance RNG (spec §9.1.3):
    # a fixed seeded base hue, plus a slow wander that is a function of t.
    _BASE_HUE = float(seeded_random("firelike-hue", 1)[0] * 360.0)

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        x_raw = lights[:, LightColumns.X]
        y_raw = lights[:, LightColumns.Y]
        x_min, x_max = float(np.min(x_raw)), float(np.max(x_raw))
        y_min, y_max = float(np.min(y_raw)), float(np.max(y_raw))
        x = (x_raw - 0.5 * (x_min + x_max)) / max(1e-6, 0.5 * (x_max - x_min))
        y = (y_raw - 0.5 * (y_min + y_max)) / max(1e-6, 0.5 * (y_max - y_min))

        x, y = _rotate(x, y, 0.12 * np.sin(t * 0.15))

        breath = 0.5 * (1.0 + np.sin(t * 2 * np.pi * 0.18))
        breath = 3 * breath**2 - 2 * breath**3
        line_w = 0.045 * (0.85 + 0.35 * breath)
        hue_drift = 6.0 * np.sin(t * 0.12)
        warm_pulse = 0.06 * np.sin(t * 0.08)
        hue_wander = 25.0 * np.sin(t * 0.045 + 2.0)  # replaces per-call rng

        slow, med, fast = t * 1.2, t * 2.1, t * 3.3
        sd_torso = _sd_ellipse(
            x,
            y,
            0.00 + 0.08 * np.sin(slow * 0.6),
            0.05 + 0.06 * np.cos(slow * 0.8),
            0.55,
            0.85,
            0.08,
        )
        sd_hip = _sd_ellipse(
            x,
            y,
            0.18 + 0.12 * np.sin(med * 0.5 + 1.0),
            -0.35 + 0.10 * np.cos(med * 0.7 + 0.5),
            0.62,
            0.42,
            -0.22,
        )
        sd_shoulder = _sd_ellipse(
            x,
            y,
            -0.35 + 0.15 * np.sin(fast * 0.4 + 2.1),
            0.35 + 0.08 * np.cos(fast * 0.9 + 1.3),
            0.36,
            0.26,
            0.30,
        )
        sd_thigh = _sd_ellipse(
            x,
            y,
            0.35 + 0.10 * np.sin(slow * 0.9 + 3.8),
            -0.65 + 0.14 * np.cos(slow * 0.3 + 2.7),
            0.70,
            0.36,
            -0.35,
        )
        sd_backarc = _sd_circle(
            x,
            y,
            -1.10 + 0.05 * np.sin(med * 0.2 + 4.2),
            0.15 + 0.07 * np.cos(med * 0.6 + 1.8),
            1.40,
        )

        line_int = (
            _contour(sd_torso, line_w)
            + _contour(sd_hip, line_w)
            + _contour(sd_shoulder, line_w)
            + _contour(sd_thigh, line_w * 1.15)
            + _contour(sd_backarc, line_w * 1.2)
        )

        fill_torso = np.clip(1.0 - np.maximum(0.0, sd_torso + 0.25) / 0.8, 0.0, 1.0)
        fill_hip = np.clip(1.0 - np.maximum(0.0, sd_hip + 0.20) / 0.7, 0.0, 1.0)
        fill_mix = np.clip(0.55 * fill_torso + 0.45 * fill_hip, 0.0, 1.0)

        noise = 0.06 * (
            np.sin(11.3 * x + 5.7 * y + 0.4 * t) * np.sin(7.1 * x - 9.2 * y - 0.33 * t)
        )

        lightness = 0.16 + 0.03 * (y + 1.0)
        lightness = lightness + 0.58 * np.clip(line_int, 0, 1) + 0.26 * fill_mix
        lightness = np.clip(lightness + 0.05 * breath + noise, 0.05, 0.92)

        chroma = 0.25 + 0.20 * fill_mix + 0.15 * np.clip(line_int, 0, 1)
        chroma = np.clip(chroma + warm_pulse + 0.03 * noise, 0.15, 0.45)

        hue = (
            self._BASE_HUE
            + hue_wander
            + hue_drift
            + 4.0 * x
            + 2.0 * y
            + 9.0 * np.clip(line_int, 0, 1)
        ) % 360.0

        out = np.zeros((lights.shape[0], 3))
        out[:, 0] = lightness
        out[:, 1] = chroma
        out[:, 2] = hue
        return out

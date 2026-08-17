"""Vespers: a slow color field for the end of the evening.

Medium notes: the restraint piece — no events, no objects, just one
continuous gradient between two OKLCH anchors that drift around the hue
wheel on multi-minute, mutually incommensurate periods (7 and ~11 min),
blended along an axis that itself rotates once every ~4.4 minutes.
Because OKLCH holds lightness steady while hue walks, every pairing the
drift produces stays luminous — this is the color space doing the
composing. A barely-there per-light breath (hashed sub-0.05 Hz phase)
keeps the field alive at the threshold of perception, and every minute
or so a slow swell of light crosses like a passing thought. Nearly
constant per-light velocity: the cheapest pattern on the wire, meant to
run all night.
"""

import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern
from luminary.patterns.util import seeded_random

_SWELL_SLOT = 60.0


def _smoothstep(v: np.ndarray, lo: float, hi: float) -> np.ndarray:
    u = np.clip((v - lo) / (hi - lo), 0.0, 1.0)
    out: np.ndarray = u * u * (3.0 - 2.0 * u)
    return out


class VespersPattern(Pattern):
    name = "vespers"
    description = "Two drifting color anchors, blended; a field to live with"

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n = lights.shape[0]
        x_raw = lights[:, LightColumns.X]
        y_raw = lights[:, LightColumns.Y]
        x_min, x_max = float(np.min(x_raw)), float(np.max(x_raw))
        y_min, y_max = float(np.min(y_raw)), float(np.max(y_raw))
        xn = (x_raw - 0.5 * (x_min + x_max)) / max(1e-6, 0.5 * (x_max - x_min))
        yn = (y_raw - 0.5 * (y_min + y_max)) / max(1e-6, 0.5 * (y_max - y_min))
        rn = np.clip(np.hypot(xn, yn), 0.0, 1.2)

        # Two hue anchors in slow, never-repeating orbits; kept a tasteful
        # arc apart so the between-space stays clean.
        hue_a = 360.0 * t / 419.0 + 30.0 * np.sin(2.0 * np.pi * t / 97.0)
        separation = 128.0 + 42.0 * np.sin(2.0 * np.pi * t / 151.0)

        # Blend axis rotates slowly; tanh keeps the middle wide and soft.
        psi = 2.0 * np.pi * t / 263.0
        s = xn * np.cos(psi) + yn * np.sin(psi)
        m = 0.5 + 0.5 * np.tanh(1.35 * s)

        # A passing thought: some minutes, a broad swell crosses over ~24 s.
        slot = int(t / _SWELL_SLOT)
        swell = np.zeros(n)
        sr = seeded_random(f"vespers-swell-{slot}", 3)
        if sr[0] < 0.7:
            begin = slot * _SWELL_SLOT + sr[1] * (_SWELL_SLOT - 26.0)
            u = (t - begin) / 24.0
            if 0.0 <= u <= 1.0:
                pos = -1.4 + 2.8 * u
                temporal = np.sin(np.pi * u)
                axis2 = psi + (sr[2] - 0.5) * 1.8
                s2 = xn * np.cos(axis2) + yn * np.sin(axis2)
                swell = 0.055 * temporal * np.exp(-((s2 - pos) ** 2) / (2.0 * 0.5**2))

        # Per-light breath: hashed phases, sub-perceptual amplitude.
        phase = seeded_random("vespers-breath", n)
        rate = 0.02 + 0.03 * seeded_random("vespers-rate", n)
        breath = 0.007 * np.sin(2.0 * np.pi * (rate * t + phase))

        # Blend the two anchors as OKLab (a, b) vectors: chroma relaxes
        # through the meeting zone, so the fields meet in pearl, not mud.
        c_anchor = 0.155 + 0.045 * np.sin(2.0 * np.pi * t / 173.0 + rn * 2.1)
        h_a = np.radians(hue_a)
        h_b = np.radians(hue_a + separation)
        a_ok = c_anchor * ((1.0 - m) * np.cos(h_a) + m * np.cos(h_b))
        b_ok = c_anchor * ((1.0 - m) * np.sin(h_a) + m * np.sin(h_b))

        out = np.zeros((n, 3))
        out[:, 0] = np.clip(
            0.16
            + 0.075 * (1.0 - rn**2)  # the heart holds a little more light
            + 0.012 * np.sin(2.0 * np.pi * t / 9.1 + rn * 2.3)
            + 1.3 * swell
            + breath,
            0.0,
            0.34,
        )
        out[:, 1] = np.clip(np.hypot(a_ok, b_ok) + 0.3 * swell, 0.03, 0.20)
        out[:, 2] = np.degrees(np.arctan2(b_ok, a_ok)) % 360.0
        return out

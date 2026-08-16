"""Emberfall: meteors of ember light ignite at the heart and ride the arms.

Medium notes: the pentagon's polar structure (R, THETA about the center
hole) makes the arms natural lanes — comets are born at the inner ring
and slide outward, a white-gold head cooling through amber into a long
deep-red tail. Spawning is slot-hashed (plasma_storm's technique): each
(lane, time-slot) pair deterministically decides whether it fires, so
any frame is recomputable in isolation. Comet widths are set in facet
units, not pixels — on this piece a body ~2 facets wide reads as a
flowing object instead of speckle. Sparse bright heads over a
near-black field is the wire codec's favorite meal.
"""

import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern
from luminary.patterns.util import seeded_random

_LANES = 14
_SLOT = 1.1  # seconds per spawn slot
_SPAWN_P = 0.16  # per lane per slot
_TAIL = 0.55  # tail length, normalized radius
_MAX_AGE = 4.8  # seconds a comet can live


def _smoothstep(v: np.ndarray, lo: float, hi: float) -> np.ndarray:
    u = np.clip((v - lo) / (hi - lo), 0.0, 1.0)
    out: np.ndarray = u * u * (3.0 - 2.0 * u)
    return out


def _comets_alive(t: float) -> tuple:
    """Arrays (angle, start, speed, sigma, flicker_phase) of live comets."""
    angles, starts, speeds, sigmas, phases = [], [], [], [], []
    first = max(0, int((t - _MAX_AGE) / _SLOT))
    last = int(t / _SLOT)
    for slot in range(first, last + 1):
        rand = seeded_random(f"ember-{slot}", _LANES * 5).reshape(_LANES, 5)
        for lane in range(_LANES):
            r0, r1, r2, r3, r4 = rand[lane]
            if r0 > _SPAWN_P:
                continue
            start = slot * _SLOT + r1 * _SLOT
            if not (0.0 <= t - start <= _MAX_AGE):
                continue
            angles.append((lane + 0.18 + 0.64 * r2) * 2.0 * np.pi / _LANES - np.pi)
            starts.append(start)
            speeds.append(0.20 + 0.20 * r3)
            sigmas.append(0.075 + 0.045 * r4)
            phases.append(r2 * 6.283)
    return (
        np.array(angles),
        np.array(starts),
        np.array(speeds),
        np.array(sigmas),
        np.array(phases),
    )


class EmberfallPattern(Pattern):
    name = "emberfall"
    description = "Ember meteors born at the heart, cooling down the arms"

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        x_raw = lights[:, LightColumns.X]
        y_raw = lights[:, LightColumns.Y]
        cx = 0.5 * (float(np.min(x_raw)) + float(np.max(x_raw)))
        cy = 0.5 * (float(np.min(y_raw)) + float(np.max(y_raw)))
        dx, dy = x_raw - cx, y_raw - cy
        rn = np.hypot(dx, dy)
        rn = rn / max(1e-6, float(np.max(rn)))
        th = np.arctan2(dy, dx)

        angle, start, speed, sigma, phase = _comets_alive(t)
        heat = np.zeros_like(rn)
        if angle.size:
            age = t - start[None, :]
            head = 0.17 + speed[None, :] * age
            behind = head - rn[:, None]
            # One fused exponent: tail decay behind the head, a tight
            # gaussian nose ahead of it, and the angular profile.
            radial_exp = np.where(
                behind >= 0.0, -behind / (_TAIL * 0.38), -(behind**2) / 0.0016
            )
            dth = (th[:, None] - angle[None, :] + np.pi) % (2.0 * np.pi) - np.pi
            profile = np.exp(radial_exp - (dth**2) / (2.0 * sigma[None, :] ** 2))
            # Gutter out as the head leaves the piece; shimmer gently.
            dying = np.clip((1.22 - head) / 0.16, 0.0, 1.0)
            shimmer = 1.0 + 0.09 * np.sin(2.0 * np.pi * 2.7 * age + phase[None, :])
            # Heads burn hotter than tails linger.
            hot = 1.0 + 0.45 * np.exp(-(behind**2) / 0.004)
            heat = np.sum(profile * dying * shimmer * hot, axis=1)
        heat = np.clip(heat, 0.0, 1.45)

        # The hearth: a coal-glow ring where comets are born.
        pulse = 0.5 + 0.5 * np.sin(2.0 * np.pi * t / 6.7)
        hearth = np.exp(-((rn - 0.16) ** 2) / 0.006) * (0.14 + 0.10 * pulse)

        q = np.clip(heat + hearth, 0.0, 1.45)
        out = np.zeros((lights.shape[0], 3))
        out[:, 0] = np.clip(0.040 + 0.72 * (q / 1.45) ** 0.8, 0.0, 0.93)
        # Cooling ramp: deep red tail -> amber -> white-gold head.
        out[:, 1] = np.clip(
            0.055
            + 0.30
            * _smoothstep(q, 0.03, 0.45)
            * (1.0 - 0.6 * _smoothstep(q, 0.95, 1.40)),
            0.0,
            0.33,
        )
        base_h = 262.0  # near-black indigo field
        ember_h = 18.0 + 68.0 * np.clip(q / 1.1, 0.0, 1.0) ** 0.65
        blend = _smoothstep(q, 0.015, 0.16)
        out[:, 2] = (base_h + ((ember_h - base_h) % 360.0) * blend) % 360.0
        return out

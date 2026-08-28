"""Fireflies: a dark meadow that slowly learns to flash in unison.

A few dozen fireflies wander the sphere on slow closed-form paths,
each blinking on its own clock — until, every ``sync_period`` seconds,
the meadow gathers itself: flash times pull toward a shared metronome
(the Photinus carolinus trick), hold a spell of near-unison waves, and
dissolve back into scattered sparks. The synchrony is not simulated —
each slot's flash offset is a deterministic lerp between that fly's
hashed jitter and the metronome, weighted by a coherence curve
evaluated at the slot's start, so any frame at any ``t`` reconstructs
the same meadow (spec §9.1.3).

Medium notes: single-fly flashes are facet-scale pools with ≥100 ms
attacks and long decays (no strobe); everything else stays a
near-black green-indigo floor, so a flash reads as an event. The
palette is one warm-green family walked in OKLCH — flies whiten
slightly at peak, exactly like the real insect's cold light.
"""

from __future__ import annotations

import numpy as np

from luminary.patterns.easing import env_ad
from luminary.patterns.fields import value_noise
from luminary.patterns.primitives import Primitive
from luminary.patterns.util import phi_theta, plane_xy, seeded_random


class Fireflies(Primitive):
    name = "fireflies"
    description = "Wandering fireflies that drift into unison and out again"

    count = 48
    interval_s = 5.2  # one flash opportunity per fly per interval
    rate = 0.8  # chance a fly takes a given opportunity
    sync_period = 300.0  # chaos -> unison -> chaos, every five minutes
    flash_attack = 0.10
    flash_decay = 0.18
    spot_deg = 5.0  # angular radius of one fly's pool of light
    wander_deg = 13.0  # how far a fly drifts from home
    meadow_l = 0.032
    salt = "fireflies"

    def _coherence(self, t: float) -> float:
        """0 = every fly on its own clock, 1 = the meadow in unison."""
        swell = 0.5 - 0.5 * np.cos(2.0 * np.pi * t / self.sync_period)
        return float(np.clip(1.6 * swell - 0.35, 0.0, 1.0))

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n = lights.shape[0]
        k = self.count

        # Per-fly constants: homes in the mid band, wander clocks.
        th0 = seeded_random(f"{self.salt}-th", k) * 2.0 * np.pi - np.pi
        ph0 = 0.55 + 1.35 * seeded_random(f"{self.salt}-ph", k)
        p1 = 37.0 + 34.0 * seeded_random(f"{self.salt}-p1", k)
        p2 = 53.0 + 44.0 * seeded_random(f"{self.salt}-p2", k)
        a1 = seeded_random(f"{self.salt}-a1", k) * 2.0 * np.pi
        a2 = seeded_random(f"{self.salt}-a2", k) * 2.0 * np.pi

        w = np.radians(self.wander_deg)
        th_f = th0 + w * np.sin(2.0 * np.pi * t / p1 + a1)
        ph_f = np.clip(ph0 + 0.6 * w * np.sin(2.0 * np.pi * t / p2 + a2), 0.15, 2.1)

        # Flash envelopes from this slot and the previous one (a flash
        # never outlives two slots). Offsets lerp toward the metronome
        # (0.25 of the interval) as coherence rises; a whisper of jitter
        # survives even full unison, like the real thing.
        interval = self.interval_s
        slot = int(np.floor(t / interval))
        env = np.zeros(k)
        for s in (slot - 1, slot):
            c = self._coherence(s * interval)
            jit = seeded_random(f"{self.salt}-j-{s}", k)
            fires = seeded_random(f"{self.salt}-f-{s}", k) < self.rate
            offset = 0.25 * c + jit * (0.85 * (1.0 - c) + 0.06 * c)
            start = (s + offset) * interval
            env = env + fires * env_ad(t - start, self.flash_attack, self.flash_decay)

        # Meadow floor: near-black grass with the faintest drifting sheen.
        u, v = plane_xy(lights)
        sheen = value_noise(u * 1.8 + 0.006 * t, v * 1.8, seed=31)
        out = np.empty((n, 3))
        out[:, 0] = self.meadow_l * (0.85 + 0.30 * sheen)
        out[:, 1] = 0.045
        out[:, 2] = 132.0

        # Light only the flies that are actually glowing.
        lit = env > 1e-4
        if np.any(lit):
            phi, th = phi_theta(lights)
            sin_phi = np.sin(phi)
            nl = np.column_stack(
                [sin_phi * np.cos(th), sin_phi * np.sin(th), np.cos(phi)]
            )
            sf = np.sin(ph_f[lit])
            fl = np.column_stack(
                [sf * np.cos(th_f[lit]), sf * np.sin(th_f[lit]), np.cos(ph_f[lit])]
            )
            sigma = np.radians(self.spot_deg)
            # angle² ≈ 2·(1 − cosθ) inside a small pool: no arccos needed.
            spot = np.exp((nl @ fl.T - 1.0) / (sigma**2))
            glow = np.minimum(spot @ env[lit], 1.25) / 1.25

            out[:, 0] += (0.68 - out[:, 0]) * glow**0.9
            out[:, 1] = 0.045 + 0.115 * glow
            out[:, 2] = 132.0 - 18.0 * glow  # grass green toward firefly gold-green
        return out

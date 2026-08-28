"""Spiegel: for Arvo Pärt's *Spiegel im Spiegel*.

Timed to the Minkler–Johnson recording (viola and piano, 11:55) —
name the file ``spiegel-im-spiegel.mp3`` in ``var/audio`` and the
stage pairs them.

Mirror in mirror: the whole render is symmetric across the sphere's
own mirror plane (azimuth negated, the geometry's x = 0 symmetry from
the craft notes). The viola is a single narrow band of pale light
that climbs the sphere over one phrase and descends the next — every
ascent answered by its reflection. The piano is three soft bells
climbing the mirror meridian itself, low-middle-high like the rising
triad, rocking forever. Nothing develops; everything reflects.
"""

import numpy as np

from luminary.patterns.easing import env_ad, smoothstep
from luminary.patterns.primitives import Primitive
from luminary.patterns.util import phi_theta


class Spiegel(Primitive):
    name = "spiegel"
    description = "Mirror in mirror: a climbing line and three bells (11:55)"
    audio = "spiegel-im-spiegel.mp3"
    duration = 715.0  # the Minkler–Johnson recording
    notes = (
        "A line of pale light climbs the sphere over one phrase and comes "
        "down the next, answered always by its own reflection; three soft "
        "bells climb the mirror line underneath, low, middle, high. Nothing "
        "develops; everything reflects. The stillest music there is — let "
        "the room get quiet enough to hear the lights."
    )

    phrase_s = 22.0  # one full climb (or descent) of the viola line
    line_l = 0.45
    line_sigma_deg = 5.0
    bar_s = 6.0  # the piano's rocking cycle: three bells per bar
    bell_l = 0.30
    bell_sigma_deg = 6.5
    floor_l = 0.022
    hue = 86.0  # F-major white-gold
    chroma = 0.04

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n = lights.shape[0]
        phi, th = phi_theta(lights)
        span = float(np.max(phi)) or 1.0

        # The viola: a band that climbs on even phrases, descends on odd
        # — azimuth-independent, so mirror symmetry is exact.
        p = int(np.floor(t / self.phrase_s))
        u = float(smoothstep(0.0, 1.0, (t - p * self.phrase_s) / self.phrase_s))
        top, bottom = 0.16 * span, 0.88 * span
        center = bottom - (bottom - top) * u if p % 2 == 0 else top + (bottom - top) * u
        sigma = np.radians(self.line_sigma_deg)
        line = np.exp(-((phi - center) ** 2) / (2.0 * sigma**2)) * self.line_l

        # The piano: three bells ON the mirror meridian itself (azimuths
        # 0° and 180° — every light's reflection sees exactly what it
        # sees), placed low, middle, high like the rising triad, one
        # ringing per third of the bar, forever.
        sin_phi = np.sin(phi)
        nl = np.column_stack([sin_phi * np.cos(th), sin_phi * np.sin(th), np.cos(phi)])
        bsig = np.radians(self.bell_sigma_deg)
        t_in = t % self.bar_s
        bells = np.zeros(n)
        for i, (az_deg, phi_frac) in enumerate(
            ((0.0, 0.85), (180.0, 0.62), (0.0, 0.38))
        ):
            az = np.radians(az_deg)
            bell_phi = phi_frac * span
            axis = np.array(
                [
                    np.sin(bell_phi) * np.cos(az),
                    np.sin(bell_phi) * np.sin(az),
                    np.cos(bell_phi),
                ]
            )
            pool = np.exp((nl @ axis - 1.0) / (bsig**2))
            dt = t_in - i * (self.bar_s / 3.0)
            if dt < 0.0:
                dt += self.bar_s
            bells = np.maximum(bells, pool * float(env_ad(dt, 0.15, 1.1)) * self.bell_l)

        level = np.maximum(line, bells)
        out = np.empty((n, 3))
        out[:, 0] = self.floor_l + level
        out[:, 1] = self.chroma * np.clip(level / self.line_l, 0.0, 1.0) + 0.012
        out[:, 2] = self.hue
        return out

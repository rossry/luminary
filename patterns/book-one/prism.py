"""Prism: the facets catch two wandering lights and split them.

Medium notes: this pattern is written against the *mesostructure*. Every
light carries its beam's throw direction (DX/DY — the fan geometry of
the physical piece), and brightness comes from how nearly that direction
faces a slowly orbiting virtual illuminant: a specular glint, raised to
a high power. Because beams within a facet fan share direction, whole
facets flare together and the sweep crawls across the piece facet by
facet — the pattern makes the construction visible in a way no (x, y)
field can. Near alignment, hue is dispersed across the glint like light
through glass. A counter-orbiting rose light answers the gold one.
"""

import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern
from luminary.patterns.util import seeded_random


def _smoothstep(v: np.ndarray, lo: float, hi: float) -> np.ndarray:
    u = np.clip((v - lo) / (hi - lo), 0.0, 1.0)
    out: np.ndarray = u * u * (3.0 - 2.0 * u)
    return out


class PrismPattern(Pattern):
    name = "prism"
    description = "Facet glints from two counter-orbiting lights, dispersed"

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n = lights.shape[0]
        dx = np.nan_to_num(lights[:, LightColumns.DX], nan=0.0)
        dy = np.nan_to_num(lights[:, LightColumns.DY], nan=0.0)
        norm = np.hypot(dx, dy)
        # Fallback for geometries without throw directions: radial.
        x_raw = lights[:, LightColumns.X]
        y_raw = lights[:, LightColumns.Y]
        cx = 0.5 * (float(np.min(x_raw)) + float(np.max(x_raw)))
        cy = 0.5 * (float(np.min(y_raw)) + float(np.max(y_raw)))
        rad = np.hypot(x_raw - cx, y_raw - cy)
        ok = norm > 1e-9
        ux = np.where(
            ok, dx / np.maximum(norm, 1e-9), (x_raw - cx) / np.maximum(rad, 1e-9)
        )
        uy = np.where(
            ok, dy / np.maximum(norm, 1e-9), (y_raw - cy) / np.maximum(rad, 1e-9)
        )

        # Hashed micro-tilt so facets are cut, not machined.
        jitter = (seeded_random("prism-tilt", n) - 0.5) * np.radians(3.0)
        cj, sj = np.cos(jitter), np.sin(jitter)
        ux, uy = ux * cj - uy * sj, ux * sj + uy * cj
        beam_angle = np.arctan2(uy, ux)

        # Two illuminants: gold wanders forward, rose orbits against it.
        phi_a = 2.0 * np.pi * t / 47.0 + 0.9 * np.sin(2.0 * np.pi * t / 13.7)
        phi_b = -2.0 * np.pi * t / 61.0 + 2.4 + 0.6 * np.sin(2.0 * np.pi * t / 17.3)

        def glint(phi: float, power: float) -> tuple:
            d = (beam_angle - phi + np.pi) % (2.0 * np.pi) - np.pi
            facing = np.clip(np.cos(d), 0.0, 1.0)
            return facing**power, d

        # A slow sheet of light travels across the piece in the illuminant's
        # direction, so glints ripple spatially instead of flashing globally.
        span = max(1e-6, float(np.max(rad)))
        sx, sy = (x_raw - cx) / span, (y_raw - cy) / span
        along_a = sx * np.cos(phi_a) + sy * np.sin(phi_a)
        along_b = sx * np.cos(phi_b) + sy * np.sin(phi_b)
        sweep_a = 0.45 + 0.55 * (
            0.5 + 0.5 * np.cos(along_a * 2.4 - 2.0 * np.pi * t / 11.0)
        )
        sweep_b = 0.45 + 0.55 * (
            0.5 + 0.5 * np.cos(along_b * 2.4 + 2.0 * np.pi * t / 14.3)
        )

        # Slow swells trade dominance between the two lights.
        env_a = 0.62 + 0.38 * np.sin(2.0 * np.pi * t / 29.0)
        env_b = 0.62 + 0.38 * np.sin(2.0 * np.pi * t / 37.0 + 1.1)
        ga, da = glint(phi_a, 40.0)
        gb, db = glint(phi_b, 30.0)
        ga = ga * env_a * sweep_a
        gb = gb * env_b * sweep_b

        # Broad low fill so unlit facets keep their crystal-steel form.
        fill = 0.16 * (0.5 + 0.5 * np.cos(beam_angle - phi_a)) ** 2 + 0.045

        out = np.zeros((n, 3))
        out[:, 0] = np.clip(0.03 + 0.72 * ga + 0.50 * gb + fill, 0.0, 0.92)
        out[:, 1] = np.clip(
            0.05
            + 0.15 * _smoothstep(ga, 0.04, 0.6)
            + 0.14 * _smoothstep(gb, 0.04, 0.6)
            - 0.09 * _smoothstep(ga + gb, 0.9, 1.4),
            0.0,
            0.22,
        )
        # Dispersion: within a glint, hue shifts with the signed angle to
        # the illuminant — a narrow refracted fringe, not a full rainbow.
        base_h = 252.0  # cold steel field
        gold_h = 82.0 + 30.0 * np.clip(da / 0.35, -1.0, 1.0)
        rose_h = 352.0 + 24.0 * np.clip(db / 0.4, -1.0, 1.0)
        # Hue engages later than luminance: dim facets stay steel, only
        # true glints take color.
        wa = _smoothstep(ga, 0.10, 0.45)
        wb = _smoothstep(gb, 0.10, 0.45) * (1.0 - wa)
        hue = base_h + ((gold_h - base_h + 540.0) % 360.0 - 180.0) * wa
        hue = hue + ((rose_h - hue + 540.0) % 360.0 - 180.0) * wb
        out[:, 2] = hue % 360.0
        return out

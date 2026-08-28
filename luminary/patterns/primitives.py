"""Parametrized primitives: the shared vocabulary shows are built from.

A :class:`Primitive` is a Pattern whose knobs are declared as class
attributes — the class body *is* the parameter schema. Constructing one
with keyword overrides re-tunes it without subclassing; subclassing
with new class-attribute values re-tunes it durably (that is how thin
registration files in ``patterns/`` publish a tuned voice, and why the
registry's no-argument instantiation always works — every parameter has
a default).

Everything here obeys the pattern contract (spec §9.1): stateless,
vectorized, pure in ``(lights, t)``. Primitives live in the importable
library — ``patterns/`` files may import and compose them, but field
math stays here, written once (invariant §2.9).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np

from luminary.patterns.base import Pattern
from luminary.patterns.easing import breath, smoothstep
from luminary.patterns.fields import fbm, ring_field, value_noise, warp
from luminary.patterns.palettes import AURORA, SEA_GLASS, Palette, blend_oklch
from luminary.patterns.util import phi_theta, plane_xy, seeded_random

_RESERVED = frozenset({"name", "description"})


class Primitive(Pattern):
    """A Pattern with declared, overridable parameters.

    Parameters are the plain class attributes of the concrete class
    (anything public and non-callable that is not ``name`` or
    ``description``). ``__init__(**overrides)`` accepts only those
    names, so a typo fails loudly instead of silently styling nothing.
    """

    def __init__(self, **params: Any) -> None:
        known = self.params()
        for key, value in params.items():
            if key not in known:
                raise TypeError(
                    f"{type(self).__name__} has no parameter {key!r}; "
                    f"parameters: {', '.join(sorted(known))}"
                )
            setattr(self, key, value)

    @classmethod
    def params(cls) -> Dict[str, Any]:
        """Parameter defaults for this class, base-to-derived."""
        out: Dict[str, Any] = {}
        for klass in reversed(cls.__mro__):
            if klass is Primitive or not issubclass(klass, Primitive):
                continue
            for key, value in vars(klass).items():
                if key.startswith("_") or key in _RESERVED:
                    continue
                if callable(value) or isinstance(value, (property, classmethod)):
                    continue
                out[key] = value
        return out

    def param_values(self) -> Dict[str, Any]:
        """Current values (defaults merged with instance overrides)."""
        return {key: getattr(self, key) for key in self.params()}

    def info(self) -> Dict[str, Any]:
        base = super().info()
        base["params"] = {
            key: value if isinstance(value, (bool, int, float, str)) else repr(value)
            for key, value in self.param_values().items()
        }
        return base


class Starfield(Primitive):
    name = "starfield"
    description = "Sparse stars twinkling over a near-black airglow sky"

    density = 0.035  # fraction of lights that are stars
    twinkle_s = 6.0  # typical twinkle period (per-star jitter around it)
    star_l = 0.60  # peak star luminance
    star_hue = 78.0  # warm starlight
    sky_l = 0.030  # sky luminance floor (a few wire-LSBs above black)
    sky_hue = 262.0
    airglow = 0.35  # 0..1: sky floor swell from slow drifting noise
    salt = "starfield"  # same salt -> the same stars, across movements

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n = lights.shape[0]
        pick = seeded_random(f"{self.salt}-pick", n)
        phase = seeded_random(f"{self.salt}-phase", n)
        rate = 0.6 + 0.9 * seeded_random(f"{self.salt}-rate", n)
        is_star = pick < self.density
        twinkle = 0.5 - 0.5 * np.cos(2.0 * np.pi * (t * rate / self.twinkle_s + phase))

        u, v = plane_xy(lights)
        glow = value_noise(u * 1.5 + 0.008 * t, v * 1.5 - 0.005 * t, seed=11)
        sky_level = self.sky_l * (1.0 + self.airglow * (glow - 0.5))

        sky = np.column_stack([sky_level, np.full(n, 0.035), np.full(n, self.sky_hue)])
        star = np.column_stack(
            [np.full(n, self.star_l), np.full(n, 0.045), np.full(n, self.star_hue)]
        )
        weight = np.where(is_star, twinkle**2, 0.0)
        return blend_oklch(sky, star, weight)


class NoiseGlow(Primitive):
    name = "noiseglow"
    description = "Domain-warped fractal noise drifting through a palette"

    palette = SEA_GLASS
    scale = 2.2  # feature count across the layout
    speed = 0.030  # drift, feature-units per second
    warp_amount = 1.2  # how alive vs. procedural the field looks
    octaves = 3  # 4th-octave detail is sub-facet at this scale: speckle
    contrast = 1.5  # >1 deepens the darks between banks
    breathe_s = 33.0  # slow global swell period (0 disables)
    breathe_depth = 0.12
    seed = 7

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        u, v = plane_xy(lights)
        uu = u * self.scale + t * self.speed
        vv = v * self.scale - t * self.speed * 0.71
        wu, wv = warp(uu, vv, self.seed, self.warp_amount, octaves=2)
        field = fbm(wu, wv, self.seed + 10, octaves=self.octaves)
        field = np.clip(field, 0.0, 1.0) ** self.contrast
        if self.breathe_s > 0.0:
            swell = breath(t, self.breathe_s)
            field = field * (1.0 - self.breathe_depth + self.breathe_depth * swell)
        return self.palette.sample(field)


class AuroraVeils(Primitive):
    name = "auroraveils"
    description = "Auroral curtains draped from the apex, keyed by a palette"

    palette = AURORA
    speed = 1.0  # multiplier on every drift clock
    sheets = 3  # curtain harmonics (azimuthal wavenumbers 2, 3, ...)
    border = 0.60  # lower-border elevation, fraction of the phi span
    tall = 0.55  # fade height above the border
    shimmer = 0.13
    floor = 0.04  # palette position of the empty sky
    salt = "veils"

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        phi, th = phi_theta(lights)
        span = float(np.max(phi)) or 1.0
        h = 1.0 - phi / span  # 1 at the apex, 0 at the rim
        s = self.speed

        curtain = np.zeros_like(h)
        norm = 0.0
        for k in range(self.sheets):
            r3 = seeded_random(f"{self.salt}-sheet-{k}", 3)
            m = k + 2  # integer harmonics keep azimuth wrap-safe
            sway = (0.35 + 0.40 * r3[0]) * np.sin(
                (m + 1) * th + t * s * (0.05 + 0.12 * r3[1]) + k * 2.1
            )
            drift = s * (0.010 + 0.030 * r3[2]) * (1.0 if k % 2 == 0 else -1.0)
            ridge = 0.5 + 0.5 * np.cos(m * th + sway + 2.0 * np.pi * drift * t)
            weight = 1.0 / (1.0 + 0.6 * k)
            curtain += weight * ridge**3
            norm += weight
        curtain = curtain / norm + 0.08  # faint airglow between curtains

        border_line = (
            self.border
            + 0.06 * np.sin(2.0 * th + t * s * 0.11)
            + 0.03 * np.sin(t * s * 0.043)
        )
        above = h - border_line
        vertical = smoothstep(-0.03, 0.07, above) * np.exp(
            -np.maximum(above, 0.0) / self.tall
        )
        ripple = 1.0 + self.shimmer * np.sin(
            17.0 * th - t * s * 2.1 + 3.0 * np.sin(7.0 * th + t * s * 0.53)
        )

        intensity = np.clip(curtain * vertical * ripple, 0.0, 1.0)
        fringe = smoothstep(0.10, 0.55, above)  # how far up the ray we are
        position = np.clip(intensity * (0.50 + 0.50 * fringe), 0.0, 1.0)
        position = self.floor + (1.0 - self.floor) * position
        return self.palette.sample(position)


class RingWave(Primitive):
    name = "ringwave"
    description = "A luminous ring sweeping apex to rim, re-keyed each pass"

    period = 11.0
    descent_deg = 130.0
    sigma_deg = 7.0
    palette: Optional[Palette] = None  # set -> palette(intensity); None -> spectral
    l_gain = 0.72  # spectral mode: crest luminance
    chroma = 0.13  # spectral mode: crest chroma
    ring_floor = 0.018  # luminance floor so the sphere never fully blacks out
    spin_salt = "ringwave"

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        phi, th = phi_theta(lights)
        az = np.degrees(th) % 360.0
        intensity, hue = ring_field(
            phi, az, t, self.period, self.spin_salt, self.descent_deg, self.sigma_deg
        )
        if self.palette is not None:
            out = self.palette.sample(np.clip(intensity, 0.0, 1.0))
            out[:, 0] = np.maximum(out[:, 0], self.ring_floor)
            return out
        n = lights.shape[0]
        out = np.empty((n, 3))
        out[:, 0] = self.ring_floor + (self.l_gain - self.ring_floor) * intensity
        out[:, 1] = self.chroma * np.sqrt(intensity)
        out[:, 2] = hue
        return out

"""Small Planet: the sphere as a tiny living world.

Seeded continents in a quiet ocean, cloud banks drifting over them, and
a sun that actually orbits: the lit hemisphere carries the day, a warm
terminator ring walks the globe every ``day_s`` seconds, and the night
side goes near-black except for city lights on the land, an auroral
cap at the apex, and a small moon whose brightness follows its true
phase (full when opposite the sun). A gentle seasonal tilt keeps no
two days identical.

Medium notes: the planet reads at facet scale — continents and cloud
banks are multi-facet features, the terminator band is ~2 facets wide,
cities are single lights. Every mix happens in the OKLab vector plane
(the ``blend_oklch`` semantics — layers are composed as vec lerps and
converted once at the end, so six stacked blends cost one conversion),
which lets dusk desaturate into shadow instead of graying into mud.
All motion is minutes-slow; the fastest thing on the planet is a city
shimmering.

Statelessness: the sun, moon, season, clouds, and twinkles are closed
forms in ``t``; continents, land texture, the composed surface colors,
and city placement depend only on the geometry, memoized on a content
fingerprint of the lights array (the cache is fully determined by its
key — same idiom as ``conifer/pacman.py``).
"""

from __future__ import annotations

import zlib
from typing import Any, Dict, Tuple

import numpy as np

from luminary.patterns.fields import fbm, value_noise
from luminary.patterns.palettes import AURORA, oklch_to_vec, vec_to_oklch
from luminary.patterns.primitives import AuroraVeils, Primitive
from luminary.patterns.util import phi_theta, seeded_random


def _vec3(l: float, c: float, h: float) -> np.ndarray:
    """One OKLCH color as its OKLab blend vector [L, C·cosH, C·sinH]."""
    hr = np.radians(h)
    return np.array([l, c * np.cos(hr), c * np.sin(hr)])


class SmallPlanet(Primitive):
    name = "small_planet"
    description = "A living miniature world: sun, seasons, cities, aurora, moon"

    day_s = 600.0  # one full day-night cycle, seconds
    year_s = 47 * 600.0  # seasonal tilt period (incommensurate with the day)
    tilt_deg = 12.0  # solar elevation swing over the year
    sea_level = 0.53  # continent threshold in the noise field
    continent_scale = 1.7  # continents per hemisphere-ish
    cloud_scale = 2.6
    cloud_cover = 0.58  # lower = cloudier
    city_density = 0.06  # fraction of land lights that are cities
    moon_s = 7020.0  # lunar orbit period (11.7 days)
    moon_deg = 7.0  # angular radius of the moonlight pool
    aurora = AuroraVeils(palette=AURORA.dimmed(0.85), speed=0.7, sheets=2, border=0.72)
    cap_lo_deg = 22.0  # aurora cap: full strength above this polar angle...
    cap_hi_deg = 38.0  # ...gone below this one
    seed = 4001
    salt = "small-planet"

    # Geometry-derived statics, memoized by lights-content fingerprint
    # plus every parameter that shapes them (a pure function of its key —
    # not state; differently-tuned instances never share an entry).
    _statics_cache: Dict[Tuple[Any, ...], Tuple[np.ndarray, ...]] = {}

    def _statics(self, lights: np.ndarray) -> Tuple[np.ndarray, ...]:
        phi, th = phi_theta(lights)
        key = (
            zlib.crc32(phi.tobytes()) ^ zlib.crc32(th.tobytes()),
            lights.shape[0],
            self.seed,
            self.salt,
            self.continent_scale,
            self.sea_level,
            self.city_density,
        )
        hit = self._statics_cache.get(key)
        if hit is not None:
            return hit
        sin_phi = np.sin(phi)
        nx = sin_phi * np.cos(th)
        ny = sin_phi * np.sin(th)
        nz = np.cos(phi)
        # Seam-free noise coordinates: built from the unit vector, with a
        # z term to break the phi mirror-symmetry of (nx, ny) alone.
        cs = self.continent_scale
        u1 = nx * cs + 3.1 * nz
        v1 = ny * cs - 2.7 * nz
        cont = fbm(u1, v1, self.seed, octaves=3)
        land = np.clip((cont - self.sea_level) / 0.05, 0.0, 1.0)  # soft coast
        land_tex = value_noise(u1 * 2.3 + 9.0, v1 * 2.3 - 4.0, self.seed + 5)
        n = lights.shape[0]

        # The daylit surface never changes: compose ocean and land (soft
        # coastlines via the lerp) once, in vec space.
        depth = np.clip(1.0 - cont / self.sea_level, 0.0, 1.0)
        ocean = np.empty((n, 3))
        ocean[:, 0] = 0.30 + 0.10 * depth
        ocean[:, 1] = 0.085 * np.cos(np.radians(248.0))
        ocean[:, 2] = 0.085 * np.sin(np.radians(248.0))
        land_h = np.radians(145.0 - 55.0 * land_tex)  # forest green into steppe tan
        landc = np.empty((n, 3))
        landc[:, 0] = 0.40 + 0.10 * land_tex
        landc[:, 1] = 0.095 * np.cos(land_h)
        landc[:, 2] = 0.095 * np.sin(land_h)
        surface = ocean + (landc - ocean) * land[:, None]

        city_pick = seeded_random(f"{self.salt}-cities", n)
        city_phase = seeded_random(f"{self.salt}-cityphase", n)
        # Cities cluster on land (and a few harbors glow offshore).
        is_city = city_pick < self.city_density * (0.12 + 0.88 * land)
        value = (phi, nx, ny, nz, surface, is_city, city_phase)
        if len(self._statics_cache) > 8:  # a process sees a couple of geometries
            self._statics_cache.clear()
        self._statics_cache[key] = value
        return value

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        phi, nx, ny, nz, surface, is_city, city_phase = self._statics(lights)

        # --- the sun (and with it, the day) --------------------------------
        alpha = 2.0 * np.pi * t / self.day_s
        decl = np.radians(self.tilt_deg) * np.sin(2.0 * np.pi * t / self.year_s)
        sx, sy, sz = (
            np.cos(decl) * np.cos(alpha),
            np.cos(decl) * np.sin(alpha),
            np.sin(decl),
        )
        insol = nx * sx + ny * sy + nz * sz
        day = np.clip((insol + 0.06) / 0.26, 0.0, 1.0)
        day = day * day * (3.0 - 2.0 * day)  # smoothstep(-0.06, 0.20)

        # --- clouds over the surface ---------------------------------------
        cloud = fbm(
            nx * self.cloud_scale + 0.011 * t + 5.0 * nz,
            ny * self.cloud_scale + 0.007 * t - 4.4 * nz,
            self.seed + 20,
            octaves=3,
        )
        cm = np.clip((cloud - self.cloud_cover) / 0.17, 0.0, 1.0)
        cm = cm * cm * (3.0 - 2.0 * cm)
        day_vec = surface + (_vec3(0.82, 0.02, 255.0) - surface) * (0.9 * cm)[:, None]

        # --- night falls ----------------------------------------------------
        night = _vec3(0.028, 0.02, 262.0)
        out = night + (day_vec - night) * day[:, None]

        # Terminator ring: a warm band where the sun is on the horizon.
        glow = (0.55 * np.exp(-((insol / 0.085) ** 2)))[:, None]
        out += (_vec3(0.55, 0.14, 45.0) - out) * glow

        # City lights: on the dark side, under clear skies, gently alive.
        twinkle = 0.85 + 0.15 * np.sin(2.0 * np.pi * (t / 7.3 + city_phase))
        city_w = np.where(is_city, (1.0 - day) * (1.0 - 0.85 * cm) * twinkle, 0.0)
        out += (_vec3(0.50, 0.11, 70.0) - out) * city_w[:, None]

        # Aurora cap at the apex, night-side (composed from the shared
        # primitive — rendered only when the cap is actually dark).
        cap_lo, cap_hi = np.radians(self.cap_lo_deg), np.radians(self.cap_hi_deg)
        cap = 1.0 - np.clip((phi - cap_lo) / (cap_hi - cap_lo), 0.0, 1.0)
        cap_w = 0.8 * cap * (1.0 - day)
        if float(np.max(cap_w)) > 1e-3:
            aurora_vec = oklch_to_vec(self.aurora.render(lights, t))
            out += (aurora_vec - out) * cap_w[:, None]

        # The moon: a slow pool of light whose brightness is its phase.
        beta = 2.0 * np.pi * t / self.moon_s + 2.1
        mx, my, mz = np.cos(beta) * 0.99, np.sin(beta) * 0.99, 0.14
        cos_moon = np.clip(nx * mx + ny * my + nz * mz, -1.0, 1.0)
        # angle² ≈ 2·(1 − cosθ): exact enough inside a 7° pool, no arccos.
        sigma = np.radians(self.moon_deg)
        spot = np.exp(-(1.0 - cos_moon) / (sigma**2))
        phase = 0.5 * (1.0 - (mx * sx + my * sy + mz * sz))  # full opposite the sun
        moon_w = (0.75 * spot * phase * (1.0 - day))[:, None]
        out += (_vec3(0.72, 0.03, 95.0) - out) * moon_w

        result: np.ndarray = vec_to_oklch(out)
        return result

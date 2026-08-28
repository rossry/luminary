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
from luminary.patterns.palettes import (
    AURORA,
    CANDLE,
    EMBER,
    SEA_GLASS,
    Palette,
    blend_oklch,
)
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


def _arc(t: float, arc_s: float, a: float, b: float) -> float:
    """Smoothstepped progress a -> b over ``arc_s`` seconds of local time.

    The dramaturgy helper: a movement hands its pattern movement-local
    t, so ``arc_s`` set to the movement's duration makes the parameter
    complete its journey exactly over the movement — the pattern is
    always coming from somewhere or going somewhere, and the arc says
    which. ``arc_s <= 0`` disables (returns ``a``: flat).
    """
    if arc_s <= 0.0:
        return a
    u = min(max(t / arc_s, 0.0), 1.0)
    u = u * u * (3.0 - 2.0 * u)
    return a + (b - a) * u


class Starfield(Primitive):
    name = "starfield"
    description = "A sky that is a population: stars arrive, hold, and let go"

    density = 0.035  # fraction of lights that can be stars, at full sky
    twinkle_s = 6.0  # typical twinkle period (per-star jitter around it)
    star_l = 0.60  # peak star luminance (a point figure: may sit well
    # above a full field's duty-cycle lane)
    star_hue = 78.0  # warm starlight
    sky_l = 0.030  # sky luminance floor (a few wire-LSBs above black)
    sky_hue = 262.0
    airglow = 0.35  # 0..1: sky floor swell from slow drifting noise
    # The population arc: sky fullness runs fill_from -> fill_to over
    # arc_s seconds of local time. Stars are ranked by seniority (their
    # hash): as the sky swells, stars ADD without churn; as it fades,
    # the latest arrivals leave first and the deepest hold longest —
    # some stars stay, and the fullness of the sky goes somewhere.
    fill_from = 1.0
    fill_to = 1.0
    arc_s = 0.0
    edge = 0.10  # softness of each arrival/departure, fraction of density
    # Meteors: rare streaks that burst toward full brightness — the
    # duty-cycle high notes over a quiet field. Expected count per
    # minute; 0 disables.
    meteor_rate = 0.0
    meteor_l = 0.95
    salt = "starfield"  # same salt -> the same stars, across movements

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n = lights.shape[0]
        pick = seeded_random(f"{self.salt}-pick", n)
        phase = seeded_random(f"{self.salt}-phase", n)
        rate = 0.6 + 0.9 * seeded_random(f"{self.salt}-rate", n)

        fill = _arc(t, self.arc_s, self.fill_from, self.fill_to)
        threshold = self.density * fill
        e = max(1e-9, self.edge * self.density)
        presence = 1.0 - smoothstep(threshold - e, threshold + e, pick)
        # Seniority: the deepest-hash stars arrived first, burn brightest
        # and steadiest; young stars are dimmer and flicker harder.
        seniority = np.clip(1.0 - pick / max(self.density, 1e-9), 0.0, 1.0)
        depth = 0.25 + 0.50 * (1.0 - seniority)
        twinkle = (
            1.0
            - depth
            + depth
            * (0.5 - 0.5 * np.cos(2.0 * np.pi * (t * rate / self.twinkle_s + phase)))
        )

        u, v = plane_xy(lights)
        glow = value_noise(u * 1.5 + 0.008 * t, v * 1.5 - 0.005 * t, seed=11)
        sky_level = self.sky_l * (1.0 + self.airglow * (glow - 0.5))

        sky = np.column_stack([sky_level, np.full(n, 0.035), np.full(n, self.sky_hue)])
        star = np.column_stack(
            [
                self.star_l * (0.55 + 0.45 * seniority),
                np.full(n, 0.045),
                np.full(n, self.star_hue),
            ]
        )
        out = blend_oklch(sky, star, presence * twinkle)
        if self.meteor_rate > 0.0:
            w = self._meteors(lights, t)
            if w is not None:
                hot = np.column_stack(
                    [np.full(n, self.meteor_l), np.full(n, 0.03), np.full(n, 90.0)]
                )
                out = blend_oklch(out, hot, w)
        return out

    def _meteors(self, lights: np.ndarray, t: float) -> Optional[np.ndarray]:
        """Blend weight (n,) of any live meteor streaks, else None.

        Slot-hashed events (patterns/README statelessness idiom): each
        8 s slot may hold one meteor — a great-arc streak crossed in
        ~1 s, a hot head with a decaying tail, then a brief afterglow.
        """
        slot_len = 8.0
        p_event = min(0.9, self.meteor_rate * slot_len / 60.0)
        phi, th = phi_theta(lights)
        slot = int(np.floor(t / slot_len))
        w: Optional[np.ndarray] = None
        for s in (slot - 1, slot):
            r = seeded_random(f"{self.salt}-met-{s}", 6)
            if r[0] >= p_event:
                continue
            dur = 0.9 + 0.5 * r[1]
            t0 = s * slot_len + r[2] * (slot_len - dur - 2.0)
            f = (t - t0) / dur
            if f < 0.0 or f > 1.8:
                continue
            az0 = 2.0 * np.pi * r[3]
            ph0 = 0.5 + 1.2 * r[4]
            ang = 2.0 * np.pi * r[5]
            length = np.radians(55.0)
            # Local chart around the path center: along/perp coordinates.
            x = (np.mod(th - az0 + np.pi, 2.0 * np.pi) - np.pi) * np.sin(ph0)
            y = phi - ph0
            along = x * np.cos(ang) + y * np.sin(ang)
            off = -x * np.sin(ang) + y * np.cos(ang)
            head = (min(f, 1.0) - 0.5) * length
            behind = head - along
            tail = np.where(
                (behind >= 0.0) & (along >= -0.55 * length),
                np.exp(-behind / (0.25 * length)),
                0.0,
            )
            bloom = np.exp(-((along - head) ** 2) / (2.0 * np.radians(1.5) ** 2))
            shape = np.maximum(0.9 * bloom, 0.6 * tail)
            perp = np.exp(-(off**2) / (2.0 * np.radians(1.8) ** 2))
            fade = 1.0 if f <= 1.0 else float(np.exp(-(f - 1.0) / 0.25))
            layer = shape * perp * fade
            w = layer if w is None else np.maximum(w, layer)
        return w


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
    # The movement arc: overall field level runs gain_from -> gain_to
    # over arc_s seconds of local time (banks rising out of the dark,
    # or a day's heat draining away). Flat at 1.0 by default.
    gain_from = 1.0
    gain_to = 1.0
    arc_s = 0.0
    # The tide: a single sphere-wide front — wavelength the whole
    # layout — crossing every tide_s seconds. A slow action at full
    # size: the proof that a still field is alive. 0 disables.
    tide_s = 0.0
    tide_depth = 0.35
    tide_angle = 30.0  # crossing direction, degrees in the plane
    seed = 7

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        u, v = plane_xy(lights)
        uu = u * self.scale + t * self.speed
        vv = v * self.scale - t * self.speed * 0.71
        wu, wv = warp(uu, vv, self.seed, self.warp_amount, octaves=2)
        field = fbm(wu, wv, self.seed + 10, octaves=self.octaves)
        field = np.clip(field, 0.0, 1.0) ** self.contrast
        if self.tide_s > 0.0:
            a = np.radians(self.tide_angle)
            proj = 0.5 * (u * np.cos(a) + v * np.sin(a))  # ~[-0.5, 0.5]
            crest = np.cos(2.0 * np.pi * (proj - t / self.tide_s))
            field = field * (1.0 - self.tide_depth * 0.5 * (1.0 - crest))
        field = field * _arc(t, self.arc_s, self.gain_from, self.gain_to)
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
    # The storm envelope: when crest_at >= 0, curtain activity rises
    # from activity_floor to a full crest at crest_at (fraction of
    # arc_s) and subsides after — the whole movement is one weather
    # system arriving, peaking, and letting go. crest_at < 0 disables.
    crest_at = -1.0
    activity_floor = 0.30
    crest_width = 0.28  # bell width, fraction of the arc
    arc_s = 0.0
    gain = 1.0  # overall curtain presence (pushes samples up the palette)
    salt = "veils"

    def _activity(self, t: float) -> float:
        if self.crest_at < 0.0 or self.arc_s <= 0.0:
            return 1.0
        u = min(max(t / self.arc_s, 0.0), 1.0)
        bell = float(np.exp(-(((u - self.crest_at) / self.crest_width) ** 2)))
        return self.activity_floor + (1.0 - self.activity_floor) * bell

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
        activity = self._activity(t)
        curtain = curtain / norm * activity + 0.08  # airglow floor stays lit

        border_line = (
            self.border
            + 0.06 * np.sin(2.0 * th + t * s * 0.11)
            + 0.03 * np.sin(t * s * 0.043)
        )
        above = h - border_line
        vertical = smoothstep(-0.03, 0.07, above) * np.exp(
            -np.maximum(above, 0.0) / self.tall
        )
        ripple = 1.0 + self.shimmer * activity * np.sin(
            17.0 * th - t * s * 2.1 + 3.0 * np.sin(7.0 * th + t * s * 0.53)
        )

        intensity = np.clip(curtain * vertical * ripple * self.gain, 0.0, 1.0)
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
    # The movement arc: ring strength runs gain_from -> gain_to over
    # arc_s seconds (a toll arriving out of stillness). Flat by default.
    gain_from = 1.0
    gain_to = 1.0
    arc_s = 0.0
    spin_salt = "ringwave"

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        phi, th = phi_theta(lights)
        az = np.degrees(th) % 360.0
        intensity, hue = ring_field(
            phi, az, t, self.period, self.spin_salt, self.descent_deg, self.sigma_deg
        )
        intensity = intensity * _arc(t, self.arc_s, self.gain_from, self.gain_to)
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


class Candles(Primitive):
    name = "candles"
    description = "Warm pools of candlelight, lit one by one across the dark"

    count = 72  # candle places at full gathering
    palette = CANDLE
    # The gathering arc: the fraction of places lit runs fill_from ->
    # fill_to over arc_s seconds, in seniority order (same rule as the
    # starfield: first lit, last out). Each candle is a small figure —
    # its core sits well above what a full field would be allowed.
    fill_from = 1.0
    fill_to = 1.0
    arc_s = 0.0
    edge = 0.08  # softness of each ignition/extinction
    spot_deg = 6.5  # pool radius
    pos_max = 0.80  # palette position at a pool's core (~L 0.54 in CANDLE)
    flicker_s = 4.2  # each flame's slow breath
    salt = "candles"

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        k = self.count
        pick = seeded_random(f"{self.salt}-pick", k)
        az = seeded_random(f"{self.salt}-az", k) * 2.0 * np.pi - np.pi
        ph = 0.85 + 1.15 * seeded_random(f"{self.salt}-ph", k)
        per = self.flicker_s * (0.7 + 0.6 * seeded_random(f"{self.salt}-per", k))
        phs = seeded_random(f"{self.salt}-phs", k) * 2.0 * np.pi

        fill = _arc(t, self.arc_s, self.fill_from, self.fill_to)
        e = max(1e-9, self.edge)
        lit = 1.0 - smoothstep(fill - e, fill + e, pick)
        flame = 1.0 - 0.25 * (0.5 + 0.5 * np.sin(2.0 * np.pi * (t / per + phs)))
        strength = lit * flame

        phi, th = phi_theta(lights)
        sin_phi = np.sin(phi)
        nl = np.column_stack([sin_phi * np.cos(th), sin_phi * np.sin(th), np.cos(phi)])
        sf = np.sin(ph)
        fl = np.column_stack([sf * np.cos(az), sf * np.sin(az), np.cos(ph)])
        sigma = np.radians(self.spot_deg)
        spot = np.exp((nl @ fl.T - 1.0) / (sigma**2))
        glow = np.minimum(spot @ strength, 1.15) / 1.15
        return self.palette.sample(np.clip(glow, 0.0, 1.0) * self.pos_max)


class Embers(Primitive):
    name = "embers"
    description = "A dying fire with a visible wind: coals fan, flare, and go out"

    # The cloud: the ash-glow bed, an EMBER-palette noise field.
    palette = EMBER
    scale = 1.8
    drift = 0.020  # feature drift, units/s
    contrast = 1.7
    # The wind: a gust every tide_s seconds that SWEEPS the whole sphere
    # in sweep_s — fast and sudden, then calm until the next one. It is
    # a palpable thing: it blows the CLOUD darker (wind_dim) while it
    # fans the SPARKS brighter (wind_fan), and every pass consumes some
    # sparks — a spark's brightest moment is its last.
    tide_s = 45.0  # seconds between gusts
    sweep_s = 5.5  # seconds for the front to cross the sphere
    gust_w = 0.07  # front thickness, fraction of the layout
    tide_angle = 30.0
    wind_dim = 0.55
    wind_fan = 1.1
    # The sparks: points of light glowing within the cloud.
    spark_density = 0.045
    spark_l = 0.38  # a resting coal (a figure: above the cloud's lane)
    flicker_s = 3.6
    mortality = 0.085  # fraction of spark lifetimes consumed per gust
    # rekindle=False: deaths are final (a fire going out — net decline).
    # rekindle=True: a standing fire — a dead coal rests dark_frac of
    # its cycle (dark_frac/mortality gusts), then rekindles, so the
    # population holds steady while individuals still flare and die.
    rekindle = False
    dark_frac = 0.30
    # The envelope: a significant swell (to swell_gain at swell_at of
    # the arc) before the long drain to gain_to. arc_s <= 0 holds at
    # gain_from with no swell.
    gain_from = 0.55
    swell_gain = 1.15
    swell_at = 0.22
    gain_to = 0.16
    arc_s = 0.0
    seed = 3
    salt = "embers"

    def _gain(self, t: float) -> float:
        if self.arc_s <= 0.0:
            return self.gain_from
        u = min(max(t / self.arc_s, 0.0), 1.0)
        if u < self.swell_at:
            return _arc(u, self.swell_at, self.gain_from, self.swell_gain)
        return _arc(
            u - self.swell_at, 1.0 - self.swell_at, self.swell_gain, self.gain_to
        )

    def _wind(
        self, u: np.ndarray, v: np.ndarray, t: float
    ) -> Tuple[np.ndarray, np.ndarray]:
        """(wind, passes) per light: the gust front and how many gusts
        have crossed each light. Every tide_s a narrow front sweeps the
        whole layout in sweep_s — sudden, then calm — and ``passes``
        increments exactly as the front crosses a light, so a spark that
        dies this pass dies at its brightest.
        """
        a = np.radians(self.tide_angle)
        proj = 0.5 * (u * np.cos(a) + v * np.sin(a))  # ~[-0.5, 0.5]
        k = np.floor(t / self.tide_s)
        tau = t - k * self.tide_s
        # The crest runs edge to edge (with clearance) in sweep_s.
        crest = -0.62 + 1.24 * tau / self.sweep_s
        live = 1.0 if tau <= self.sweep_s * 1.1 else 0.0
        wind = np.exp(-(((proj - crest) / self.gust_w) ** 2)) * live
        passes = np.maximum(k + (crest > proj), 0.0)
        return wind, passes

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n = lights.shape[0]
        u, v = plane_xy(lights)
        wind, passes = self._wind(u, v, t)
        gain = self._gain(t)

        # The cloud, blown darker where the gust runs.
        uu = u * self.scale + t * self.drift
        vv = v * self.scale - t * self.drift * 0.71
        wu, wv = warp(uu, vv, self.seed, 1.1, octaves=2)
        field = fbm(wu, wv, self.seed + 10, octaves=3)
        field = np.clip(field, 0.0, 1.0) ** self.contrast
        cloud = self.palette.sample(field * (1.0 - self.wind_dim * wind) * gain)

        # The sparks: seeded coals with individual breath, fanned by the
        # wind, consumed by it. Survivors keep glowing through the drain.
        pick = seeded_random(f"{self.salt}-pick", n)
        life = seeded_random(f"{self.salt}-life", n)
        per = self.flicker_s * (0.7 + 0.6 * seeded_random(f"{self.salt}-per", n))
        ph = seeded_random(f"{self.salt}-ph", n) * 2.0 * np.pi
        is_spark = pick < self.spark_density
        if self.rekindle:
            p_now = (life + passes * self.mortality) % 1.0
            p_next = (life + (passes + 1.0) * self.mortality) % 1.0
            alive = p_now > self.dark_frac
            dying_next = alive & (p_next <= self.dark_frac)
        else:
            alive = life > self.mortality * passes
            dying_next = alive & (life <= self.mortality * (passes + 1.0))
        flicker = 0.85 + 0.15 * np.sin(2.0 * np.pi * (t / per) + ph)
        fan = self.wind_fan * wind * (1.0 + 0.8 * dying_next)
        level = np.where(
            is_spark & alive,
            np.minimum(
                self.spark_l * (0.45 + 0.55 * gain) * flicker * (1.0 + fan), 0.90
            ),
            0.0,
        )
        # Fanned coals run hotter: orange toward yellow-white.
        hot = np.column_stack(
            [
                level,
                np.full(n, 0.13),
                42.0 + 26.0 * np.minimum(fan, 1.0),
            ]
        )
        weight = np.clip(level / max(self.spark_l, 1e-6), 0.0, 1.0)
        weight = np.minimum(weight, 1.0) * (level > 0.0)
        return blend_oklch(cloud, hot, np.minimum(weight, 0.95))

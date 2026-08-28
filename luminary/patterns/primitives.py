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
from luminary.patterns.easing import breath, env_ad, smoothstep
from luminary.patterns.fields import _hash01, fbm, ring_field, value_noise, warp
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
    # Trying to be stars: per-star color temperature (tint spreads the
    # population from warm gold toward blue-white through near-white
    # middles), a fast low-amplitude flutter on top of the slow breath,
    # and the duty-cycle trade — while the sky is sparse, the stars
    # that ARE on run brighter (sparse_boost), and the deep seniors go
    # on rising through the arc (swell).
    tint = 0.0  # 0: one hue; 1: full warm-to-blue spread
    flutter = 0.0  # fast micro-twinkle amplitude ("a very little bit" ~ 0.1)
    sparse_boost = 0.0
    swell = 0.0
    # Churn: short-lived stars that rise AND fall on their own clocks —
    # a population breathing under the seniority arc, not a one-way
    # fill. Sized against the sky itself: expected ephemerals at any
    # moment ≈ churn × the full-sky star count.
    churn = 0.0
    churn_life_s = 9.0
    churn_l = 0.60  # peak of an ephemeral, as a fraction of a senior's
    salt = "starfield"  # same salt -> the same stars, across movements

    def _star_colors(self, n: int) -> Tuple[np.ndarray, np.ndarray]:
        """(chroma, hue) per star. With tint, temperature runs warm gold
        through near-white to blue-white — blended in OKLab vec space so
        the middle of the population really is white."""
        if self.tint <= 0.0:
            return np.full(n, 0.045), np.full(n, self.star_hue)
        temp = seeded_random(f"{self.salt}-temp", n)
        temp = np.clip(0.5 + self.tint * (temp - 0.5) * 1.8, 0.0, 1.0)
        warm_h, cool_h = np.radians(62.0), np.radians(256.0)
        wa = np.array([0.085 * np.cos(warm_h), 0.085 * np.sin(warm_h)])
        co = np.array([0.075 * np.cos(cool_h), 0.075 * np.sin(cool_h)])
        vec = wa[None, :] + (co - wa)[None, :] * temp[:, None]
        chroma = np.hypot(vec[:, 0], vec[:, 1])
        hue = np.degrees(np.arctan2(vec[:, 1], vec[:, 0])) % 360.0
        return chroma, hue

    def _twinkle(self, t: float, seniority: np.ndarray, n: int) -> np.ndarray:
        """The per-star brightness dance: the slow breath (deep stars
        steady, young ones swinging), times an optional fast flutter."""
        phase = seeded_random(f"{self.salt}-phase", n)
        rate = 0.6 + 0.9 * seeded_random(f"{self.salt}-rate", n)
        depth = 0.25 + 0.50 * (1.0 - seniority)
        tw = (
            1.0
            - depth
            + depth
            * (0.5 - 0.5 * np.cos(2.0 * np.pi * (t * rate / self.twinkle_s + phase)))
        )
        if self.flutter > 0.0:
            p2 = seeded_random(f"{self.salt}-fl", n) * 2.0 * np.pi
            f1 = 1.3 + 1.1 * seeded_random(f"{self.salt}-f1", n)
            f2 = 0.7 + 0.5 * seeded_random(f"{self.salt}-f2", n)
            fast = np.sin(2.0 * np.pi * f1 * t + p2) * np.sin(2.0 * np.pi * f2 * t)
            tw = tw * (1.0 - self.flutter + self.flutter * (0.5 + 0.5 * fast))
        return np.asarray(tw)

    def _sky(self, lights: np.ndarray, t: float, n: int) -> np.ndarray:
        u, v = plane_xy(lights)
        glow = value_noise(u * 1.5 + 0.008 * t, v * 1.5 - 0.005 * t, seed=11)
        sky_level = self.sky_l * (1.0 + self.airglow * (glow - 0.5))
        return np.column_stack([sky_level, np.full(n, 0.035), np.full(n, self.sky_hue)])

    def _churn(self, t: float, n: int) -> np.ndarray:
        """Ephemeral-star envelopes in [0,1]: per light, offset windows
        of churn_life_s each holding a rise-and-fall (sin²) star with
        probability churn — alive briefly, gone completely, statelessly
        (a per-light per-window integer hash decides)."""
        if self.churn <= 0.0:
            return np.zeros(n)
        off = seeded_random(f"{self.salt}-churn-off", n)
        span = self.churn_life_s * (0.6 + 0.8 * seeded_random(f"{self.salt}-cl", n))
        x = t / span + off
        window = np.floor(x).astype(np.int64)
        lit = (
            _hash01(np.arange(n, dtype=np.int64), window, seed=1013)
            < self.churn * self.density
        )
        env: np.ndarray = np.sin(np.pi * (x - window)) ** 2
        return np.where(lit, env, 0.0)

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n = lights.shape[0]
        pick = seeded_random(f"{self.salt}-pick", n)

        fill = _arc(t, self.arc_s, self.fill_from, self.fill_to)
        threshold = self.density * fill
        e = max(1e-9, self.edge * self.density)
        presence = 1.0 - smoothstep(threshold - e, threshold + e, pick)
        # Seniority: the deepest-hash stars arrived first, burn brightest
        # and steadiest; young stars are dimmer and flicker harder.
        seniority = np.clip(1.0 - pick / max(self.density, 1e-9), 0.0, 1.0)
        twinkle = self._twinkle(t, seniority, n)

        # The duty trade: a sparse sky runs its stars near full; the
        # deep seniors keep rising through the arc.
        u_arc = min(max(t / self.arc_s, 0.0), 1.0) if self.arc_s > 0.0 else 1.0
        peak = min(0.95, self.star_l * (1.0 + self.sparse_boost * (1.0 - fill)))
        rising = 1.0 + self.swell * u_arc * seniority
        level = np.minimum(peak * (0.55 + 0.45 * seniority) * rising, 0.95)

        chroma, hue = self._star_colors(n)
        sky = self._sky(lights, t, n)
        star = np.column_stack([level, chroma, hue])
        weight = presence * twinkle
        ephem = self._churn(t, n)
        if self.churn > 0.0:
            # Ephemerals live in the not-yet-arrived population (their
            # window envelope IS their twinkle), never over a senior.
            w2 = np.where(presence < 0.5, ephem * self.churn_l, 0.0)
            weight = np.maximum(weight, w2)
        out = blend_oklch(sky, star, weight)
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


class Starfall(Starfield):
    """The stars leave the sky by FALLING from it.

    The firmament starts full (the same salt keeps the same stars as any
    other Starfield movement). Then, newest first, each star is picked:
    it swells into a flare over flare_rise_s, then streaks down its own
    meridian and off the stage in fall_s, tail burning behind it — and
    that point of sky is dark from then on. The departure schedule is a
    story: one, then a few, then a wave of it, then a trickle, down to
    the ``keep`` fraction of deep seniors who never fall. Pure in t: a
    star's departure time is a hash-ranked function, so any frame can be
    computed cold.
    """

    name = "starfall"
    description = "A full sky that empties one shooting star at a time"

    keep = 0.10  # the deep seniors who stay
    fall_delay = 14.0  # hold the full sky this long before the first fall
    fall_span = 175.0  # departures spread over this much local time
    # The schedule, as (order-fraction -> time-fraction) nodes: shallow
    # start (one at a time), the wave, then the long trickle.
    fall_q = (0.0, 0.02, 0.10, 0.55, 0.88, 1.0)
    fall_tf = (0.0, 0.14, 0.34, 0.55, 0.80, 1.0)
    flare_rise_s = 1.7  # the doomed star swells...
    fall_s = 1.35  # ...then is gone off the stage in this long
    trail_deg = 30.0
    fall_l = 0.95

    def _departures(self, pick: np.ndarray) -> np.ndarray:
        """Departure time per light (inf for keepers and non-stars)."""
        rank = np.clip(pick / max(self.density, 1e-9), 0.0, 1.0)
        q = (1.0 - rank) / max(1e-9, 1.0 - self.keep)
        T = self.fall_delay + np.interp(q, self.fall_q, self.fall_tf) * self.fall_span
        return np.where(rank < self.keep, np.inf, T)

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n = lights.shape[0]
        pick = seeded_random(f"{self.salt}-pick", n)
        is_star = pick < self.density
        seniority = np.clip(1.0 - pick / max(self.density, 1e-9), 0.0, 1.0)
        T = self._departures(pick)
        dt = t - T

        twinkle = self._twinkle(t, seniority, n)
        chroma, hue = self._star_colors(n)
        sky = self._sky(lights, t, n)
        level = np.minimum(self.star_l * (0.55 + 0.45 * seniority), 0.95)
        # The chosen star swells toward white and burns steady — its
        # goodbye starts before it moves.
        pre = np.clip(1.0 + dt / self.flare_rise_s, 0.0, 1.0)
        pre = np.where(np.isfinite(dt), pre, 0.0)
        alive = np.where(np.isfinite(dt), dt < 0.0, True)
        star = np.column_stack(
            [
                level + (self.fall_l - level) * pre**2,
                chroma * (1.0 - 0.6 * pre),
                hue,
            ]
        )
        weight = np.where(is_star & alive, np.maximum(twinkle, pre), 0.0)
        out = blend_oklch(sky, star, weight)

        w = self._falls(lights, t, pick, T)
        if w is not None:
            hot = np.column_stack(
                [np.full(n, self.fall_l), np.full(n, 0.03), np.full(n, 90.0)]
            )
            out = blend_oklch(out, hot, w)
        return out

    def _falls(
        self, lights: np.ndarray, t: float, pick: np.ndarray, T: np.ndarray
    ) -> Optional[np.ndarray]:
        """Blend weight of every star currently streaking off the stage."""
        dt = t - T
        falling = np.flatnonzero(
            (pick < self.density) & np.isfinite(dt) & (dt >= 0.0) & (dt <= self.fall_s)
        )
        if falling.size == 0:
            return None
        phi, th = phi_theta(lights)
        span = float(np.max(phi)) or 1.0
        sin_phi = np.sin(np.clip(phi, 0.2, np.pi - 0.2))
        trail = np.radians(self.trail_deg)
        sig_p = np.radians(1.8)
        sig_h = np.radians(1.6)
        w: Optional[np.ndarray] = None
        for i in falling:
            prog = float(dt[i]) / self.fall_s
            head = phi[i] + (1.06 * span - phi[i]) * prog**1.5
            off = (np.mod(th - th[i] + np.pi, 2.0 * np.pi) - np.pi) * sin_phi
            perp = np.exp(-(off**2) / (2.0 * sig_p**2))
            behind = head - phi
            seg = phi >= phi[i] - np.radians(2.0)
            tail = np.where((behind >= 0.0) & seg, np.exp(-behind / trail), 0.0)
            bloom = np.exp(-((phi - head) ** 2) / (2.0 * sig_h**2))
            layer = perp * np.maximum(bloom, 0.55 * tail)
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
    # size: the proof that a still field is alive. 0 disables. A second
    # tide at its own period and angle turns the swell into weather:
    # two crossing waves whose interference travels.
    tide_s = 0.0
    tide_depth = 0.35
    tide_angle = 30.0  # crossing direction, degrees in the plane
    tide2_s = 0.0
    tide2_depth = 0.30
    tide2_angle = 115.0
    seed = 7

    def _tide(
        self,
        field: np.ndarray,
        u: np.ndarray,
        v: np.ndarray,
        t: float,
        period: float,
        depth: float,
        angle: float,
    ) -> np.ndarray:
        a = np.radians(angle)
        proj = 0.5 * (u * np.cos(a) + v * np.sin(a))  # ~[-0.5, 0.5]
        crest = np.cos(2.0 * np.pi * (proj - t / period))
        return np.asarray(field * (1.0 - depth * 0.5 * (1.0 - crest)))

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        u, v = plane_xy(lights)
        uu = u * self.scale + t * self.speed
        vv = v * self.scale - t * self.speed * 0.71
        wu, wv = warp(uu, vv, self.seed, self.warp_amount, octaves=2)
        field = fbm(wu, wv, self.seed + 10, octaves=self.octaves)
        field = np.clip(field, 0.0, 1.0) ** self.contrast
        if self.tide_s > 0.0:
            field = self._tide(
                field, u, v, t, self.tide_s, self.tide_depth, self.tide_angle
            )
        if self.tide2_s > 0.0:
            field = self._tide(
                field, u, v, t, self.tide2_s, self.tide2_depth, self.tide2_angle
            )
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
    # What makes an aurora an aurora: fine vertical RAYS filamenting
    # each curtain (rays), curtain tops of uneven height, and — while
    # the storm runs high — break-up surges racing around the sphere
    # (one per surge_s) and a corona gathering at the apex. Intensity
    # above white_hot burns through the palette toward pale green-white.
    rays = 1.0
    surge_s = 0.0
    white_hot = 0.80
    hot_hue = 140.0  # what the burnt-through cores burn toward
    salt = "veils"

    def _activity(self, t: float) -> float:
        if self.crest_at < 0.0 or self.arc_s <= 0.0:
            return 1.0
        u = min(max(t / self.arc_s, 0.0), 1.0)
        bell = float(np.exp(-(((u - self.crest_at) / self.crest_width) ** 2)))
        return self.activity_floor + (1.0 - self.activity_floor) * bell

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        phi, th = phi_theta(lights)
        n = lights.shape[0]
        span = float(np.max(phi)) or 1.0
        h = 1.0 - phi / span  # 1 at the apex, 0 at the rim
        s = self.speed
        activity = self._activity(t)
        # Wrap-safe azimuth chart for every noise lookup.
        cx, sx = np.cos(th), np.sin(th)

        intensity = np.zeros(n)
        for k in range(self.sheets):
            r4 = seeded_random(f"{self.salt}-sheet-{k}", 4)
            m = k + 2  # integer harmonics keep azimuth wrap-safe
            sway = (0.35 + 0.40 * r4[0]) * np.sin(
                (m + 1) * th + t * s * (0.05 + 0.12 * r4[1]) + k * 2.1
            )
            drift = s * (0.010 + 0.030 * r4[2]) * (1.0 if k % 2 == 0 else -1.0)
            # Where along the sphere this curtain hangs right now.
            ridge = 0.5 + 0.5 * np.cos(m * th + sway + 2.0 * np.pi * drift * t)
            ridge = ridge**1.5
            # The rays: fine filaments across azimuth, billowed by a
            # slow fold field, racing on the drift clock — the curtain
            # is made of light-shafts, not of one smooth wash.
            fold = value_noise(
                cx * 1.3 + 0.045 * s * t, sx * 1.3 - 0.031 * s * t, seed=41 + k
            )
            shafts = value_noise(
                cx * 5.5 + 2.2 * fold + 0.22 * s * t * (1.0 if k % 2 else -1.0),
                sx * 5.5 - 1.8 * fold,
                seed=57 + k,
            )
            shafts = np.clip((shafts - 0.32) / 0.68, 0.0, 1.0) ** 2.2
            filaments = (1.0 - self.rays) + self.rays * (0.15 + 1.15 * shafts)
            # Each sheet hangs at its own border, with tops of uneven
            # height: ray length varies along the curtain.
            border_k = self.border + (k - (self.sheets - 1) / 2.0) * 0.07
            border_line = (
                border_k
                + 0.06 * np.sin(2.0 * th + t * s * 0.11 + k)
                + 0.03 * np.sin(t * s * 0.043 + 2.2 * k)
            )
            above = h - border_line
            raylen = self.tall * (
                0.55
                + 0.65
                * value_noise(cx * 2.1 + 0.05 * s * t + 7.0 * k, sx * 2.1, seed=71 + k)
            )
            vertical = smoothstep(-0.025, 0.05, above) * np.exp(
                -np.maximum(above, 0.0) / np.maximum(raylen, 1e-6)
            )
            weight = 1.0 / (1.0 + 0.5 * k)
            layer = 1.9 * weight * ridge * filaments * vertical
            intensity = 1.0 - (1.0 - intensity) * (1.0 - np.clip(layer, 0.0, 1.0))

        intensity = intensity * (0.25 + 0.75 * activity)
        # Break-up: while the storm runs high, a surge races the sphere.
        if self.surge_s > 0.0 and activity > 0.6:
            wavepos = 2.0 * np.pi * ((t / self.surge_s) % 1.0)
            d = np.mod(th - wavepos + np.pi, 2.0 * np.pi) - np.pi
            band = np.exp(-(d**2) / (2.0 * 0.55**2))
            gate = smoothstep(0.6, 0.9, activity)
            intensity = intensity * (1.0 + 0.75 * band * gate)
        # Corona: at full crest the rays gather over the apex.
        corona = np.exp(-((phi / 0.38) ** 2)) * smoothstep(0.78, 1.0, activity)
        intensity = intensity + 0.45 * corona

        ripple = 1.0 + self.shimmer * activity * np.sin(
            17.0 * th - t * s * 2.1 + 3.0 * np.sin(7.0 * th + t * s * 0.53)
        )
        above_all = h - (self.border - 0.10)
        intensity = np.clip(intensity * ripple * self.gain, 0.0, 1.0)
        fringe = smoothstep(0.10, 0.55, above_all)  # how far up the ray we are
        # Energy is the palette position — the curtain rim reaches the
        # top of the palette; the fringe pushes the high reaches a
        # little further along it (that is where the violet lives).
        position = np.clip(intensity * (0.85 + 0.30 * fringe), 0.0, 1.0)
        position = self.floor + (1.0 - self.floor) * position
        out = self.palette.sample(position)
        # The hottest cores burn past the palette toward near-white,
        # keyed by hot_hue (green-white by default; a violet-crowned
        # tuning burns purple-white).
        hotw = smoothstep(self.white_hot, 1.0, position) * 0.75
        if float(np.max(hotw)) > 1e-4:
            pale = np.column_stack(
                [np.full(n, 0.92), np.full(n, 0.05), np.full(n, self.hot_hue)]
            )
            out = blend_oklch(out, pale, hotw)
        return out


class RingWave(Primitive):
    name = "ringwave"
    description = "A luminous ring sweeping apex to rim, re-keyed each pass"

    period = 11.0  # one crest's descent, apex to rim
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
    # Launch cadence, decoupled from descent: with launch_s > 0 a new
    # ring starts every launch_s while each still takes the full period
    # to descend — rings share the sphere. start_at suppresses launches
    # before that local time (dropping the too-dim first toll of a
    # rising arc). ``meander`` colors each ring by WHEN it launched:
    # the palette position is launch-time / meander_s — a journey the
    # rings take together, one color at a time.
    launch_s = 0.0
    start_at = 0.0
    meander: Optional[Palette] = None
    meander_s = 240.0
    spin_salt = "ringwave"

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        phi, th = phi_theta(lights)
        az = np.degrees(th) % 360.0
        n = lights.shape[0]
        if self.launch_s <= 0.0:
            intensity, hue = ring_field(
                phi,
                az,
                t,
                self.period,
                self.spin_salt,
                self.descent_deg,
                self.sigma_deg,
            )
            intensity = intensity * _arc(t, self.arc_s, self.gain_from, self.gain_to)
            if self.palette is not None:
                out = self.palette.sample(np.clip(intensity, 0.0, 1.0))
                out[:, 0] = np.maximum(out[:, 0], self.ring_floor)
                return out
            out = np.empty((n, 3))
            out[:, 0] = self.ring_floor + (self.l_gain - self.ring_floor) * intensity
            out[:, 1] = self.chroma * np.sqrt(intensity)
            out[:, 2] = hue
            return out

        # Concurrent rings: every launch still on the sphere renders its
        # own descent (the shared ring_field math, offset to its launch).
        best = np.zeros(n)
        color = np.zeros((n, 3))
        color[:, 0] = self.ring_floor
        latest = int(np.floor((t - self.start_at) / self.launch_s))
        overlap = int(np.ceil(self.period / self.launch_s)) + 1
        for j in range(max(latest - overlap, 0), latest + 1):
            t_launch = self.start_at + j * self.launch_s
            dt = t - t_launch
            if dt < 0.0 or dt >= self.period:
                continue
            intensity, _ = ring_field(
                phi,
                az,
                dt,
                self.period,
                self.spin_salt,
                self.descent_deg,
                self.sigma_deg,
            )
            gain = _arc(t_launch, self.arc_s, self.gain_from, self.gain_to)
            intensity = intensity * gain
            if self.meander is not None:
                pos = min(max(t_launch / self.meander_s, 0.0), 1.0)
                anchor = self.meander.sample(np.array([pos]))[0]
            else:
                anchor = np.array([self.l_gain, self.chroma, 210.0])
            wins = intensity > best
            best = np.where(wins, intensity, best)
            for c in range(3):
                color[:, c] = np.where(wins, anchor[c], color[:, c])
        out = np.empty((n, 3))
        out[:, 0] = self.ring_floor + (color[:, 0] - self.ring_floor) * best
        out[:, 1] = color[:, 1] * np.sqrt(best)
        out[:, 2] = color[:, 2]
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
    # fill_gamma < 1 bends the arc fast-then-patient (the first flames
    # in seconds, the congregation over minutes).
    fill_from = 1.0
    fill_to = 1.0
    arc_s = 0.0
    fill_gamma = 1.0
    edge = 0.08  # softness of each ignition/extinction
    spot_deg = 6.5  # pool radius
    spot_to = 0.0  # >0: pools grow to this radius as the gathering fills
    pos_max = 0.80  # palette position at a pool's core (~L 0.54 in CANDLE)
    pos_to = 0.0  # >0: core position grows to this with the gathering
    flicker_s = 4.2  # each flame's slow breath
    flutter = 0.0  # fast flame-tip dance on top of the breath (~0.16)
    # Anchors: (azimuth°, polar°) seats lit FIRST, in order, before any
    # hash-chosen candle — the physical landmarks of the sculpture
    # (measured in an anchor_span_deg-tall frame; scaled to fit others).
    anchors: Optional[Tuple[Tuple[float, float], ...]] = None
    anchor_span_deg = 99.48
    # The sighing breath: at snuff_at a wave of still air spreads from
    # the center (the apex) to the rim over snuff_s — each flame leans
    # bright as it arrives, then goes out, leaving afterglow embers
    # and then the dark. floor_pos keeps the wax-smoke floor lit.
    snuff_at = 0.0
    snuff_s = 14.0
    afterglow = 0.12
    floor_pos = 0.0
    salt = "candles"

    def _fill(self, t: float) -> float:
        if self.arc_s <= 0.0:
            return self.fill_from
        u = min(max(t / self.arc_s, 0.0), 1.0)
        if self.fill_gamma != 1.0:
            u = u**self.fill_gamma
        else:
            u = u * u * (3.0 - 2.0 * u)
        return self.fill_from + (self.fill_to - self.fill_from) * u

    def _places(self, span: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(pick, az, ph) for every candle seat: anchors first (tiny
        ordered pick values — first lit, last out), hash seats after."""
        k = self.count
        pick = 0.02 + 0.98 * seeded_random(f"{self.salt}-pick", k)
        az = seeded_random(f"{self.salt}-az", k) * 2.0 * np.pi - np.pi
        ph = 0.85 + 1.15 * seeded_random(f"{self.salt}-ph", k)
        if self.anchors:
            m = min(len(self.anchors), k)
            scale = span / np.radians(self.anchor_span_deg)
            for i in range(m):
                a_deg, p_deg = self.anchors[i]
                pick[i] = (i + 0.5) * 1e-3
                az[i] = np.radians(a_deg)
                ph[i] = np.radians(p_deg) * scale
        return pick, az, ph

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        k = self.count
        phi, th = phi_theta(lights)
        span = float(np.max(phi)) or 1.0
        pick, az, ph = self._places(span)
        per = self.flicker_s * (0.7 + 0.6 * seeded_random(f"{self.salt}-per", k))
        phs = seeded_random(f"{self.salt}-phs", k) * 2.0 * np.pi

        fill = self._fill(t)
        prog = min(max(t / self.arc_s, 0.0), 1.0) if self.arc_s > 0.0 else 1.0
        e = max(1e-9, self.edge)
        lit = 1.0 - smoothstep(fill - e, fill + e, pick)
        flame = 1.0 - 0.25 * (0.5 + 0.5 * np.sin(2.0 * np.pi * (t / per + phs)))
        if self.flutter > 0.0:
            f1 = 1.6 + 1.0 * seeded_random(f"{self.salt}-f1", k)
            f2 = 0.6 + 0.5 * seeded_random(f"{self.salt}-f2", k)
            p2 = seeded_random(f"{self.salt}-p2", k) * 2.0 * np.pi
            fast = np.sin(2.0 * np.pi * f1 * t + p2) * np.sin(2.0 * np.pi * f2 * t)
            flame = flame * (1.0 - self.flutter + self.flutter * (0.5 + 0.5 * fast))
        strength = lit * flame

        if self.snuff_at > 0.0 and t >= self.snuff_at:
            # The breath spreads apex to rim; each flame leans bright
            # for a moment as it arrives, then dies to afterglow.
            front = (t - self.snuff_at) / self.snuff_s * (span * 1.08)
            arrive = front - ph  # >0 once the breath has reached a candle
            lean = 1.0 + 0.55 * np.exp(-((arrive + 0.06) ** 2) / (2.0 * 0.05**2))
            out_mul = np.where(
                arrive > 0.0,
                self.afterglow * np.exp(-np.maximum(arrive, 0.0) / 0.35),
                lean,
            )
            strength = strength * out_mul

        sin_phi = np.sin(phi)
        nl = np.column_stack([sin_phi * np.cos(th), sin_phi * np.sin(th), np.cos(phi)])
        sf = np.sin(ph)
        fl = np.column_stack([sf * np.cos(az), sf * np.sin(az), np.cos(ph)])
        spot_now = self.spot_deg + (
            (self.spot_to - self.spot_deg) * prog if self.spot_to > 0.0 else 0.0
        )
        sigma = np.radians(spot_now)
        spot = np.exp((nl @ fl.T - 1.0) / (sigma**2))
        glow = np.minimum(spot @ strength, 1.15) / 1.15
        pos_now = self.pos_max + (
            (self.pos_to - self.pos_max) * prog if self.pos_to > 0.0 else 0.0
        )
        position = np.clip(glow, 0.0, 1.0) * pos_now
        if self.floor_pos > 0.0:
            position = np.maximum(position, self.floor_pos)
        return self.palette.sample(position)


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
    # a palpable thing: under the front the CLOUD goes dark (wind_dim)
    # while the SPARKS inside it flare (wind_fan), and every pass
    # consumes some sparks — a spark's brightest moment is its last.
    tide_s = 45.0  # seconds between gusts
    sweep_s = 5.5  # seconds for the front to cross the sphere
    gust_w = 0.07  # front thickness, fraction of the layout
    tide_angle = 30.0
    wind_dim = 0.55  # instantaneous dimming under the front itself
    wind_fan = 1.1
    # The scar the wind leaves: each pass beats the cloud down by
    # ``scar`` and the damage heals only on the slow ``heal_s`` clock —
    # much slower than the gusts come, so the bed never fully recovers
    # between them and each gust visibly loses it ground.
    scar = 0.22
    heal_s = 110.0
    scar_max = 0.60
    # The sparks: coals glowing INSIDE the cloud banks — a coal needs a
    # bed of ash (cloud field above cloud_gate) to live in; the voids
    # between banks stay dark.
    spark_density = 0.045
    spark_l = 0.38  # a resting coal (a figure: above the cloud's lane)
    flicker_s = 3.6
    cloud_gate = 0.30  # sparks live where the (unblown) field exceeds this
    gate_soft = 0.10
    # After each pass a fanned coal stays flared for its own while —
    # per-coal 0.5–1.6× flare_s — and a coal consumed by the pass burns
    # brightest of all through its flare, then goes dark.
    flare_s = 5.0
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
    # The dying fall: past dark_at seconds the whole scene fades over
    # dark_s toward dark_floor of its level (0 disables) — the act ends
    # on the last breath of the last wave, not on a hard cut.
    dark_at = 0.0
    dark_s = 60.0
    dark_floor = 0.12
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
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(wind, passes, since) per light: the gust front, how many
        gusts have crossed each light, and seconds since the latest
        crossing (inf where none has). Every tide_s a narrow front
        sweeps the whole layout in sweep_s — sudden, then calm — and
        ``passes`` increments exactly as the front crosses a light, so
        a spark that dies this pass dies at its brightest.
        """
        a = np.radians(self.tide_angle)
        proj = 0.5 * (u * np.cos(a) + v * np.sin(a))  # ~[-0.5, 0.5]
        k = np.floor(t / self.tide_s)
        tau = t - k * self.tide_s
        # The crest runs edge to edge (with clearance) in sweep_s.
        crest = -0.62 + 1.24 * tau / self.sweep_s
        live = 1.0 if tau <= self.sweep_s * 1.1 else 0.0
        wind = np.exp(-(((proj - crest) / self.gust_w) ** 2)) * live
        crossed = crest > proj
        passes = np.maximum(k + crossed, 0.0)
        cross_tau = np.clip((proj + 0.62) * self.sweep_s / 1.24, 0.0, self.sweep_s)
        since = np.where(crossed, tau - cross_tau, tau + (self.tide_s - cross_tau))
        since = np.where(passes >= 1.0, since, np.inf)
        return wind, passes, since

    def _scar(self, passes: np.ndarray, since: np.ndarray) -> np.ndarray:
        """Accumulated cloud damage in [0, scar_max]: every past pass
        contributes ``scar`` decayed on the heal_s clock — a geometric
        sum in closed form, so the wake stays a pure function of t."""
        if self.scar <= 0.0 or self.heal_s <= 0.0:
            return np.zeros_like(since)
        r = float(np.exp(-self.tide_s / self.heal_s))
        decay = np.where(np.isfinite(since), np.exp(-since / self.heal_s), 0.0)
        total = self.scar * decay * (1.0 - r**passes) / (1.0 - r)
        return np.clip(total, 0.0, self.scar_max)

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n = lights.shape[0]
        u, v = plane_xy(lights)
        wind, passes, since = self._wind(u, v, t)
        gain = self._gain(t)

        # The cloud: blown dark under the front, and scarred behind it —
        # the beaten-down wake heals far slower than the gusts come.
        uu = u * self.scale + t * self.drift
        vv = v * self.scale - t * self.drift * 0.71
        wu, wv = warp(uu, vv, self.seed, 1.1, octaves=2)
        field = fbm(wu, wv, self.seed + 10, octaves=3)
        field = np.clip(field, 0.0, 1.0) ** self.contrast
        blown = (1.0 - self.wind_dim * wind) * (1.0 - self._scar(passes, since))
        cloud = self.palette.sample(field * blown * gain)

        # The sparks: coals seeded through the cloud banks (never the
        # voids), each breathing on its own clock, flaring on its own
        # clock after every gust, consumed by the wind. A coal the pass
        # killed burns brightest through its dying flare, then goes out.
        pick = seeded_random(f"{self.salt}-pick", n)
        life = seeded_random(f"{self.salt}-life", n)
        per = self.flicker_s * (0.7 + 0.6 * seeded_random(f"{self.salt}-per", n))
        ph = seeded_random(f"{self.salt}-ph", n) * 2.0 * np.pi
        tail = self.flare_s * (0.5 + 1.1 * seeded_random(f"{self.salt}-tail", n))
        in_cloud = smoothstep(
            self.cloud_gate - self.gate_soft, self.cloud_gate + self.gate_soft, field
        )
        is_spark = pick < self.spark_density
        if self.rekindle:
            p_now = (life + passes * self.mortality) % 1.0
            p_prev = (life + np.maximum(passes - 1.0, 0.0) * self.mortality) % 1.0
            alive = p_now > self.dark_frac
            died_now = (passes >= 1.0) & (p_prev > self.dark_frac) & ~alive
        else:
            alive = life > self.mortality * passes
            died_now = ~alive & (life > self.mortality * np.maximum(passes - 1.0, 0.0))
        flicker = 0.85 + 0.15 * np.sin(2.0 * np.pi * (t / per) + ph)
        # The flare: attack in a beat as the front hits, then each
        # coal's own decay — different coals hold it different whiles.
        dt = np.where(np.isfinite(since), since, 0.0)
        flare = np.where(
            np.isfinite(since),
            np.clip(dt / 0.35, 0.0, 1.0) * np.exp(-dt / tail),
            0.0,
        )
        glow = np.where(alive, flicker * (1.0 + self.wind_fan * flare), 0.0)
        glow = glow + np.where(died_now, 1.9 * flare, 0.0)
        level = np.where(
            is_spark,
            np.minimum(self.spark_l * (0.45 + 0.55 * gain) * in_cloud * glow, 0.92),
            0.0,
        )
        # Flaring coals run hotter: orange toward yellow-white.
        heat = np.minimum(self.wind_fan * flare + 1.9 * flare * died_now, 1.0)
        hot = np.column_stack(
            [
                level,
                np.full(n, 0.13),
                42.0 + 26.0 * heat,
            ]
        )
        weight = np.clip(level / max(self.spark_l, 1e-6), 0.0, 1.0)
        weight = np.minimum(weight, 1.0) * (level > 0.0)
        out = blend_oklch(cloud, hot, np.minimum(weight, 0.95))
        if self.dark_at > 0.0:
            fall = smoothstep(self.dark_at, self.dark_at + self.dark_s, t)
            keep = 1.0 - (1.0 - self.dark_floor) * float(fall)
            out[:, 0] *= keep
            out[:, 1] *= keep
        return out


class Motif(Primitive):
    name = "motif"
    description = "A fixed constellation that plays the same small phrase forever"

    # The lattice: ``count`` anchors laid on a golden-angle descent from
    # near the apex — designed, not random, and never moving. Every
    # cycle_s they play their phrase in order, one pulse each, then
    # rest. Everything else in a show happens around them; they do not
    # change for anyone.
    count = 7
    cycle_s = 6.4
    note_frac = 0.72  # the phrase occupies this much of the cycle
    pool_deg = 4.5
    peak_l = 0.42
    hue = 95.0  # pale gold
    chroma = 0.05
    attack = 0.12
    decay = 0.85
    phase_s = 0.0  # shift the cycle: the first note lands at phase_s

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n = lights.shape[0]
        phi, th = phi_theta(lights)
        sin_phi = np.sin(phi)
        nl = np.column_stack([sin_phi * np.cos(th), sin_phi * np.sin(th), np.cos(phi)])
        sigma = np.radians(self.pool_deg)

        step = self.note_frac * self.cycle_s / self.count
        t_in = (t - self.phase_s) % self.cycle_s
        level = np.zeros(n)
        for i in range(self.count):
            az = np.radians((i * 137.508) % 360.0)
            ph = 0.55 + 1.35 * (i + 0.5) / self.count
            axis = np.array(
                [np.sin(ph) * np.cos(az), np.sin(ph) * np.sin(az), np.cos(ph)]
            )
            pool = np.exp((nl @ axis - 1.0) / (sigma**2))
            dt = t_in - i * step
            if dt < 0.0:
                dt += self.cycle_s  # the previous cycle's tail
            env = float(env_ad(dt, self.attack, self.decay))
            level = np.maximum(level, pool * env)

        out = np.empty((n, 3))
        out[:, 0] = self.peak_l * level
        out[:, 1] = self.chroma * np.clip(level * 1.5, 0.0, 1.0)
        out[:, 2] = self.hue
        return out

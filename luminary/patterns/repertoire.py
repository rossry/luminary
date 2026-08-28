"""Repertoire: the substantial book-two voices and shows, importable.

Pattern files under ``patterns/`` are exec-loaded, never importable — so
any voice or show that *other* shows want to nest lives here, and the
pattern file is a thin registration subclass (the book-two idiom,
uniform across the volume). The rule: art lives in the library exactly
when something else composes it.

Contents:

- :class:`SmallPlanet` — the sphere as a tiny living world (sun,
  seasons, cities, aurora cap, phase-true moon).
- :class:`Fireflies` — a meadow that drifts into unison flashing and
  back, synchrony in closed form.
- :class:`Relay` — bead races run on the physical wiring, heat after
  heat.
- :func:`nocturne_movements` / :func:`nocturne` — the composed half
  hour of night, as a movement list any conductor can nest.

Everything obeys the pattern contract (spec §9.1): stateless,
vectorized, pure in ``(lights, t)``.
"""

from __future__ import annotations

import zlib
from typing import Any, Dict, List, Tuple

import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.compose import Conductor, Movement
from luminary.patterns.easing import env_ad, smootherstep
from luminary.patterns.fields import fbm, value_noise
from luminary.patterns.palettes import (
    AURORA,
    Palette,
    SEA_GLASS,
    oklch_to_vec,
    vec_to_oklch,
)
from luminary.patterns.primitives import (
    AuroraVeils,
    Candles,
    Embers,
    NoiseGlow,
    Primitive,
    RingWave,
    Starfield,
)
from luminary.patterns.util import phi_theta, plane_xy, seeded_random


def _vec3(l: float, c: float, h: float) -> np.ndarray:
    """One OKLCH color as its OKLab blend vector [L, C·cosH, C·sinH]."""
    hr = np.radians(h)
    return np.array([l, c * np.cos(hr), c * np.sin(hr)])


class SmallPlanet(Primitive):
    name = "small_planet"
    description = "A living miniature world: sun, seasons, cities, aurora, moon"
    notes = (
        "A world the size of your arms. Watch one full day cross it in ten "
        "minutes: dawn on one limb, cities waking on the dark side of the "
        "other, weather riding the trade winds between. The aurora belongs "
        "to the winter pole; the moon is full only when it faces the sun. "
        "Arrived: it simply turns, and keeps turning."
    )

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


class Fireflies(Primitive):
    name = "fireflies"
    description = "Wandering fireflies that drift into unison and out again"
    notes = (
        "A dark meadow, a few dozen slow lights, each on its own clock. "
        "Every five minutes the meadow finds itself: the flashes pull into "
        "unison, hold a breath of synchrony, and scatter again. Coming and "
        "going at once — watch for the moment it locks."
    )

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


class Relay(Primitive):
    name = "relay"
    description = "Bead races down the physical strip order, heat after heat"
    notes = (
        "Every strip is a lane and the racers run the actual wiring — down "
        "the edge, in the radial, out, around. Twenty seconds a heat: "
        "surges, flagging, a gold flood at the line, a breath, new colors, "
        "again. The sculpture showing you its own electricity. Best up "
        "close."
    )

    race_s = 14.0  # gun to the last plausible finish
    rest_s = 6.0  # lineup breath between heats
    bead_sigma = 0.030  # bead half-width, as a fraction of the strip
    tail = 0.10  # comet tail length, fraction of the strip
    wobble = 0.06  # mid-race surge amplitude, fraction of the strip
    lane_c = 0.105  # lane chroma
    base_l = 0.028
    salt = "relay"

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n = lights.shape[0]
        ctrl = lights[:, LightColumns.CONTROLLER].astype(np.int64)
        chan = lights[:, LightColumns.CHANNEL].astype(np.int64)
        idx = lights[:, LightColumns.INDEX]

        # Lanes = physical strips, in canonical (controller, channel) order.
        sids, inv = np.unique(ctrl * 64 + chan, return_inverse=True)
        k = len(sids)
        length = np.zeros(k)
        np.maximum.at(length, inv, idx)
        x = idx / np.maximum(length[inv], 1.0)  # 0..1 along each strip's wiring

        round_s = self.race_s + self.rest_s
        rnd = int(np.floor(t / round_s))
        tau = t - rnd * round_s

        # This heat's draw, per lane: finish time, wobble, lane colors.
        finish = self.race_s * (0.62 + 0.33 * seeded_random(f"{self.salt}-T-{rnd}", k))
        wob_f = 2.0 + 3.0 * seeded_random(f"{self.salt}-wf-{rnd}", k)
        wob_p = 2.0 * np.pi * seeded_random(f"{self.salt}-wp-{rnd}", k)
        hue_shift = 360.0 * seeded_random(f"{self.salt}-h-{rnd}", 1)[0]
        # Golden-angle spacing: neighboring lanes get far-apart hues.
        lane_hue = (np.arange(k) * 137.508 + hue_shift) % 360.0
        winner = int(np.argmin(finish))

        # Bead positions: exact at the gun and at each lane's finish.
        s = np.clip(tau / finish, 0.0, 1.0)
        gate = s * (1.0 - s)
        pos = (
            smootherstep(0.0, 1.0, s)
            + self.wobble * np.sin(wob_f * 2.0 * np.pi * s + wob_p) * gate
        )
        running = (tau >= 0.0) & (s < 1.0)

        # Per-light gather of this lane's state.
        pos_l = pos[inv]
        run_l = running[inv]
        hue_l = lane_hue[inv]
        d = x - pos_l
        sig = self.bead_sigma
        head = np.exp(-(d**2) / (2.0 * sig**2))
        behind = (d < 0.0) & (d > -3.5 * self.tail)
        comet = np.where(behind, 0.55 * np.exp(d / self.tail), 0.0)
        bead = np.where(run_l, np.maximum(head, comet), 0.0)

        # Finishes: the winner floods gold, the field acknowledges faintly.
        dt_fin = tau - finish
        flash = env_ad(dt_fin, 0.12, 0.9)
        lane_flash = np.where(np.arange(k) == winner, 0.60, 0.10) * flash
        flash_l = lane_flash[inv]

        # Rest breath: the whole field settles and swells once before the gun.
        rest = np.clip((tau - self.race_s) / self.rest_s, 0.0, 1.0)
        breathe = 0.020 * np.sin(np.pi * rest) if rest > 0.0 else 0.0

        out = np.empty((n, 3))
        out[:, 0] = np.clip(
            self.base_l + breathe + 0.60 * bead + 0.55 * flash_l, 0.0, 0.92
        )
        out[:, 1] = self.lane_c * np.clip(bead + flash_l, 0.12, 1.0) + 0.02
        # Lanes keep their hue; a winning flood turns the lane gold.
        gold = (flash_l > bead * 0.8) & (flash_l > 0.02)
        out[:, 2] = np.where(gold, 85.0, hue_l)
        return out


# The toll: night blues that brighten toward a pale crest — a ring is a
# band, a figure, so its top sits above the full-field duty-cycle lane.
TOLL = Palette(
    [
        (0.0, 0.020, 0.015, 255.0),
        (0.5, 0.30, 0.100, 245.0),
        (0.85, 0.60, 0.120, 235.0),
        (1.0, 0.80, 0.070, 225.0),
    ]
)


def nocturne_movements() -> List[Movement]:
    """The night, as data: seven movements, exactly 1800 s.

    Every movement is one action at the size of the sphere, and knows
    whether it is going somewhere, coming from somewhere, or arrived:
    the day's fire drains out (going), a sky populates star by star
    (going), an auroral storm crests and lets down (coming-arriving-
    leaving), the deep sea rests (arrived — the still heart), a toll
    builds out of the stillness (coming), candles gather one by one
    (going, toward warmth), and the same stars — same salt, same
    seniority — release in reverse order of arrival (going home).

    Duty cycle: full fields hold a low lane (means well under 0.3);
    figures — stars, ring crests, candle cores, meteors — sit above it,
    and meteors alone burst toward full brightness.
    """
    return [
        Movement(
            Embers(arc_s=240.0, swell_gain=1.25, mortality=0.16),
            240.0,
            fade=10.0,
            title="dusk",
            notes=(
                "The day's fire, and the wind that ends it. Coals glow "
                "inside the ash-cloud; every three-quarters of a minute a "
                "gust sweeps the whole sphere in a five-second breath — "
                "watch it: the cloud goes dark under it while the sparks "
                "flare hot, and some flare for the last time. The fire "
                "swells once, defiant, near the start. Then: going out, "
                "gust by gust, until only the deepest coals remain."
            ),
        ),
        Movement(
            Starfield(
                density=0.035,
                twinkle_s=6.5,
                star_l=0.85,
                star_hue=80.0,
                fill_from=0.04,
                fill_to=1.0,
                arc_s=210.0,
                meteor_rate=0.9,
            ),
            210.0,
            fade=20.0,
            title="first-stars",
            notes=(
                "One star, then three, then a sky. The brightest arrived "
                "first and hold steady; the young ones flicker at the edge "
                "of arriving. Once a minute or so, something falls. Going: "
                "toward fullness."
            ),
        ),
        Movement(
            AuroraVeils(
                palette=AURORA,
                speed=1.3,
                crest_at=0.45,
                activity_floor=0.50,
                arc_s=300.0,
                gain=1.35,
            ),
            300.0,
            fade=24.0,
            title="veils",
            notes=(
                "Weather from above: green curtains hung from the apex, "
                "already swaying as you arrive. The storm crests with "
                "violet at its fringes around the second minute, then "
                "lets itself down. One system — coming, arrived, leaving."
            ),
        ),
        Movement(
            NoiseGlow(
                palette=SEA_GLASS,
                scale=2.6,
                speed=0.028,
                contrast=1.45,
                gain_from=0.95,
                gain_to=0.95,
                arc_s=240.0,
                tide_s=28.0,
                tide_depth=0.50,
                breathe_s=0.0,
                seed=12,
            ),
            240.0,
            fade=24.0,
            title="deep-sea",
            notes=(
                "The resting heart of the night. Nothing is going "
                "anywhere: this is what arrived feels like. The proof it "
                "is alive is the swell — one sphere-wide wave every "
                "twenty-eight seconds, rich at its crest, dark in its "
                "trough."
            ),
        ),
        Movement(
            RingWave(
                period=14.0,
                sigma_deg=9.0,
                palette=TOLL,
                gain_from=0.12,
                gain_to=1.0,
                arc_s=80.0,
            ),
            240.0,
            fade=18.0,
            title="rings",
            notes=(
                "Out of the stillness, a toll. Each ring is a single "
                "gesture the size of the sphere — fourteen seconds from "
                "apex to rim — and each lands a little fuller than the "
                "last. Someone is calling. Coming: toward us."
            ),
        ),
        Movement(
            Candles(fill_from=0.03, fill_to=0.88, arc_s=270.0),
            300.0,
            fade=26.0,
            title="candles",
            notes=(
                "An answer: one candle. Then its neighbors. Warm pools "
                "gather across the dark, each flame breathing on its own "
                "clock, until the sphere holds a congregation of small "
                "fires. Going: toward warmth, one light at a time."
            ),
        ),
        Movement(
            Starfield(
                density=0.035,
                twinkle_s=7.0,
                star_l=0.70,
                sky_l=0.024,
                fill_from=1.0,
                fill_to=0.10,
                arc_s=250.0,
                meteor_rate=0.5,
            ),
            270.0,
            fade=28.0,
            title="starfall",
            notes=(
                "The same stars as before — the sky remembers its own. Now "
                "they let go in reverse order of arrival: the newest "
                "first, the deep ones last, until only the fixed stars "
                "hold. Going: home. If one falls on your watch, that was "
                "the goodbye."
            ),
        ),
    ]


def nocturne() -> Conductor:
    """The half hour of night as a nestable pattern instance."""
    show = Conductor(nocturne_movements())
    show.name = "nocturne"
    show.description = (
        "Half an hour of night: embers, stars, veils, sea, rings, candles"
    )
    show.notes = (
        "Thirty minutes of night in seven movements, each one action at "
        "the size of the sphere: fire drains, a sky fills, a storm "
        "crests, the sea rests, a toll approaches, candles gather, and "
        "the same stars let go in reverse order of arrival."
    )
    show.audio = "nocturne.mp3"  # the curated set: see book-two/nocturne.py
    return show

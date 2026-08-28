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
from luminary.patterns.compose import Conductor, Layered, Movement
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
    Blackout,
    Candles,
    Embers,
    NoiseGlow,
    Primitive,
    RingWave,
    Starfall,
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
    wander_s = 54.0  # mean wander period (54 = the meadow's amble)
    meadow_l = 0.032
    # The meadow's colors: grass by default; retuned voices (Köln's
    # scouting) move the whole scene into another world.
    base_hue = 132.0
    glow_hue_shift = -18.0  # flash color relative to the base
    salt = "fireflies"

    def _coherence(self, t: float) -> float:
        """0 = every fly on its own clock, 1 = the meadow in unison."""
        swell = 0.5 - 0.5 * np.cos(2.0 * np.pi * t / self.sync_period)
        return float(np.clip(1.6 * swell - 0.35, 0.0, 1.0))

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n = lights.shape[0]
        k = self.count

        # Per-fly constants: homes in the mid band, wander clocks
        # (scaled by wander_s; the default reproduces the meadow's own).
        th0 = seeded_random(f"{self.salt}-th", k) * 2.0 * np.pi - np.pi
        ph0 = 0.55 + 1.35 * seeded_random(f"{self.salt}-ph", k)
        ws = self.wander_s / 54.0
        p1 = ws * (37.0 + 34.0 * seeded_random(f"{self.salt}-p1", k))
        p2 = ws * (53.0 + 44.0 * seeded_random(f"{self.salt}-p2", k))
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
        out[:, 2] = self.base_hue

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
            # The base hue shading toward the flash color as a fly glows.
            out[:, 2] = self.base_hue + self.glow_hue_shift * glow
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

# The veils' night: a violet-blue dark sky under green curtains whose
# tops turn through blue into real purple — the crest crowns burn
# purple-white (pair with hot_hue). AURORA keeps violet only at its
# very tip; this palette gives the high fringes a whole violet band.
VEILS_NIGHT = Palette(
    [
        (0.0, 0.030, 0.022, 240.0),
        (0.40, 0.30, 0.130, 158.0),
        (0.66, 0.50, 0.150, 140.0),
        (0.80, 0.52, 0.150, 210.0),
        (0.90, 0.58, 0.150, 305.0),
        (1.0, 0.68, 0.120, 322.0),
    ]
)

# The rings' journey, one color per toll: green, through blue-white and
# purple-white, down to a warm and dimming red (the palette's own L
# carries the dimming — late rings arrive quieter because they are red).
RING_MEANDER = Palette(
    [
        (0.0, 0.50, 0.130, 150.0),
        (0.33, 0.72, 0.060, 225.0),
        (0.62, 0.68, 0.070, 300.0),
        (1.0, 0.30, 0.110, 30.0),
    ]
)

# The sculpture's own landmarks, measured from the folded 4A-33 net
# (azimuth°, polar° in a 99.48°-span frame): the four hexagon centers —
# the only vertices where six triangle-panels meet — with the
# center-front point completing their ring at the opening, then the
# tips of the four arms.
SEATS = (
    (54.0, 37.38),
    (-18.0, 37.38),
    (-162.0, 37.38),
    (126.0, 37.38),
    (-90.0, 37.38),
    (54.0, 58.28),
    (126.0, 58.28),
    (0.0, 90.0),
    (180.0, 90.0),
)


def nocturne_movements() -> List[Movement]:
    """The night, as data: seven movements, 1784 s (29:44).

    Every movement is one action at the size of the sphere, and knows
    whether it is going somewhere, coming from somewhere, or arrived.
    Each is timed to its own track (the curated set — filenames and
    sources in ``patterns/book-two/nocturne.py``) and declares it as
    ``Movement.audio``, so a stage playing the show as chapters starts
    each act's music at the act.

    Duty cycle: full fields hold a low lane (means well under 0.3);
    figures — stars, ring crests, candle cores, falling stars — sit
    above it, and only streaks burst toward full brightness.
    """
    return [
        Movement(
            Embers(
                arc_s=251.0,
                gain_from=0.40,
                swell_gain=1.35,
                swell_at=0.60,
                gain_to=1.50,
                mortality=0.06,
                dark_at=222.0,
                dark_s=26.0,
                dark_floor=0.08,
            ),
            251.0,
            fade=10.0,
            title="embers",
            audio="poa-alpina.mp3",
            notes=(
                "The day's fire, and the wind that cannot put it out — "
                "yet. Coals glow inside the ash banks, and every "
                "three-quarters of a minute a gust crosses the sphere "
                "in a five-second breath: the cloud goes dark under it "
                "and stays beaten down, the coals flare and hold their "
                "flare — and the fire comes back stronger, growing "
                "through the first two and a half minutes faster than "
                "the wind can take it. It burns full nearly to the end; "
                "the last gust and the dying fall share the final half "
                "minute."
            ),
        ),
        Movement(
            Starfield(
                density=0.035,
                twinkle_s=6.5,
                star_l=0.88,
                fill_from=0.04,
                fill_to=1.0,
                arc_s=132.0,
                meteor_rate=0.9,
                tint=1.0,
                flutter=0.10,
                sparse_boost=0.45,
                swell=0.25,
                churn=0.30,
            ),
            132.0,
            fade=12.0,
            title="first-stars",
            audio="saman.mp3",
            notes=(
                "One star, then three, then a sky. While it is nearly "
                "empty the few that are on burn nearly full — and short-"
                "lived stars rise and fall all through it, warm gold to "
                "blue-white, while the deep ones rise and rise. Going: "
                "toward fullness."
            ),
        ),
        Movement(
            AuroraVeils(
                palette=VEILS_NIGHT,
                speed=1.3,
                crest_at=0.45,
                activity_floor=0.50,
                arc_s=391.0,
                gain=1.35,
                surge_s=24.0,
                white_hot=0.88,
                hot_hue=318.0,
            ),
            391.0,
            fade=24.0,
            title="veils",
            audio="flight-from-the-city.mp3",
            notes=(
                "Weather from above: curtains of rayed light hung from "
                "the apex, their tops uneven, their shafts racing, over "
                "a violet-blue dark. The storm crests near the third "
                "minute — surges race the sphere, the high fringes turn "
                "through blue into real purple, the cores burn "
                "purple-white, a corona gathers at the crown — then it "
                "lets itself down. One system: coming, arrived, leaving."
            ),
        ),
        Movement(
            Layered(
                NoiseGlow(
                    palette=SEA_GLASS,
                    scale=2.6,
                    speed=0.028,
                    contrast=1.45,
                    gain_from=0.95,
                    gain_to=0.95,
                    arc_s=194.0,
                    tide_s=28.0,
                    tide_depth=0.50,
                    tide2_s=41.0,
                    tide2_depth=0.35,
                    tide2_angle=115.0,
                    breathe_s=0.0,
                    seed=12,
                ),
                Starfield(
                    density=0.02,
                    fill_from=0.0,
                    fill_to=0.0,
                    sky_l=0.0,
                    star_l=0.60,
                    star_hue=185.0,
                    tint=0.0,
                    twinkle_s=3.5,
                    flutter=0.12,
                    churn=0.30,
                    churn_life_s=7.0,
                    churn_l=0.85,
                    salt="plankton",
                ),
            ),
            194.0,
            fade=24.0,
            title="deep-sea",
            audio="the-pearl.mp3",
            notes=(
                "The resting heart of the night. Two sphere-wide swells "
                "cross each other — every wave arrives differently — and "
                "plankton motes glow up and fade through the banks, "
                "cyan points on the green-dark. Nothing is going "
                "anywhere: this is what arrived feels like."
            ),
        ),
        Movement(
            RingWave(
                period=14.0,
                sigma_deg=6.0,
                launch_s=7.0,
                start_at=7.0,
                gain_from=0.22,
                gain_to=1.0,
                arc_s=110.0,
                meander=RING_MEANDER,
                meander_s=439.0,
            ),
            439.0,
            fade=18.0,
            title="rings",
            audio="cantus.mp3",
            notes=(
                "Out of the stillness, a toll every seven seconds, each "
                "ring still taking its slow fourteen from apex to rim — "
                "two always share the sphere. Their color is a journey: "
                "green, through blue-white, purple-white, down to a warm "
                "red that dims as the lament does. Someone is calling, "
                "and then the calling is over."
            ),
        ),
        Movement(
            Candles(
                anchors=SEATS,
                anchor_spread=0.16,
                anchor_jitter_deg=2.5,
                fill_from=0.0,
                fill_to=1.0,
                arc_s=130.0,
                fill_gamma=0.75,
                edge=0.015,
                spot_to=9.5,
                pos_to=1.0,
                flutter=0.16,
                vary=1.0,
                ignite_flare=0.55,
                die_frac=0.08,
                snuff_at=138.0,
                snuff_s=13.0,
                floor_pos=0.05,
            ),
            166.0,
            fade=14.0,
            title="candles",
            audio="requiem-static-king.mp3",
            notes=(
                "An answer: flames catching at the sculpture's own "
                "bones — the hexagon hearts, the center-front, the arm "
                "tips — unevenly, each flaring as it lights, none on "
                "anyone's schedule. No two alike: brighter and dimmer, "
                "wide and small, guttering and recovering; a few go out "
                "early and stay out. The rest swell to a roaring wave "
                "of fire — then one sighing breath spreads from the "
                "crown and takes every flame, some leaning a beat "
                "longer than others, and the dark it leaves is full of "
                "stars."
            ),
        ),
        Movement(
            Starfall(
                density=0.035,
                twinkle_s=7.0,
                star_l=0.70,
                sky_l=0.024,
                tint=1.0,
                flutter=0.10,
                fall_delay=16.0,
                fall_span=174.0,
                end_black_at=189.0,
                end_black_s=26.0,
            ),
            191.0,
            fade=16.0,
            title="starfall",
            audio="eluvium.mp3",
            notes=(
                "The same stars as before — the sky remembers its own. "
                "Then one is chosen: it swells and falls, streaking away "
                "in its own direction, gold ones gold and blue ones "
                "blue, burning out as they go. Then another, and "
                "another — one single swell, strongest just before the "
                "end, the sky itself draining away beneath them — until "
                "the last star falls on black. If you make a wish, you "
                "have the whole shower."
            ),
        ),
        Movement(
            Blackout(),
            20.0,
            fade=0.0,
            title="blackout",
            notes=(
                "Twenty seconds of nothing at all. Hold it — the night "
                "is over when the dark says so, not the lights."
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
        "A half hour of night in seven movements, each one action at "
        "the size of the sphere: fire drains, a sky fills, a storm "
        "crests, the sea rests, a toll passes through every color of "
        "night, candles roar and are breathed out, and the stars fall. "
        "Each act carries its own track — queue it as chapters and the "
        "music changes with the act."
    )
    return show

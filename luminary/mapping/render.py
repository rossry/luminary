"""Mapping-mode renderers: one composite pattern, driven by per-light roles.

**Parity by construction.** Every positional field — beads, board hues,
the wheel's hue and windmill, the ring, the finale — is evaluated once,
on the net capture's lights only, and every rendered light receives its
value by gathering through ``ref``: its reference net light. The window
passes the identity mapping; the wire passes each hypothesis LED's
nearest net light along its panel's serpentine path. There is no
wire-side field evaluation at all, so the window and the wire cannot
disagree about what a place on the sphere looks like — the hypothesis
(winding, density, channel) only changes *which* net lights a strip's
indices reference, never the field values. Role assignment happens in
the session builders — the same scene role per panel-and-strip; this
module only turns (roles, ref, net geometry, t) into OKLCH, pure and
vectorized, stateless for a fixed construction (the session swaps
instances when the mapping state changes, exactly like a WS
set_pattern).

Visual language (plan/mapping/DESCRIPTION.md):
  BEADS        the idle backdrop everywhere, wire included: staggered
               white beads that fade in, crawl their strut, and fade
               out within about two seconds — independent seeded phases
               per strut and lane, never synchronized. Twins mirror
               across each strut.
  BREATHE      the board being placed breathes in its board color.
  SOLID        a board locked in stage A holds its color, steady, until
               the ports stage completes; in stage B, waiting boards
               are back on the beads backdrop.
  WHEEL        the orientation test: hue is the light's angle about its
               board's HOME vertex — the corner the board's panels meet
               at — one continuous wheel per board, fixed by logical
               position (recording a mapping never moves it); the
               data-aux door panels continue their board's wheel rather
               than starting their own — under a three-spoke dark
               windmill sweeping clockwise (net frame). Full brightness
               on the strip under test; 20% brightness on recorded
               strips and on the first-30-LED previews of unmapped
               strips.
  OFF          deliberately unlit. The active strip plays the wheel on
               its first and last index quarters with OFF between, so a
               density mismatch in either direction reads as "only one
               half of the strip lit", not a subtle hue shift.
  RING         the mapped pattern: a hue ring descending in elevation
               (PHI_S), each successive wave rotating its hues by a
               seeded random angle.

Board colors are pleasant OKLCH hues spaced equally around the wheel in
plan order (moderate chroma — identity tags, not tests): `board_hues`.
"""

from __future__ import annotations

from typing import List, Tuple

import numpy as np

from luminary.patterns.base import Pattern
from luminary.patterns.util import seeded_random

# Per-light roles
BEADS = 0
BREATHE = 1
SOLID = 2
WHEEL_FULL = 3
WHEEL_DIM = 4
RING = 5
OFF = 6  # deliberately unlit (the active strip's dark middle half)

_BREATHE_PERIOD = 2.6  # seconds; calm but clearly alive
_BAND_PERIOD = 6.0  # seconds per windmill revolution (angular speed)
_SPOKES = 3  # dark windmill spokes — a third of the wait per panel
_WHEEL_DIM_GAIN = 0.20  # recorded strips / previews vs the active strip
_RING_PERIOD = 7.0  # seconds per apex-to-rim descent
_BEAD_LANES = (7.3, 9.1)  # seconds between beads per strut; staggered lanes
_BEAD_LIFE = 2.0  # seconds a bead lives: fade in, crawl, fade out
_BEAD_CYCLES = 8  # per-(edge, lane) random slots before traffic repeats

# Completion finale (stage done): waves, black, then the show wipes in.
FINALE_WAVES = 3
FINALE_WAVE_PERIOD = 1.8  # quick succession — not the stately 7s ring
FINALE_BLACK = 1.2  # a beat of darkness before the show
FINALE_WIPE = 4.5  # seconds for the phi wipe, apex to rim
_WIPE_SOFT = np.radians(9.0)  # soft border width of the wipe, in phi


def board_hues(n: int) -> np.ndarray:
    """n pleasant identity hues, equally spaced around the color wheel."""
    return (25.0 + 360.0 * np.arange(n) / max(n, 1)) % 360.0


def net_edges(geometry: dict) -> np.ndarray:
    """(e, 4) [x1 y1 x2 y2] — unique triangle edges of a net config."""
    pts = geometry["points"]
    seen = set()
    rows: List[Tuple[float, float, float, float]] = []
    for series in geometry["triangles"]:
        for tri in series:
            for k in range(3):
                a, b = sorted((tri[k], tri[(k + 1) % 3]))
                if (a, b) in seen:
                    continue
                seen.add((a, b))
                rows.append((pts[a][0], pts[a][1], pts[b][0], pts[b][1]))
    return np.asarray(rows, dtype=np.float64)


class BeadField:
    """Per-light bead intensity over time — the shared beads machinery.

    Each strut hosts one bead per lane on an independent seeded clock:
    every _BEAD_LANES[lane] seconds a bead may spawn (seeded gate) and
    live for _BEAD_LIFE seconds — fade in, crawl the whole strut
    (either direction), fade out — staggered across struts and lanes
    rather than synchronized. Both sides of a strut bind to the same
    edge, so twins match. The edge binding and seeded tables are
    precomputed once; ``field(t)`` is then pure and vectorized.
    """

    def __init__(self, xy: np.ndarray, edges: np.ndarray) -> None:
        n = xy.shape[0]
        # Per-light bead-edge projections: nearest point on each edge is
        # expensive per frame; instead each light binds to its nearest
        # edge once (mapping visuals, not a show pattern).
        p1 = edges[:, 0:2][None, :, :]
        d = edges[:, 2:4][None, :, :] - p1
        rel = xy[:, None, :] - p1
        seg_len2 = np.maximum((d**2).sum(-1), 1e-9)
        s = np.clip((rel * d).sum(-1) / seg_len2, 0.0, 1.0)
        foot = p1 + s[..., None] * d
        dist = np.linalg.norm(xy[:, None, :] - foot, axis=-1)
        self._n = n
        self._edge_of = dist.argmin(axis=1)
        rows = np.arange(n)
        self._edge_s = s[rows, self._edge_of]  # position along bound edge
        self._edge_d = dist[rows, self._edge_of]  # distance from it
        self._edge_len = np.sqrt(seg_len2[0, self._edge_of])
        # Constant seeded bead tables (per edge): a phase per lane, and a
        # small pool of per-cycle randomness (gate, direction, spare).
        e = edges.shape[0]
        self._bead_phase = [
            seeded_random(f"map-bead-phase-{lane}", e)
            for lane in range(len(_BEAD_LANES))
        ]
        self._bead_r = [
            seeded_random(f"map-bead-{lane}", e * _BEAD_CYCLES * 3).reshape(
                e, _BEAD_CYCLES, 3
            )
            for lane in range(len(_BEAD_LANES))
        ]

    def __call__(self, t: float) -> np.ndarray:
        out = np.zeros(self._n)
        eo = self._edge_of
        for lane, period in enumerate(_BEAD_LANES):
            clock = t / period + self._bead_phase[lane][eo]
            cycle = np.floor(clock).astype(np.int64)
            # The bead lives in the first _BEAD_LIFE seconds of its
            # cycle; u runs 0..1 over that life and past 1 for the dark
            # remainder (the envelope clips it to nothing).
            u = (clock - cycle) * (period / _BEAD_LIFE)
            r = self._bead_r[lane][eo, cycle % _BEAD_CYCLES]
            gate = r[:, 0] < 0.65  # a random subset of struts each cycle
            forward = r[:, 1] < 0.5
            uu = np.where(forward, u, 1.0 - u)
            margin = 8.0 / self._edge_len  # enter/exit past the ends
            center = -margin + (1.0 + 2.0 * margin) * uu
            env = np.sin(0.5 * np.pi * np.clip(np.minimum(u, 1.0 - u) / 0.18, 0, 1))
            along = (self._edge_s - center) * self._edge_len
            profile = np.exp(-(along**2) / (2 * 6.0**2))
            across = np.exp(-(self._edge_d**2) / (2 * 5.0**2))
            out = np.maximum(out, gate * env**2 * profile * across)
        return out


class MappingPattern(Pattern):
    """Composite renderer for one snapshot of the mapping state.

    All fields live on the net (``net_*`` arrays, one row per net
    capture light); ``roles`` and ``ref`` are per *rendered* light —
    the window passes ``ref = arange(n_net)``, the wire passes each
    hypothesis LED's reference net light. See the module docstring:
    this shape makes window/wire divergence structurally impossible.
    """

    name = "mapping"
    description = "Deployment mapping visuals (session-managed)"

    def __init__(
        self,
        roles: np.ndarray,  # (n,) ints, per rendered light
        ref: np.ndarray,  # (n,) reference net-light index per light
        net_xy: np.ndarray,  # (nb, 2) net capture positions
        edges: np.ndarray,  # (e, 4) net edges for the beads backdrop
        net_anchor: np.ndarray,  # (nb, 2) each net light's board-vertex anchor
        net_hue: np.ndarray,  # (nb,) each net light's board hue
        net_phi: np.ndarray,  # (nb,) radians, for RING
    ) -> None:
        self._roles = roles
        self._ref = ref
        self._net_phi = net_phi
        self._beads_field = BeadField(net_xy, edges)
        rel = net_xy - net_anchor
        self._net_ang = np.arctan2(rel[:, 1], rel[:, 0])
        self._net_az = np.degrees(np.arctan2(net_xy[:, 0], -net_xy[:, 1]))
        self._net_hue = net_hue

    # ------------------------------------------------- net-side layers

    def _wheel(self, t: float) -> Tuple[np.ndarray, np.ndarray]:
        """(intensity, hue) of the orientation test, on the net. Hue is
        the net light's angle about its board's home vertex — pure logical
        position, one continuous wheel per board — and the dark
        windmill's three spokes sweep clockwise in the net frame at
        _BAND_PERIOD."""
        hue = np.degrees(self._net_ang) % 360.0
        band = 2.0 * np.pi * (t / _BAND_PERIOD)
        pitch = 2.0 * np.pi / _SPOKES
        diff = np.mod(self._net_ang - band, pitch)
        diff = np.minimum(diff, pitch - diff)  # to the nearest spoke
        dark = 1.0 - 0.85 * np.exp(-(diff**2) / (2 * 0.30**2))
        return dark, hue

    def _ring(self, t: float) -> Tuple[np.ndarray, np.ndarray]:
        """(intensity, hue) of the descending elevation ring, on the
        net; each wave rotates the hue wheel by a seeded random angle."""
        wave = int(t // _RING_PERIOD)
        phase = (t % _RING_PERIOD) / _RING_PERIOD
        target = phase * np.radians(130.0)  # apex past the panel rim
        diff = self._net_phi - target
        intensity = np.exp(-(diff**2) / (2 * np.radians(6.0) ** 2))
        spin = 360.0 * float(seeded_random(f"map-ring-{wave}", 1)[0])
        hue = (self._net_az + spin) % 360.0
        return intensity, hue

    # ---------------------------------------------------------- render

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        ref = self._ref
        roles = self._roles
        n = roles.shape[0]
        out = np.zeros((n, 3))

        beads = self._beads_field(t)[ref]
        out[:, 0] = 0.035 + 0.30 * beads
        out[:, 1] = 0.03 + 0.02 * (1.0 - beads)  # beads run near-white
        out[:, 2] = 250.0

        m = roles == BREATHE
        if m.any():
            breathe = 0.5 - 0.5 * np.cos(2 * np.pi * t / _BREATHE_PERIOD)
            out[m, 0] = 0.10 + 0.50 * breathe
            out[m, 1] = 0.16
            out[m, 2] = self._net_hue[ref][m]

        m = roles == SOLID
        if m.any():
            out[m, 0] = 0.32
            out[m, 1] = 0.14
            out[m, 2] = self._net_hue[ref][m]

        wheel_m = (roles == WHEEL_FULL) | (roles == WHEEL_DIM)
        if wheel_m.any():
            dark, hue = self._wheel(t)
            dark, hue = dark[ref], hue[ref]
            wgain = np.where(roles == WHEEL_FULL, 1.0, _WHEEL_DIM_GAIN)
            out[wheel_m, 0] = (0.05 + 0.55 * dark[wheel_m]) * wgain[wheel_m]
            out[wheel_m, 1] = 0.30
            out[wheel_m, 2] = hue[wheel_m]

        m = roles == OFF
        if m.any():
            out[m, 0] = 0.02
            out[m, 1] = 0.02
            out[m, 2] = 250.0

        ring_m = roles == RING
        if ring_m.any():
            intensity, hue = self._ring(t)
            intensity, hue = intensity[ref], hue[ref]
            base = 0.035 + 0.30 * beads[ring_m]
            out[ring_m, 0] = np.maximum(base, 0.05 + 0.6 * intensity[ring_m])
            lit = intensity[ring_m] > 0.12
            out[ring_m, 1] = np.where(lit, 0.30, 0.03)
            out[ring_m, 2] = np.where(lit, hue[ring_m], 250.0)

        out[:, 0] = np.clip(out[:, 0], 0.0, 0.9)
        out[:, 1] = np.clip(out[:, 1], 0.0, 0.34)
        out[:, 2] = np.mod(out[:, 2], 360.0)
        return out


class FinalePattern(Pattern):
    """The completion sequence, then the show. When the last panel is
    recorded, both surfaces play three rainbow waves in quick
    succession over the still-running beads backdrop — the last wave
    sweeps the beads out behind its front — then hold black for a beat,
    and then run the ``spiral`` pattern masked by a soft-bordered wipe
    through PHI_S, apex to rim — after which the show simply plays.

    Everything (waves, beads, the show itself) is composed on the net
    lights and gathered through ``ref``, so both surfaces are the same
    broadcast to the last bit. Pure in ``(lights, t)`` for a fixed
    construction: ``t0`` — the session-clock moment the mapping
    completed — is a construction parameter, exactly like the session's
    other instance swaps. A session resumed directly into the done
    stage replays the finale from its own start (t0=0).
    """

    name = "mapping-finale"
    description = "Mapping complete: three waves, black, spiral wipe-in"

    def __init__(
        self,
        show: Pattern,
        net_lights: np.ndarray,  # the full net capture array, for the show
        net_xy: np.ndarray,  # (nb, 2)
        net_phi: np.ndarray,  # (nb,) radians
        edges: np.ndarray,  # (e, 4) — the beads keep playing
        ref: np.ndarray,  # (n,) reference net-light index per light
        t0: float,
    ) -> None:
        self._show = show
        self._net_lights = net_lights
        self._net_phi = net_phi
        self._net_az = np.degrees(np.arctan2(net_xy[:, 0], -net_xy[:, 1]))
        self._beads_field = BeadField(net_xy, edges)
        self._ref = ref
        self._t0 = t0
        self._phi_lo = float(np.nanmin(net_phi))
        self._phi_hi = float(np.nanmax(net_phi))

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        nb = self._net_phi.shape[0]
        dt = max(0.0, t - self._t0)
        waves_end = FINALE_WAVES * FINALE_WAVE_PERIOD
        if dt < waves_end:
            wave = int(dt // FINALE_WAVE_PERIOD)
            phase = (dt % FINALE_WAVE_PERIOD) / FINALE_WAVE_PERIOD
            target = phase * np.radians(130.0)
            intensity = np.exp(
                -((self._net_phi - target) ** 2) / (2 * np.radians(6.0) ** 2)
            )
            spin = 360.0 * float(seeded_random(f"map-finale-{wave}", 1)[0])
            hue = (self._net_az + spin) % 360.0
            # The beads have been playing the whole time (same session
            # clock, so the backdrop is continuous into the finale); the
            # last wave clears them out behind its front.
            beads = self._beads_field(t)
            keep = np.ones(nb)
            if wave == FINALE_WAVES - 1:
                keep = np.clip((self._net_phi - target) / np.radians(4.0), 0.0, 1.0)
            out = np.zeros((nb, 3))
            out[:, 0] = np.maximum((0.035 + 0.30 * beads) * keep, 0.65 * intensity)
            lit = intensity > 0.12
            out[:, 1] = np.where(lit, 0.30, (0.03 + 0.02 * (1.0 - beads)) * keep)
            out[:, 2] = np.where(lit, hue, 250.0)
            waves: np.ndarray = out[self._ref]
            return waves
        if dt < waves_end + FINALE_BLACK:
            return np.zeros((self._ref.shape[0], 3))
        out = np.asarray(
            self._show.render(self._net_lights, t), dtype=np.float64
        ).copy()
        out = np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)
        wipe_t = dt - waves_end - FINALE_BLACK
        if wipe_t < FINALE_WIPE:
            # The reveal edge sweeps top (phi_lo) to bottom, starting and
            # ending a soft-border past the ends so 0% and 100% are real.
            span = self._phi_hi - self._phi_lo + 2 * _WIPE_SOFT
            edge = self._phi_lo - _WIPE_SOFT + span * (wipe_t / FINALE_WIPE)
            x = np.clip((edge - self._net_phi) / _WIPE_SOFT + 1.0, 0.0, 1.0)
            mask = x * x * (3.0 - 2.0 * x)  # smoothstep: the soft border
            out[:, 0] *= mask
            out[:, 1] *= mask
        shown: np.ndarray = out[self._ref]
        return shown

"""Mapping-mode renderers: one composite pattern, driven by per-light roles.

The same class renders the base-station window (true net capture
positions) and the wire (hypothesis strip positions): construction takes
per-light annotation arrays, so the pattern itself never knows which
surface it is on. Role assignment happens in the session/builders; this
module only turns (roles, geometry, t) into OKLCH — pure and vectorized,
stateless for a fixed construction (the session swaps instances when the
mapping state changes, exactly like a WS set_pattern).

Visual language (plan/mapping/DESCRIPTION.md):
  BEADS        gentle white beads drifting along strut straightaways,
               mirrored across each strut — the pre-mapping backdrop.
  BREATHE      slow single-color breathing (stage A: full = the board
               being placed, half = boards already locked).
  WHEEL        the orientation test: a sixth of a color wheel about the
               panel's six-red corner with a dark band sweeping
               clockwise (net frame); half brightness once confirmed.
  RING         the mapped pattern: a hue ring descending in elevation
               (PHI_S) every few seconds, over the beads backdrop.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import numpy as np

from luminary.patterns.base import Pattern
from luminary.patterns.util import seeded_random

# Per-light roles
BEADS = 0
BREATHE_FULL = 1
BREATHE_HALF = 2
WHEEL_FULL = 3
WHEEL_HALF = 4
RING = 5

_BREATHE_PERIOD = 2.6  # seconds; calm but clearly alive
_BAND_PERIOD = 3.0  # seconds per revolution of the wheel's dark band
_RING_PERIOD = 7.0  # seconds per apex-to-rim descent
_BEAD_SLOT = 2.4  # seconds per spawn slot per edge


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


class MappingPattern(Pattern):
    """Composite renderer for one snapshot of the mapping state."""

    name = "mapping"
    description = "Deployment mapping visuals (session-managed)"

    def __init__(
        self,
        xy: np.ndarray,  # (n, 2) net-plane positions
        roles: np.ndarray,  # (n,) ints from the role constants above
        edges: np.ndarray,  # (e, 4) net edges for the beads backdrop
        corner_xy: Optional[np.ndarray] = None,  # (n, 2) six-red corner
        winding_sign: Optional[np.ndarray] = None,  # (n,) +1 ccw / -1 cw
        phi_s: Optional[np.ndarray] = None,  # (n,) radians, for RING
        breathe_hue: float = 200.0,
    ) -> None:
        n = xy.shape[0]
        self._xy = xy
        self._roles = roles
        self._edges = edges
        self._corner = corner_xy if corner_xy is not None else np.zeros((n, 2))
        self._wind = winding_sign if winding_sign is not None else np.ones(n)
        self._phi = phi_s
        self._hue = breathe_hue
        # Precompute per-light bead-edge projections: nearest point on
        # each edge is expensive per frame; instead each light binds to
        # its nearest edge once (mapping visuals, not a show pattern).
        p1 = self._edges[:, 0:2][None, :, :]
        d = self._edges[:, 2:4][None, :, :] - p1
        rel = xy[:, None, :] - p1
        seg_len2 = np.maximum((d**2).sum(-1), 1e-9)
        s = np.clip((rel * d).sum(-1) / seg_len2, 0.0, 1.0)
        foot = p1 + s[..., None] * d
        dist = np.linalg.norm(xy[:, None, :] - foot, axis=-1)
        self._edge_of = dist.argmin(axis=1)
        rows = np.arange(n)
        self._edge_s = s[rows, self._edge_of]  # position along bound edge
        self._edge_d = dist[rows, self._edge_of]  # distance from it
        self._edge_len = np.sqrt(seg_len2[0, self._edge_of])

    # ---------------------------------------------------------- layers

    def _beads(self, t: float) -> np.ndarray:
        """Per-light bead intensity: beads spawn per edge in hashed time
        slots, glide a short way along the edge, grow and fade. Both
        sides of a strut bind to the same edge, so twins match."""
        n = self._xy.shape[0]
        out = np.zeros(n)
        for slot in (int(t / _BEAD_SLOT) - 1, int(t / _BEAD_SLOT)):
            if slot < 0:
                continue
            r = seeded_random(f"map-bead-{slot}", self._edges.shape[0] * 3)
            r = r.reshape(-1, 3)
            gate = r[self._edge_of, 0]
            s0 = 0.15 + 0.6 * r[self._edge_of, 1]
            drift = (r[self._edge_of, 2] - 0.5) * 0.25
            rel = (t - slot * _BEAD_SLOT) / _BEAD_SLOT
            if not 0.0 <= rel <= 2.0:
                continue
            env = np.sin(np.clip(rel / 1.6, 0.0, 1.0) * np.pi) ** 2
            center = s0 + drift * rel
            along = (self._edge_s - center) * self._edge_len
            profile = np.exp(-(along**2) / (2 * 6.0**2))
            across = np.exp(-(self._edge_d**2) / (2 * 5.0**2))
            out = np.maximum(out, (gate < 0.5) * env * profile * across)
        return out

    def _wheel(self, t: float) -> Tuple[np.ndarray, np.ndarray]:
        """(intensity, hue) of the orientation test about each light's
        own corner. Hue spans the wheel with angle; the dark band sweeps
        clockwise in the net frame at _BAND_PERIOD."""
        rel = self._xy - self._corner
        ang = np.arctan2(rel[:, 1], rel[:, 0]) * self._wind
        hue = (np.degrees(ang)) % 360.0
        band = 2.0 * np.pi * (t / _BAND_PERIOD)
        diff = np.mod(ang - band + np.pi, 2 * np.pi) - np.pi
        dark = 1.0 - 0.85 * np.exp(-(diff**2) / (2 * 0.35**2))
        return dark, hue

    def _ring(self, t: float) -> Tuple[np.ndarray, np.ndarray]:
        """(intensity, hue) of the descending elevation ring."""
        n = self._xy.shape[0]
        if self._phi is None:
            return np.zeros(n), np.zeros(n)
        phase = (t % _RING_PERIOD) / _RING_PERIOD
        target = phase * np.radians(130.0)  # apex past the panel rim
        diff = self._phi - target
        intensity = np.exp(-(diff**2) / (2 * np.radians(6.0) ** 2))
        # Hue varies around the ring: azimuth about the apex.
        hue = (np.degrees(np.arctan2(self._xy[:, 0], -self._xy[:, 1]))) % 360.0
        return intensity, hue

    # ---------------------------------------------------------- render

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n = self._xy.shape[0]
        out = np.zeros((n, 3))
        roles = self._roles

        beads = self._beads(t)
        out[:, 0] = 0.035 + 0.30 * beads
        out[:, 1] = 0.03 + 0.02 * (1.0 - beads)  # beads run near-white
        out[:, 2] = 250.0

        breathe = 0.5 - 0.5 * np.cos(2 * np.pi * t / _BREATHE_PERIOD)
        for role, gain in ((BREATHE_FULL, 1.0), (BREATHE_HALF, 0.5)):
            m = roles == role
            if m.any():
                out[m, 0] = 0.06 + 0.55 * gain * breathe
                out[m, 1] = 0.24
                out[m, 2] = self._hue

        wheel_m = (roles == WHEEL_FULL) | (roles == WHEEL_HALF)
        if wheel_m.any():
            dark, hue = self._wheel(t)
            wgain = np.where(roles == WHEEL_FULL, 1.0, 0.5)
            out[wheel_m, 0] = (0.05 + 0.55 * dark[wheel_m]) * wgain[wheel_m]
            out[wheel_m, 1] = 0.30
            out[wheel_m, 2] = hue[wheel_m]

        ring_m = roles == RING
        if ring_m.any():
            intensity, hue = self._ring(t)
            base = 0.035 + 0.30 * beads[ring_m]
            out[ring_m, 0] = np.maximum(base, 0.05 + 0.6 * intensity[ring_m])
            lit = intensity[ring_m] > 0.12
            out[ring_m, 1] = np.where(lit, 0.30, 0.03)
            out[ring_m, 2] = np.where(lit, hue[ring_m], 250.0)

        out[:, 0] = np.clip(out[:, 0], 0.0, 0.9)
        out[:, 1] = np.clip(out[:, 1], 0.0, 0.34)
        out[:, 2] = np.mod(out[:, 2], 360.0)
        return out

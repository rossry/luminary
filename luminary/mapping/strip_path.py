"""Where LED *i* of *n* sits on a panel, and which net light it references.

This is the bridge between a physical strip and the designed net, and it is
deliberately one implementation. The mapping session uses it to light
hypothesis LEDs while an operator confirms a panel; the production capture
uses it to assign real ``(controller, channel, index)`` identities from the
records that session wrote. If those two disagreed, a deployment would render
differently from the tool that mapped it — a production-divergence bug of
exactly the kind CLAUDE.md's "one logic path" rule exists to prevent.

The path itself (plan/mapping/DESCRIPTION.md "The strip path"): from the
panel's six-red corner, half-edge, radial in, radial out, finish the edge —
three times, back to the start. Twelve legs.
"""

from __future__ import annotations

from typing import Dict, Tuple

import numpy as np

from luminary.mapping.plan import PanelPlan


def tri_of_lights(net_geometry: dict, xy: np.ndarray) -> np.ndarray:
    """(n,) triangle index per light by point location (capture order is
    not triangle-contiguous after the canonical identity sort)."""
    pts = net_geometry["points"]
    tris = [t for series in net_geometry["triangles"] for t in series]
    out = np.full(xy.shape[0], -1, dtype=np.int64)
    for idx, tri in enumerate(tris):
        (x0, y0), (x1, y1), (x2, y2) = ((pts[i][0], pts[i][1]) for i in tri)
        det = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        l0 = ((y1 - y2) * (xy[:, 0] - x2) + (x2 - x1) * (xy[:, 1] - y2)) / det
        l1 = ((y2 - y0) * (xy[:, 0] - x2) + (x0 - x2) * (xy[:, 1] - y2)) / det
        l2 = 1.0 - l0 - l1
        inside = (l0 > -1e-6) & (l1 > -1e-6) & (l2 > -1e-6) & (out < 0)
        out[inside] = idx
    assert (out >= 0).all(), "unlocated lights"
    return out


class StripPaths:
    """Panel strip paths over one net's capture, with per-panel caches."""

    def __init__(self, net_geometry: dict, net_xy: np.ndarray) -> None:
        self.net_geometry = net_geometry
        self.net_xy = net_xy
        self.net_tri = tri_of_lights(net_geometry, net_xy)
        self._path_cache: Dict[int, Tuple[np.ndarray, np.ndarray]] = {}
        self._frac_cache: Dict[int, Tuple[np.ndarray, np.ndarray]] = {}

    def panel_path(self, panel: PanelPlan) -> Tuple[np.ndarray, np.ndarray]:
        """(points (13,2), cumulative arclength (13,)) of the panel's
        physical strip path, ccw: start corner → half-edge → radial in
        → radial out → finish edge, then the far edge, then the third,
        back to the start corner."""
        cached = self._path_cache.get(panel.tri_index)
        if cached is not None:
            return cached
        pts = self.net_geometry["points"]
        tris = [t for s in self.net_geometry["triangles"] for t in s]
        tri = tris[panel.tri_index]
        corner = np.asarray(panel.corner_xy)
        vs = [np.asarray(pts[i][:2], dtype=np.float64) for i in tri]
        k = next(i for i, v in enumerate(vs) if np.allclose(v, corner))
        v1, va, vb = vs[k], vs[(k + 1) % 3], vs[(k + 2) % 3]
        # ccw: walk the boundary counterclockwise in the net frame.
        # (2-D cross product spelled out: numpy >= 2 removed it.)
        cross = float(
            (va[0] - v1[0]) * (vb[1] - v1[1]) - (va[1] - v1[1]) * (vb[0] - v1[0])
        )
        v2, v3 = (va, vb) if cross > 0 else (vb, va)
        o = (v1 + v2 + v3) / 3.0
        m12, m23, m31 = (v1 + v2) / 2, (v2 + v3) / 2, (v3 + v1) / 2
        path = np.stack([v1, m12, o, m12, v2, m23, o, m23, v3, m31, o, m31, v1])
        seg = np.linalg.norm(np.diff(path, axis=0), axis=1)
        cum = np.concatenate([[0.0], np.cumsum(seg)])
        self._path_cache[panel.tri_index] = (path, cum)
        return path, cum

    def strip_xy(self, panel: PanelPlan, density: int, winding: str) -> np.ndarray:
        """Position of LED i of n: arclength (i+0.5)/n along the
        serpentine; cw walks the same path the other way."""
        path, cum = self.panel_path(panel)
        total = float(cum[-1])
        s = (np.arange(density) + 0.5) / density * total
        if winding == "cw":
            s = total - s
        seg_idx = np.clip(np.searchsorted(cum, s, side="right") - 1, 0, 11)
        seg_len = np.maximum(cum[seg_idx + 1] - cum[seg_idx], 1e-9)
        f = ((s - cum[seg_idx]) / seg_len)[:, None]
        arc: np.ndarray = path[seg_idx] + f * (path[seg_idx + 1] - path[seg_idx])
        return arc

    def strip_refs(self, panel: PanelPlan, density: int, winding: str) -> np.ndarray:
        """Reference net light per strip LED — the single bridge that lets
        every field render net-side (render.MappingPattern) and lets the
        production capture inherit each beam's display shape: LED i of n is
        the light at the matching *rank* along the serpentine (capture
        lights sorted by path fraction), so at the panel's native density
        the mapping is an exact bijection and at double density each light
        is referenced twice — no dark skipped-light holes, robust to the
        strips' offset from the centerline path."""
        idx, frac = self.panel_path_frac(panel)
        order = idx[np.argsort(frac, kind="stable")]
        pos = np.floor((np.arange(density) + 0.5) / density * order.size)
        refs = order[np.clip(pos.astype(np.int64), 0, order.size - 1)]
        if winding == "cw":
            refs = refs[::-1]
        return np.asarray(refs)

    def panel_path_frac(self, panel: PanelPlan) -> Tuple[np.ndarray, np.ndarray]:
        """(light indices, path fraction) for the panel's capture lights:
        each light's fraction along the ccw serpentine — the window-side
        mirror of hypothesis strip index / n."""
        cached = self._frac_cache.get(panel.tri_index)
        if cached is not None:
            return cached
        path, cum = self.panel_path(panel)
        idx = np.flatnonzero(self.net_tri == panel.tri_index)
        p = self.net_xy[idx]
        a = path[:-1][None, :, :]
        d = (path[1:] - path[:-1])[None, :, :]
        len2 = np.maximum((d**2).sum(-1), 1e-9)
        tproj = np.clip(((p[:, None, :] - a) * d).sum(-1) / len2, 0.0, 1.0)
        foot = a + tproj[..., None] * d
        dist = ((p[:, None, :] - foot) ** 2).sum(-1)
        best = dist.argmin(axis=1)
        rows = np.arange(idx.size)
        s = cum[best] + tproj[rows, best] * np.sqrt(len2[0, best])
        result = (idx, s / float(cum[-1]))
        self._frac_cache[panel.tri_index] = result
        return result

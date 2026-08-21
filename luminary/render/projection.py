"""World -> 2D screen layout, shared by SVG and the Canvas client (spec §14.4).

One projection rule: the viewBox and per-light draw data are computed here and
delivered to every renderer — the server-side SVG and the browser Canvas place
lights identically.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np

from luminary.geometry.lights import Kind, LightColumns, LightsGeometry
from luminary.geometry.scaffold import Scaffold


def viewbox_from_points(
    points_xy: np.ndarray, pad_fraction: float = 0.06
) -> Tuple[float, float, float, float]:
    """(min_x, min_y, width, height) with symmetric padding."""
    finite = points_xy[np.all(np.isfinite(points_xy), axis=1)]
    if finite.shape[0] == 0:
        return (0.0, 0.0, 1.0, 1.0)
    lo = finite.min(axis=0)
    hi = finite.max(axis=0)
    span = np.maximum(hi - lo, 1e-6)
    pad = span * pad_fraction
    lo = lo - pad
    span = span + 2 * pad
    return (float(lo[0]), float(lo[1]), float(span[0]), float(span[1]))


def lights_layout(
    lights: LightsGeometry, scaffold: Optional[Scaffold] = None
) -> Dict[str, Any]:
    """The client draw layout (spec §14.3.1, served by /api/lights/{id}/layout).

    Includes everything the canvas needs to build its draw list once:
    per-light identity, kind, weight, XY position, optional display polygon
    (spec §6.5.3), plus the viewBox and optional scaffold lines to underlay.
    """
    arr = lights.array
    points = arr[:, [LightColumns.X, LightColumns.Y]]
    all_points = [points]
    scaffold_lines = []
    if scaffold is not None:
        all_points.extend([scaffold.p1_xy, scaffold.p2_xy])
        scaffold_lines = [
            {
                "p1": [float(v) for v in scaffold.p1_xy[i]],
                "mid": [float(v) for v in scaffold.mid_xy[i]],
                "p2": [float(v) for v in scaffold.p2_xy[i]],
            }
            for i in range(scaffold.n_lines)
        ]
    for entry in lights.display:
        if entry:
            all_points.append(np.asarray(entry, dtype=np.float64))
    viewbox = viewbox_from_points(np.concatenate(all_points, axis=0))

    entries = []
    for row in range(lights.n):
        weight = arr[row, LightColumns.WEIGHT]
        dx = arr[row, LightColumns.DX]
        dy = arr[row, LightColumns.DY]
        entries.append(
            {
                "controller": int(arr[row, LightColumns.CONTROLLER]),
                "channel": int(arr[row, LightColumns.CHANNEL]),
                "index": int(arr[row, LightColumns.INDEX]),
                "kind": int(arr[row, LightColumns.KIND]),
                "x": _num(arr[row, LightColumns.X]),
                "y": _num(arr[row, LightColumns.Y]),
                # Emission direction in the layout plane (unit XY, spec §7.3.1);
                # lets renderers model the physical throw (strips face inward).
                "dir": None if np.isnan(dx) else [float(dx), float(dy)],
                "weight": None if np.isnan(weight) else float(weight),
                "display": lights.display[row],
            }
        )
    return {
        "viewBox": list(viewbox),
        "lights": entries,
        "scaffold": scaffold_lines,
        "overlays": lights.meta.get("overlays"),
        "counts": {
            "total": lights.n,
            "active": int(np.sum(arr[:, LightColumns.KIND] == Kind.ACTIVE)),
            "interpolated": int(np.sum(arr[:, LightColumns.KIND] == Kind.INTERPOLATED)),
            "inactive": int(np.sum(arr[:, LightColumns.KIND] == Kind.INACTIVE)),
        },
    }


def scaffold_layout(scaffold: Scaffold) -> Dict[str, Any]:
    """Draw layout for a bare scaffold view."""
    lines = [
        {
            "id": scaffold.lines[i].id,
            "p1": [float(v) for v in scaffold.p1_xy[i]],
            "mid": [float(v) for v in scaffold.mid_xy[i]],
            "p2": [float(v) for v in scaffold.p2_xy[i]],
            "normal": [float(v) for v in scaffold.normals[i, 1]],
        }
        for i in range(scaffold.n_lines)
    ]
    pts = np.concatenate([scaffold.p1_xy, scaffold.mid_xy, scaffold.p2_xy], axis=0)
    return {"viewBox": list(viewbox_from_points(pts)), "lines": lines}


def _num(value: float) -> Optional[float]:
    return None if np.isnan(value) else float(value)

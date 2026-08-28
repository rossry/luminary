"""Mapped production capture: the net design plus the recorded wiring.

`capture()` describes the *design* — one light per beam, with no idea which
board or strip drives it, so everything lands on controller 0. This module
closes that gap (spec §7.3.1, §19.6): it takes the per-board mapping records
an operator confirmed with ``luminary map`` and produces the geometry the
installation actually has, with real ``(controller, channel, index)``
identities.

One LED, one beam. At a panel's native density the strip maps onto the net's
beams one-for-one and each LED simply inherits its beam. A denser strip has
*more* beams, not LEDs doubled up on the same one, so the beam it lands in is
**subdivided** across the LEDs that share it: each gets its own slice of the
beam polygon, its own position at that slice's centre, and its own folded 3-D
coordinate. Inheriting the whole beam for both would give them identical
positions, and a pattern would then render them the same colour forever.

The strip path and the index-to-beam bridge come from
``luminary.mapping.strip_path``, shared with the mapping session — so a
deployment renders the way the tool that mapped it said it would.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from luminary.geometry.lights import LightColumns, LightsGeometry, LightSpec
from luminary.geometry.net import Net
from luminary.geometry.pentagon.adapters import build_fold, capture, folder
from luminary.mapping.plan import Plan
from luminary.mapping.state import BoardRecord
from luminary.mapping.strip_path import StripPaths

_CONFIGS = Path(__file__).resolve().parents[3] / "configs"


class MappingIncompleteError(ValueError):
    """The records do not describe a drivable installation."""


def _slice_polygon(
    poly: List[List[float]], axis: np.ndarray, lo: float, hi: float
) -> List[List[float]]:
    """The part of a convex polygon whose projection on ``axis`` is in
    [lo, hi] — Sutherland-Hodgman against two parallel half-planes."""
    current = [np.asarray(v, dtype=np.float64) for v in poly]
    for keep_above, bound in ((True, lo), (False, hi)):
        if not current:
            return []
        clipped: List[np.ndarray] = []
        for i, a in enumerate(current):
            b = current[(i + 1) % len(current)]
            pa = float(a @ axis) - bound
            pb = float(b @ axis) - bound
            if not keep_above:
                pa, pb = -pa, -pb
            if pa >= 0:
                clipped.append(a)
            if (pa >= 0) != (pb >= 0):
                t = pa / (pa - pb) if pa != pb else 0.0
                clipped.append(a + t * (b - a))
        current = clipped
    return [[float(v[0]), float(v[1])] for v in current]


def _centroid(poly: List[List[float]]) -> Tuple[float, float]:
    pts = np.asarray(poly, dtype=np.float64)
    return float(pts[:, 0].mean()), float(pts[:, 1].mean())


def _subdivide(
    poly: List[List[float]], axis: np.ndarray, parts: int
) -> List[List[List[float]]]:
    """Cut a beam polygon into ``parts`` slices across ``axis``.

    Equal extent along the strip direction, which is how the LEDs are
    spaced. A slice that degenerates (a sliver at a polygon tip) falls back
    to the whole polygon rather than producing a light with no shape.
    """
    pts = np.asarray(poly, dtype=np.float64)
    proj = pts @ axis
    lo, hi = float(proj.min()), float(proj.max())
    if parts < 2 or hi - lo < 1e-9:
        return [poly for _ in range(parts)]
    edges = [lo + (hi - lo) * i / parts for i in range(parts + 1)]
    out = []
    for i in range(parts):
        piece = _slice_polygon(poly, axis, edges[i], edges[i + 1])
        out.append(piece if len(piece) >= 3 else poly)
    return out


def capture_mapped(
    net: Net,
    plan: Plan,
    boards: Dict[int, BoardRecord],
    *,
    net_lights: Optional[LightsGeometry] = None,
    strict: bool = True,
    interpolate_dense: bool = False,
) -> LightsGeometry:
    """Net + mapping records -> the deployed geometry.

    ``strict`` refuses a partial mapping. Turn it off to drive whatever has
    been mapped so far — useful mid-commissioning, and honest about what it
    is: the unmapped panels are simply absent, so they stay dark.

    ``interpolate_dense`` carries a subdivided beam as one ACTIVE light plus
    INTERPOLATED neighbours, so a 360-LED strip costs 180 lights on the wire
    and the board reconstructs the rest (§11.7.3). Measured on a Feather
    SCORPIO driving 6 x 360: it takes the ACK round trip's p95 from 33.2 ms
    to 16.8 ms against a 33.3 ms frame interval — the difference between
    running at the edge and running with margin — while also cutting wire
    bytes 35% and host encode time 23%. Native-density strips are unaffected,
    since there is nothing to subdivide.
    """
    net_lights = net_lights if net_lights is not None else capture(net)
    geometry = json.loads((_CONFIGS / f"{plan.net_name}.json").read_text())["geometry"]
    xy = net_lights.array[:, [LightColumns.X, LightColumns.Y]]
    strips = StripPaths(geometry, xy)

    # Reuse the serialized form: it already carries each beam's display
    # polygon, throw direction, extent, and folded 3-D position, so a strip
    # LED inherits the full description of the beam it lights.
    source_rows = net_lights.to_file_dict()["lights"]
    fold = folder(build_fold(net))

    mapped: List[LightSpec] = []
    seen: Dict[int, int] = {}
    for unit in plan.units:
        record = boards.get(unit)
        # Recorded absent is a decision, not a gap: the board is not on the
        # sphere for this run, so it contributes no lights and strict mode has
        # nothing to complain about.
        if record is not None and record.absent:
            continue
        if record is None or record.controller_id is None:
            if strict:
                raise MappingIncompleteError(
                    f"unit {unit} has no controller locked; run `luminary map` "
                    "(or press x there to record it absent)"
                )
            continue
        controller = record.controller_id
        if controller in seen and seen[controller] != unit:
            raise MappingIncompleteError(
                f"controller {controller} is claimed by units "
                f"{seen[controller]} and {unit}"
            )
        seen[controller] = unit

        expected = len(
            [p for p in plan.panels[unit] if p.face not in record.absent_faces]
        )
        if strict and len(record.channels) != expected:
            raise MappingIncompleteError(
                f"unit {unit} (controller {controller}) has "
                f"{len(record.channels)}/{expected} panels mapped "
                "(press x while mapping to record one absent)"
            )

        for channel, channel_record in sorted(record.channels.items()):
            panel = plan.by_face[channel_record.face]
            density, winding = channel_record.density, channel_record.winding
            refs = strips.strip_refs(panel, density, winding)
            xy = strips.strip_xy(panel, density, winding)

            # LEDs sharing a beam are consecutive along the strip, so the
            # beam is split across exactly that run.
            for start, stop, ref in _runs(refs):
                entry = dict(source_rows[int(ref)])
                parts = stop - start
                poly = entry.get("display")
                slices: List[Optional[List[List[float]]]]
                if parts > 1 and poly:
                    axis = _strip_axis(xy, start, stop)
                    slices = list(_subdivide(poly, axis, parts))
                else:
                    slices = [poly] * parts
                for offset in range(parts):
                    piece = dict(entry)
                    piece["controller"] = controller
                    piece["channel"] = channel
                    piece["index"] = start + offset
                    if interpolate_dense and parts > 1 and offset > 0:
                        # The strip's last light must stay ACTIVE: an
                        # INTERPOLATED light needs an ACTIVE one on each side
                        # to interpolate between.
                        if start + offset != len(refs) - 1:
                            piece["kind"] = "interpolated"
                    shape = slices[offset]
                    if parts > 1 and shape:
                        cx, cy = _centroid(shape)
                        piece["display"] = shape
                        piece["pos"] = [cx, cy]
                        folded = fold(panel.tri_index, cx, cy)
                        if folded is not None:
                            piece["pos3"] = folded
                        elif "pos3" in piece:
                            del piece["pos3"]
                    mapped.append(LightSpec.model_validate(piece))

    if not mapped:
        raise MappingIncompleteError(
            "no panels are mapped; run `luminary map` before building geometry"
        )

    meta = dict(net_lights.meta)
    meta["name"] = f"{plan.net_name}-mapped"
    meta["mapped"] = {
        "controllers": sorted(seen),
        "panels": sum(len(b.channels) for b in boards.values() if b is not None),
        "lights": len(mapped),
    }
    source = dict(net_lights.source)
    source["type"] = "pentagon-mapped"
    source["net"] = plan.net_name
    return LightsGeometry.from_specs(
        mapped, space=net_lights.space, source=source, meta=meta
    )


def _runs(refs: "np.ndarray") -> List[Tuple[int, int, int]]:
    """(start, stop, value) for each run of equal consecutive refs."""
    out: List[Tuple[int, int, int]] = []
    start = 0
    for i in range(1, len(refs) + 1):
        if i == len(refs) or refs[i] != refs[start]:
            out.append((start, i, int(refs[start])))
            start = i
    return out


def _strip_axis(xy: "np.ndarray", start: int, stop: int) -> "np.ndarray":
    """Unit direction the strip runs through one beam.

    Taken from the LED positions themselves, so a beam is cut across the
    strip's actual travel rather than an assumed orientation.
    """
    if stop - start >= 2:
        delta = xy[stop - 1] - xy[start]
    else:
        delta = xy[min(stop, len(xy) - 1)] - xy[start]
    norm = float(np.linalg.norm(delta))
    if norm < 1e-9:
        return np.array([1.0, 0.0])
    return np.asarray(delta / norm)

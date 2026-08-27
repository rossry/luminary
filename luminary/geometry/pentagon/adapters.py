"""Adapters from the pentagon Net to scaffold / lights geometry."""

from __future__ import annotations

import math
from typing import List, Optional, Set, Tuple

from luminary.geometry.lights import (
    MAX_CHANNELS,
    LightsGeometry,
    LightSpec,
    SpaceSpec,
)
from luminary.geometry.net import Net
from luminary.geometry.scaffold import LineSpec, Scaffold
from luminary.geometry.triangle import Triangle

# How far the illuminated panel stops short of the structural triangle, in
# physical inches, measured perpendicular to the strut *centerline* (the frame
# lines run vertex to vertex, so that is what they are). The lit cloth+PVC+LED
# triangle is mounted inside the metal frame, so neighbouring lit panels end up
# 2 x this apart: the single knob for how widely spaced the lit triangles read.
#
# Measured from one build photo, self-scaled so camera geometry cancels:
# across a panel seam the two LED strips sit 14.7 px apart against a
# 279.5 px apex-to-apex span of two adjacent all-hexavalent faces
# (span ≈ 101"), i.e. strips 2.65" each side of the strut centerline.
# The cloth edge sits one pipe OD inside the strip line: 2.65" − OD ≈ 1.5".
#
# Render fidelity only — this moves the per-light ``display`` polygons
# (spec §6.5.3) and the ``panel`` / ``pvc_panel`` overlays, never a light's
# position, identity, or anything on the wire.
PANEL_INSET_INCHES = 1.5

# World-units-per-inch calibration, mirroring the clients: a net's mean edge
# length in world units maps to this many inches, fixing the scale of that net.
#
# This is a net-world-to-inches conversion, not a property of the net's own
# geometry: the 2D layout is an idealization whose edges fall in three classes
# (50.0 / 53.52 / 56.46 world, ratio 1.129) that do NOT correspond class-for-
# class to the sphere's struts (A 50.25" / B 58.125" / C 59.375", ratio 1.182).
# So the scale has to come from the physical struts the panels actually mount
# on. Those are all class B or C — the installed faces avoid the pentagon-tip
# A struts entirely — giving 58.85" over 4A-33's 62 struts and 58.88" over
# 4A-37's 70. Derived from the panel-to-sphere-face mapping, which exists for
# those two configs only; the others are assumed to be the same family.
_MEAN_STRUT_INCHES = 58.86


def to_scaffold(net: Net) -> Scaffold:
    """Emit the Net's geometric lines (or triangle edges) as a planar scaffold.

    Preserves every existing ``configs/*.json`` as a valid scaffold source
    (spec §5.5.1) instead of inventing a second pentagon format.
    """
    lines: List[LineSpec] = []
    seen: Set[Tuple[int, int]] = set()

    explicit = net.config.geometry.lines
    if explicit:
        pairs = [tuple(sorted(pair)) for pair in explicit]
    else:
        pairs = []
        for _, triangle, _ in net.config.iter_triangles_with_ids():
            a, b, c = triangle
            pairs.extend(
                [tuple(sorted((a, b))), tuple(sorted((b, c))), tuple(sorted((c, a)))]
            )

    for i, j in pairs:
        if (i, j) in seen:
            continue
        seen.add((i, j))
        p_i, p_j = net.points[i], net.points[j]
        lines.append(
            LineSpec(
                id=f"line-{i}-{j}",
                p1=[p_i.x, p_i.y],
                p2=[p_j.x, p_j.y],
            )
        )

    return Scaffold(
        lines,
        SpaceSpec(authoritative=["xy"]),
        meta={"name": "pentagon", "source": "pentagon-net"},
    )


def _panel_shrink(triangle: Triangle, inset: float) -> Tuple[float, float, float]:
    """``(cx, cy, scale)`` that pulls a triangle's contents ``inset`` world
    units in from every edge.

    Scaling about the *incenter* — not the centroid — by ``1 - inset/inradius``
    moves all three edges inward by exactly ``inset``, for any triangle. The net's faces
    are near-equilateral but not uniformly so (a 3V geodesic has three strut
    classes; 4A-33 is 15 equilateral 50" faces plus 18 scalene
    50/53.5/56.5" ones), and only the incenter is equidistant from all three
    edges, so the gap stays even on the scalene faces.
    """
    a, b, c = triangle.vertices
    sides = [b.distance(c), c.distance(a), a.distance(b)]
    semi = sum(sides) / 2
    area = math.sqrt(
        max(0.0, semi * (semi - sides[0]) * (semi - sides[1]) * (semi - sides[2]))
    )
    inradius = area / semi if semi > 0 else 0.0
    scale = 1.0 - inset / inradius if inradius > 0 else 1.0
    inc = triangle.incenter
    return inc.x, inc.y, max(0.0, scale)


def capture(
    net: Net, channels: int = MAX_CHANNELS, controller: int = 0
) -> LightsGeometry:
    """One ACTIVE light per beam, with the beam polygon as its display shape.

    Identity mapping is DEFERRED (review §19.6): channels go round-robin per
    facet and indices count up along each channel. The physical strip path is
    now specified (plan/mapping/DESCRIPTION.md "The strip path": from the
    six-red corner — half-edge, radial in, radial out, finish the edge, times
    three, back to the start); assigning real identities along it awaits the
    per-board mapping YAMLs. This function is the single place to change when
    that lands (spec §7.3.1).
    """
    specs: List[LightSpec] = []
    next_index = {ch: 0 for ch in range(channels)}
    facet_ordinal = 0

    # Structural overlays for the renderers (spec §14.3.1): the physical piece
    # is inset cloth+PVC+LED triangles inside a metal frame, so clients draw
    # dark seams — "frame" (triangle perimeter, metal) fat, "pvc" (facet
    # boundary pipes, midpoint↔incenter) thin. World XY segments, deduped.
    frame_seen: Set[Tuple[Tuple[float, float], Tuple[float, float]]] = set()
    frame_lines: List[List[List[float]]] = []
    pvc_lines: List[List[List[float]]] = []
    tri_polys: List[List[List[float]]] = []  # per structural triangle, for hit tests
    pvc_tri: List[int] = []  # which triangle each pvc segment belongs to
    frame_total = 0.0
    for tri_index, triangle in enumerate(net.triangles):
        vs = triangle.vertices
        tri_polys.append([[v.x, v.y] for v in vs])
        for i in range(3):
            a, b = vs[i], vs[(i + 1) % 3]
            pa = (round(a.x, 6), round(a.y, 6))
            pb = (round(b.x, 6), round(b.y, 6))
            key = (pa, pb) if pa <= pb else (pb, pa)
            if key in frame_seen:
                continue
            frame_seen.add(key)
            frame_lines.append([[a.x, a.y], [b.x, b.y]])
            frame_total += a.distance(b)
        for facet in triangle.get_facets():
            _, m1, inc, m2 = facet.vertices
            pvc_lines.append([[m1.x, m1.y], [inc.x, inc.y]])
            pvc_lines.append([[inc.x, inc.y], [m2.x, m2.y]])
            pvc_tri.extend((tri_index, tri_index))

    # The illuminated panel is inset from its structural triangle by
    # PANEL_INSET_INCHES (see above). One affine per triangle — shared by the
    # beam display polygons here and, via the "panel" overlay, by the client's
    # cloth mask and LED positions — so every renderer shrinks by the same map.
    world_per_inch = (frame_total / len(frame_lines)) / _MEAN_STRUT_INCHES
    inset_world = PANEL_INSET_INCHES * world_per_inch
    panels = [_panel_shrink(triangle, inset_world) for triangle in net.triangles]

    # The pipes are part of the panel: the LED strips are mounted on them, so
    # they sit inside the metal frame with the cloth, not spanning the full
    # structural triangle. "pvc" stays in structural space because the client
    # ray-casts LED anchors against it *before* applying the panel affine;
    # "pvc_panel" is where the pipes physically are, and is what gets drawn.
    def _to_panel(t: int, p: List[float]) -> List[float]:
        cx, cy, s = panels[t]
        return [cx + (p[0] - cx) * s, cy + (p[1] - cy) * s]

    pvc_panel_lines = [
        [_to_panel(t, seg[0]), _to_panel(t, seg[1])]
        for t, seg in zip(pvc_tri, pvc_lines)
    ]

    # Fold onto the 3V sphere (spec §4.1.2 dual-authoritative): when the
    # config carries points3d, every light gets a true 3D position — the
    # barycentric image of its net position in its triangle's folded
    # corners. The net XY stays the drawing/pattern plane; the fold fills
    # X3/Y3/Z3 (and, derived, RHO/THETA_S/PHI_S).
    fold_tris: Optional[List[Optional[Tuple]]] = None
    g = net.config.geometry
    if g.points3d is not None:
        tri_indices = [tri for series in g.triangles for tri in series]
        assert len(tri_indices) == len(net.triangles)
        fold_tris = []
        for tri in tri_indices:
            p2d = [g.points[i] for i in tri]
            p3d = [g.points3d[i] for i in tri]
            if any(p is None for p in p3d):
                fold_tris.append(None)
                continue
            (x0, y0), (x1, y1), (x2, y2) = [(p[0], p[1]) for p in p2d]
            det = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
            fold_tris.append((x0, y0, x1, y1, x2, y2, det, p3d))

    def _fold(tri_index: int, px: float, py: float) -> Optional[List[float]]:
        entry = fold_tris[tri_index] if fold_tris is not None else None
        if entry is None:
            return None
        x0, y0, x1, y1, x2, y2, det, p3d = entry
        l0 = ((y1 - y2) * (px - x2) + (x2 - x1) * (py - y2)) / det
        l1 = ((y2 - y0) * (px - x2) + (x0 - x2) * (py - y2)) / det
        l2 = 1.0 - l0 - l1
        return [l0 * p3d[0][d] + l1 * p3d[1][d] + l2 * p3d[2][d] for d in range(3)]

    for tri_index, triangle in enumerate(net.triangles):
        panel_x, panel_y, shrink = panels[tri_index]
        for facet in triangle.get_facets():
            channel = facet_ordinal % channels
            facet_ordinal += 1
            for edge_beams in facet.get_beams():
                for beam in edge_beams:
                    basis = beam.get_basis_point()
                    anchor = beam.anchor_point
                    dx, dy = basis.x - anchor.x, basis.y - anchor.y
                    # The Net's forward_vector (a fixed perpendicular of the
                    # baseline) points OUT of the facet on some edges, putting
                    # the basis outside the cloth and reversing the throw. The
                    # beam polygon is built from the real extents, so it is
                    # authoritative: if the throw points away from the beam
                    # body, mirror the basis back through the anchor.
                    cx = sum(v.x for v in beam.vertices) / len(beam.vertices)
                    cy = sum(v.y for v in beam.vertices) / len(beam.vertices)
                    if (cx - anchor.x) * dx + (cy - anchor.y) * dy < 0:
                        dx, dy = -dx, -dy
                        basis = anchor - (basis - anchor)
                    norm = math.hypot(dx, dy)
                    direction: Optional[List[float]] = None
                    extent: Optional[List[float]] = None
                    if norm > 0:
                        ux, uy = dx / norm, dy / norm
                        direction = [ux, uy, 0.0]
                        # Extent: far end of the beam polygon along the throw
                        # direction (spec §7.3.1). Shallow beams can end
                        # behind the basis point; an occlusion point is never
                        # behind the light, so clamp to the light's position.
                        reach = max(
                            (v.x - anchor.x) * ux + (v.y - anchor.y) * uy
                            for v in beam.vertices
                        )
                        reach = max(reach, norm)
                        extent = [anchor.x + reach * ux, anchor.y + reach * uy, 0.0]
                    specs.append(
                        LightSpec(
                            controller=controller,
                            channel=channel,
                            index=next_index[channel],
                            kind="active",
                            pos=[basis.x, basis.y],
                            pos3=_fold(tri_index, basis.x, basis.y),
                            dir=direction,
                            extent=extent,
                            normal=direction,
                            display=[
                                [
                                    panel_x + (v.x - panel_x) * shrink,
                                    panel_y + (v.y - panel_y) * shrink,
                                ]
                                for v in beam.vertices
                            ],
                        )
                    )
                    next_index[channel] += 1

    return LightsGeometry.from_specs(
        specs,
        space=SpaceSpec(
            authoritative=["xy", "xyz"] if fold_tris is not None else ["xy"]
        ),
        source={"type": "pentagon", "channels": channels},
        meta={
            "name": "pentagon-lights",
            "overlays": {
                "frame": frame_lines,
                "pvc": pvc_lines,
                "pvc_panel": pvc_panel_lines,
                "triangles": tri_polys,
                # Per structural triangle, aligned with "triangles": the
                # [cx, cy, scale] that maps it onto its illuminated panel.
                "panel": [[cx, cy, s] for cx, cy, s in panels],
                "panel_inset_in": PANEL_INSET_INCHES,
            },
        },
    )

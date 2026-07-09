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


def capture(
    net: Net, channels: int = MAX_CHANNELS, controller: int = 0
) -> LightsGeometry:
    """One ACTIVE light per beam, with the beam polygon as its display shape.

    Identity mapping is DEFERRED (review §19.6): until physical strip routing
    is decided, channels go round-robin per facet and indices count up along
    each channel. This function is the single place to change when the real
    routing is known (spec §7.3.1).
    """
    specs: List[LightSpec] = []
    next_index = {ch: 0 for ch in range(channels)}
    facet_ordinal = 0

    for triangle in net.triangles:
        for facet in triangle.get_facets():
            channel = facet_ordinal % channels
            facet_ordinal += 1
            for edge_beams in facet.get_beams():
                for beam in edge_beams:
                    basis = beam.get_basis_point()
                    anchor = beam.anchor_point
                    dx, dy = basis.x - anchor.x, basis.y - anchor.y
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
                            dir=direction,
                            extent=extent,
                            normal=direction,
                            display=[[v.x, v.y] for v in beam.vertices],
                        )
                    )
                    next_index[channel] += 1

    return LightsGeometry.from_specs(
        specs,
        space=SpaceSpec(authoritative=["xy"]),
        source={"type": "pentagon", "channels": channels},
        meta={"name": "pentagon-lights"},
    )

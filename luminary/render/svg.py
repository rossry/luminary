"""Static SVG rendering of scaffolds and lights geometries (spec §14.5).

Rendered once per request, never per frame — live playback is the Canvas
client's job. Draws from the same layout data as the Canvas (spec §14.4).
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from luminary.geometry.lights import Kind, LightColumns, LightsGeometry
from luminary.geometry.scaffold import Scaffold
from luminary.render.projection import lights_layout, scaffold_layout

_KIND_STROKE = {
    int(Kind.ACTIVE): "#e8e8e8",
    int(Kind.INTERPOLATED): "#888888",
    int(Kind.INACTIVE): "#444444",
}


def _svg_open(viewbox: list, width: str = "100%", height: str = "640") -> str:
    vb = " ".join(f"{v:.3f}" for v in viewbox)
    return (
        f'<svg width="{width}" height="{height}" viewBox="{vb}" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<rect x="{viewbox[0]:.3f}" y="{viewbox[1]:.3f}" '
        f'width="{viewbox[2]:.3f}" height="{viewbox[3]:.3f}" fill="#101014"/>'
    )


def scaffold_svg(scaffold: Scaffold) -> str:
    """Skeleton view: lines plus midpoint normal ticks."""
    layout = scaffold_layout(scaffold)
    viewbox = layout["viewBox"]
    stroke_w = max(viewbox[2], viewbox[3]) * 0.004
    tick = max(viewbox[2], viewbox[3]) * 0.03
    parts = [_svg_open(viewbox)]
    for line in layout["lines"]:
        x1, y1 = line["p1"]
        mx, my = line["mid"]
        x2, y2 = line["p2"]
        parts.append(
            f'<path d="M {x1:.3f} {y1:.3f} Q {2*mx - 0.5*(x1+x2):.3f} '
            f'{2*my - 0.5*(y1+y2):.3f} {x2:.3f} {y2:.3f}" stroke="#c8c8d0" '
            f'stroke-width="{stroke_w:.3f}" fill="none" stroke-linecap="round"/>'
        )
        nx, ny = line["normal"][0], line["normal"][1]
        parts.append(
            f'<line x1="{mx:.3f}" y1="{my:.3f}" x2="{mx + nx * tick:.3f}" '
            f'y2="{my + ny * tick:.3f}" stroke="#5588ff" '
            f'stroke-width="{stroke_w * 0.7:.3f}"/>'
        )
    parts.append("</svg>")
    return "".join(parts)


def lights_svg(
    lights: LightsGeometry,
    colors_srgb8: Optional[np.ndarray] = None,
    scaffold: Optional[Scaffold] = None,
) -> str:
    """Lights view: display polygons where present, dots elsewhere.

    Without colors: kinds are styled (active bright, interpolated dim,
    inactive dark). With colors (an (n,3) uint8 array from
    ``Engine.colors_srgb8``): each light is filled with its color.
    """
    layout = lights_layout(lights, scaffold)
    viewbox = layout["viewBox"]
    dot_r = max(viewbox[2], viewbox[3]) * 0.006
    parts = [_svg_open(viewbox)]

    stroke_w = max(viewbox[2], viewbox[3]) * 0.002
    for line in layout["scaffold"]:
        x1, y1 = line["p1"]
        x2, y2 = line["p2"]
        parts.append(
            f'<line x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" '
            f'stroke="#3a3a44" stroke-width="{stroke_w:.3f}"/>'
        )

    kinds = lights.ints(LightColumns.KIND)
    for row, entry in enumerate(layout["lights"]):
        if colors_srgb8 is not None:
            r, g, b = (int(v) for v in colors_srgb8[row])
            fill = f"#{r:02X}{g:02X}{b:02X}"
        else:
            fill = _KIND_STROKE[int(kinds[row])]
        display = entry["display"]
        if display:
            points = " ".join(f"{px:.3f},{py:.3f}" for px, py in display)
            parts.append(f'<polygon points="{points}" fill="{fill}"/>')
        elif entry["x"] is not None:
            radius = dot_r if kinds[row] != Kind.INTERPOLATED else dot_r * 0.6
            parts.append(
                f'<circle cx="{entry["x"]:.3f}" cy="{entry["y"]:.3f}" '
                f'r="{radius:.3f}" fill="{fill}"/>'
            )
    parts.append("</svg>")
    return "".join(parts)

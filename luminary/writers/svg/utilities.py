"""SVG utility functions for generating SVG elements."""

from typing import List
from luminary.geometry.point import Point


def create_svg_header(viewbox: str, width: str, height: str) -> str:
    """
    Generate opening SVG tag with namespace.

    Args:
        viewbox: ViewBox attribute string
        width: Width attribute string
        height: Height attribute string

    Returns:
        SVG header string
    """
    return f'<svg width="{width}" height="{height}" viewBox="{viewbox}" xmlns="http://www.w3.org/2000/svg">'


def create_polygon_svg(
    points: List[Point], fill: str, opacity: float, stroke: str = "none"
) -> str:
    """
    Generate SVG polygon element.

    Args:
        points: List of Point objects defining polygon vertices
        fill: Fill color
        opacity: Fill opacity (0.0 to 1.0)
        stroke: Stroke color (default "none")

    Returns:
        SVG polygon element string
    """
    point_coords = []
    for point in points:
        point_coords.append(f"{point.x},{point.y}")
    points_str = " ".join(point_coords)

    if stroke == "none":
        return (
            f'  <polygon points="{points_str}" fill="{fill}" fill-opacity="{opacity}"/>'
        )
    else:
        return f'  <polygon points="{points_str}" fill="{fill}" fill-opacity="{opacity}" stroke="{stroke}"/>'


def create_circle_svg(
    center: Point,
    radius: float,
    fill: str,
    stroke: str = "none",
    stroke_width: float = 0,
) -> str:
    """
    Generate SVG circle element.

    Args:
        center: Center point
        radius: Circle radius
        fill: Fill color
        stroke: Stroke color (default "none")
        stroke_width: Stroke width (default 0)

    Returns:
        SVG circle element string
    """
    if stroke == "none" or stroke_width == 0:
        return f'  <circle cx="{center.x}" cy="{center.y}" r="{radius}" fill="{fill}"/>'
    else:
        return f'  <circle cx="{center.x}" cy="{center.y}" r="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>'


def create_line_svg(
    p1: Point, p2: Point, stroke_color: str, stroke_width: float
) -> str:
    """
    Generate SVG line element with rounded caps.

    Args:
        p1: Start point
        p2: End point
        stroke_color: Line color
        stroke_width: Line width

    Returns:
        SVG line element string with semicircle rounded caps
    """
    return f'  <line x1="{p1.x}" y1="{p1.y}" x2="{p2.x}" y2="{p2.y}" stroke="{stroke_color}" stroke-width="{stroke_width}" stroke-linecap="round"/>'


def create_text_svg(
    text: str, position: Point, font_size: int, color: str, opacity: float
) -> str:
    """
    Generate SVG text element, centered at position.

    Args:
        text: Text content
        position: Text position (center point)
        font_size: Font size
        color: Text color
        opacity: Text opacity (0.0 to 1.0)

    Returns:
        SVG text element string
    """
    return f'  <text x="{position.x}" y="{position.y}" font-family="Arial" font-size="{font_size}" fill="{color}" fill-opacity="{opacity}" text-anchor="middle">{text}</text>'

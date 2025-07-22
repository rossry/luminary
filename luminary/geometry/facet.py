"""Facet class for quadrilateral subdivisions of triangles."""

from enum import IntEnum
from typing import List
from luminary.geometry.point import Point
from luminary.writers.svg.svg_exportable import SVGExportable
from luminary.writers.svg.utilities import create_polygon_svg, create_text_svg


class EdgeType(IntEnum):
    """Canonical ordering of facet edges."""
    MAJOR_STARBOARD = 0  # Right major edge
    MINOR_STARBOARD = 1  # Right minor edge  
    MINOR_PORT = 2       # Left minor edge
    MAJOR_PORT = 3       # Left major edge


class Facet(SVGExportable):
    """Facet quadrilateral formed by triangle subdivision."""

    def __init__(
        self,
        vertex: Point,
        midpoint1: Point,
        incenter: Point,
        midpoint2: Point,
        color: str,
        label: str,
    ):
        """
        Initialize Facet with vertices in order: vertex → midpoint1 → incenter → midpoint2.

        Args:
            vertex: Triangle vertex point (primary vertex)
            midpoint1: First edge midpoint (lateral vertex)
            incenter: Triangle incenter
            midpoint2: Second edge midpoint (lateral vertex)
            color: Fill color for the facet
            label: Text label (A-C or D-F)
        """
        self.vertices = [vertex, midpoint1, incenter, midpoint2]
        self.color = color
        self.label = label
        self.centroid = self._calculate_centroid()

    def _calculate_centroid(self) -> Point:
        """
        Calculate centroid as average of vertex coordinates.

        Returns:
            Point representing centroid (no color)
        """
        total_x = sum(point.x for point in self.vertices)
        total_y = sum(point.y for point in self.vertices)
        count = len(self.vertices)

        return Point(total_x / count, total_y / count)

    def get_svg(self) -> List[str]:
        """
        Generate SVG elements for facet in back-to-front order.

        Returns:
            List of SVG element strings:
            1. Colored polygon (60% opacity)
            2. Text label (font-size 10, black, 70% opacity, centered at centroid)
        """
        svg_elements = []

        # 1. Colored polygon with 60% opacity
        svg_elements.append(create_polygon_svg(self.vertices, self.color, 0.6))

        # 2. Text label (font-size 10, black, 70% opacity)
        svg_elements.append(
            create_text_svg(self.label, self.centroid, 10, "black", 0.7)
        )

        return svg_elements

    def get_centroid(self) -> Point:
        """Return facet centroid."""
        return self.centroid

    def get_vertices(self) -> List[Point]:
        """Return copy of facet vertices."""
        return self.vertices.copy()
    
    def get_primary_vertex(self) -> Point:
        """Return primary vertex (shared with triangle)."""
        return self.vertices[0]
    
    def get_incenter(self) -> Point:
        """Return incenter vertex."""
        return self.vertices[2]
    
    def get_lateral_vertices(self) -> List[Point]:
        """Return the two lateral vertices."""
        return [self.vertices[1], self.vertices[3]]

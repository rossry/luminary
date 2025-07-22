"""Kite class for quadrilateral subdivisions of triangles."""

from typing import List
from luminary.geometry.point import Point
from luminary.writers.svg.svg_exportable import SVGExportable
from luminary.writers.svg.utilities import create_polygon_svg, create_text_svg


class Kite(SVGExportable):
    """Kite quadrilateral formed by triangle subdivision."""

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
        Initialize Kite with vertices in order: vertex → midpoint1 → incenter → midpoint2.

        Args:
            vertex: Triangle vertex point
            midpoint1: First edge midpoint
            incenter: Triangle incenter
            midpoint2: Second edge midpoint
            color: Fill color for the kite
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
        Generate SVG elements for kite in back-to-front order.

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
        """Return kite centroid."""
        return self.centroid

    def get_vertices(self) -> List[Point]:
        """Return copy of kite vertices."""
        return self.vertices.copy()

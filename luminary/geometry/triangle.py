"""Triangle class with incenter calculation and orientation detection."""

from enum import Enum
from typing import List, Tuple, TYPE_CHECKING
from luminary.geometry.point import Point
from luminary.writers.svg.svg_exportable import SVGExportable
from luminary.writers.svg.utilities import create_line_svg

if TYPE_CHECKING:
    from luminary.geometry.facet import Facet


class Orientation(Enum):
    """Triangle orientation relative to apex point."""

    APEXWARD = "apexward"  # Pointing toward apex
    NADIRWARD = "nadirward"  # Pointing away from apex


class Triangle(SVGExportable):
    """Triangle with incenter calculation and SVG generation."""

    def __init__(
        self,
        p1: Point,
        p2: Point,
        p3: Point,
        triangle_id: int,
        apex: Point,
        beam_counts: Tuple[int, int, int, int] = (7, 4, 4, 7),
    ):
        """
        Initialize Triangle with vertices and calculate geometric properties.

        Args:
            p1: First vertex
            p2: Second vertex
            p3: Third vertex
            triangle_id: Unique triangle identifier
            apex: Pentagon apex point for orientation detection
            beam_counts: Number of beams for each facet edge (MAJOR_STARBOARD, MINOR_STARBOARD, MINOR_PORT, MAJOR_PORT)
        """
        self.vertices = [p1, p2, p3]
        self.triangle_id = triangle_id
        self.apex = apex
        self.beam_counts = beam_counts

        # Calculate geometric properties
        self.incenter = self._calculate_incenter()
        self.edge_midpoints = [
            p1.midpoint_to(p2),  # Edge 1-2 midpoint
            p2.midpoint_to(p3),  # Edge 2-3 midpoint
            p3.midpoint_to(p1),  # Edge 1-3 midpoint
        ]
        self.orientation = self._determine_orientation()

        # Generate facets with proper labeling
        self.facets: List["Facet"] = self._create_facets()

    def _calculate_incenter(self) -> Point:
        """
        Calculate incenter using standard formula.

        Formula: I = (a*A + b*B + c*C) / (a + b + c)
        where a,b,c are side lengths opposite vertices A,B,C

        Returns:
            Point representing incenter
        """
        p1, p2, p3 = self.vertices

        # Calculate side lengths (opposite to each vertex)
        from luminary.geometry.primitives import Segment

        a = Segment(p2, p3).length()  # Side opposite to p1
        b = Segment(p1, p3).length()  # Side opposite to p2
        c = Segment(p1, p2).length()  # Side opposite to p3

        # Handle degenerate triangle (zero perimeter)
        perimeter = a + b + c
        if perimeter == 0:
            return Point((p1.x + p2.x + p3.x) / 3, (p1.y + p2.y + p3.y) / 3)

        # Calculate weighted average: I = (a*A + b*B + c*C) / (a + b + c)
        incenter_x = (a * p1.x + b * p2.x + c * p3.x) / perimeter
        incenter_y = (a * p1.y + b * p2.y + c * p3.y) / perimeter

        return Point(incenter_x, incenter_y)

    def _determine_orientation(self) -> Orientation:
        """
        Determine triangle orientation relative to apex point.

        Logic: Count vertices closer to apex than incenter
        - 1 vertex closer → APEXWARD (triangle points toward apex)
        - 2+ vertices closer → NADIRWARD (triangle points away from apex)

        Returns:
            Orientation.APEXWARD or Orientation.NADIRWARD
        """
        incenter_to_apex = self.incenter.distance(self.apex)

        # Count vertices closer to apex than incenter using functional approach
        vertices_closer_count = len(
            [
                vertex
                for vertex in self.vertices
                if vertex.distance(self.apex) < incenter_to_apex
            ]
        )

        # 1 vertex closer = pointing toward apex, 2+ = pointing away
        return (
            Orientation.APEXWARD
            if vertices_closer_count == 1
            else Orientation.NADIRWARD
        )

    def _get_facet_labels(self) -> List[str]:
        """
        Get facet labels based on orientation.

        Returns:
            List of three label strings
        """
        if self.orientation == Orientation.APEXWARD:
            return ["A", "B", "C"]
        else:
            return ["D", "E", "F"]

    def _get_counterclockwise_order(self, start_vertex_idx: int) -> List[int]:
        """
        Get vertex indices in counterclockwise order starting from given vertex.

        Uses cross product to determine orientation and ensure counterclockwise ordering.

        Args:
            start_vertex_idx: Index of starting vertex (0, 1, or 2)

        Returns:
            List of vertex indices in counterclockwise order
        """
        # Get the three vertices starting from start_vertex_idx
        indices = [
            start_vertex_idx,
            (start_vertex_idx + 1) % 3,
            (start_vertex_idx + 2) % 3,
        ]

        # Check if the triangle vertices are already in counterclockwise order
        # using the cross product of two edge vectors
        v1 = self.vertices[indices[0]]
        v2 = self.vertices[indices[1]]
        v3 = self.vertices[indices[2]]

        # Calculate vectors v1->v2 and v1->v3
        vec1 = v2 - v1
        vec2 = v3 - v1

        # Cross product: positive = counterclockwise, negative = clockwise
        cross_product = vec1.cross_product(vec2)

        if cross_product > 0:
            # Already counterclockwise
            ordered_indices = indices
        else:
            # Clockwise, so reverse the last two to make counterclockwise
            ordered_indices = [indices[0], indices[2], indices[1]]

        # Reverse to get clockwise (since we had it backwards before)
        return [ordered_indices[0], ordered_indices[2], ordered_indices[1]]

    def _create_facets(self) -> List["Facet"]:
        """
        Create 3 facets from triangle subdivision in counterclockwise order.

        For APEXWARD triangles: A = closest to apex, then B, C counterclockwise
        For NADIRWARD triangles: D = furthest from apex, then E, F counterclockwise

        Returns:
            List of Facet objects ordered counterclockwise from A/D facet
        """
        # Import here to avoid circular imports
        from luminary.geometry.facet import Facet

        # Find the starting vertex (A for apexward, D for nadirward)
        vertex_distances = []
        for i, vertex in enumerate(self.vertices):
            distance = vertex.distance(self.apex)
            vertex_distances.append((i, vertex, distance))

        # Find the starting vertex based on orientation
        if self.orientation == Orientation.APEXWARD:
            # A = closest to apex
            start_vertex_idx = min(vertex_distances, key=lambda v: v[2])[0]
        else:
            # D = furthest from apex
            start_vertex_idx = max(vertex_distances, key=lambda v: v[2])[0]

        # Calculate counterclockwise order from the starting vertex
        ordered_vertices = self._get_counterclockwise_order(start_vertex_idx)

        labels = self._get_facet_labels()
        facets = []

        # Create facets in counterclockwise order
        for label_idx, vertex_idx in enumerate(ordered_vertices):
            vertex = self.vertices[vertex_idx]

            # Calculate edge midpoints using modular arithmetic
            # Edge midpoints: [0] = midpoint(v0,v1), [1] = midpoint(v1,v2), [2] = midpoint(v2,v0)
            # For vertex i: edge FROM vertex i, and edge TO vertex i
            midpoint1 = self.edge_midpoints[vertex_idx]  # Edge from this vertex
            midpoint2 = self.edge_midpoints[(vertex_idx + 2) % 3]  # Edge to this vertex

            facet_label = (
                f"{self.triangle_id}{labels[label_idx]}"  # Prepend triangle ID
            )

            facets.append(
                Facet(
                    vertex=vertex,
                    midpoint1=midpoint1,
                    incenter=self.incenter,
                    midpoint2=midpoint2,
                    color=vertex.color or "black",
                    label=facet_label,
                    beam_counts=self.beam_counts,
                )
            )

        return facets

    def get_svg(self) -> List[str]:
        """
        Generate SVG elements for triangle base components (without edge lines).

        Returns:
            List of SVG element strings
        """
        svg_elements = []

        # 1. Triangle fill (40% black) - back layer
        points_str = f"{self.vertices[0].x},{self.vertices[0].y} {self.vertices[1].x},{self.vertices[1].y} {self.vertices[2].x},{self.vertices[2].y}"
        svg_elements.append(
            f'  <polygon points="{points_str}" fill="black" fill-opacity="0.4"/>'
        )

        # 2. Incenter dot (black circle, radius 1.5) - middle layer
        svg_elements.append(
            f'  <circle cx="{self.incenter.x}" cy="{self.incenter.y}" r="1.5" fill="black"/>'
        )

        # 3. Construction lines from incenter to edge midpoints
        for midpoint in self.edge_midpoints:
            svg_elements.append(create_line_svg(self.incenter, midpoint, "black", 1))

        return svg_elements

    def get_edge_lines_svg(self) -> List[str]:
        """
        Generate SVG elements for triangle edges.
        These should be rendered on top of everything else.

        Returns:
            List of SVG line element strings
        """
        svg_elements = []

        # Draw triangle edges (full-width, black)
        for i in range(3):
            v1 = self.vertices[i]
            v2 = self.vertices[(i + 1) % 3]
            svg_elements.append(create_line_svg(v1, v2, "black", 2))

        return svg_elements

    def get_construction_lines_svg(self) -> List[str]:
        """
        Generate SVG elements for construction lines (incenter to midpoints).
        These should be rendered on top of facets.

        Returns:
            List of SVG line element strings
        """
        svg_elements = []

        # Geometric lines from incenter to edge midpoints (half-width, black)
        for midpoint in self.edge_midpoints:
            svg_elements.append(create_line_svg(self.incenter, midpoint, "black", 1))

        return svg_elements

    def get_vertices(self) -> List[Point]:
        """Return triangle vertices."""
        return self.vertices.copy()

    def get_facets(self) -> List["Facet"]:
        """Return triangle facets."""
        return self.facets.copy()

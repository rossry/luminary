"""Facet class for quadrilateral subdivisions of triangles."""

from enum import IntEnum
from typing import List, Tuple
import math
from luminary.geometry.point import Point
from luminary.geometry.beam import Beam
from luminary.writers.svg.svg_exportable import SVGExportable
from luminary.writers.svg.utilities import create_polygon_svg, create_text_svg


class EdgeType(IntEnum):
    """Canonical ordering of facet edges."""

    MAJOR_STARBOARD = 0  # Right major edge
    MINOR_STARBOARD = 1  # Right minor edge
    MINOR_PORT = 2  # Left minor edge
    MAJOR_PORT = 3  # Left major edge


# vertices should be stored as named variables of the object. we can keep vertices as a variable for convenient access, but it should be marked internal with an underscore
class Facet(SVGExportable):
    """Facet quadrilateral formed by triangle subdivision."""

    def __init__(
        self,
        vertex: Point,  # CLAUDE TODO: rename vertex_primary
        midpoint1: Point,  # CLAUDE TODO: rename vertex_port (though first carefully check that I haven't mixed 1/2 vs port/starboard by inspecting the actual logic)
        incenter: Point,  # CLAUDE TODO: rename vertex_incenter
        midpoint2: Point,  # CLAUDE TODO: rename vertex_starboard
        color: str,
        label: str,
        beam_counts: Tuple[int, int, int, int],
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
            beam_counts: Number of beams for each edge (MAJOR_STARBOARD, MINOR_STARBOARD, MINOR_PORT, MAJOR_PORT)
        """
        self.vertices = (vertex, midpoint1, incenter, midpoint2)
        self.color = color
        self.label = label
        self.centroid = self._calculate_centroid()

        # Generate beams at init time
        self.beams = self._generate_beams(beam_counts)

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

    def get_vertices(self) -> Tuple[Point, Point, Point, Point]:
        """Return tuple of facet vertices."""
        return self.vertices

    # CLAUDE TODO: return by variable name, not magic index
    def get_primary_vertex(self) -> Point:
        """Return primary vertex (shared with triangle)."""
        return self.vertices[0]

    # CLAUDE TODO: return by variable name, not magic index
    def get_incenter(self) -> Point:
        """Return incenter vertex."""
        return self.vertices[2]

    # CLAUDE TODO: return by variable name, not magic indeices
    def get_lateral_vertices(self) -> Tuple[Point, Point]:
        """Return the two lateral vertices."""
        return (self.vertices[1], self.vertices[3])

    # CLAUDE TODO: return by variable name, not magic index
    def _get_axis_of_symmetry(self) -> Tuple[Point, Point]:
        """Get axis of symmetry from primary vertex to incenter.

        Returns:
            Tuple of (start_point, end_point) for the axis line
        """
        return (self.vertices[0], self.vertices[2])  # primary vertex to incenter

    def _get_edge_points(self, edge_type: EdgeType) -> Tuple[Point, Point]:
        """Get the two points that define an edge.

        Args:
            edge_type: Which edge to get points for

        Returns:
            Tuple of (start_point, end_point) for the edge
        """
        # CLAUDE TODO: write this with match/case
        if edge_type == EdgeType.MAJOR_STARBOARD:
            return (self.vertices[0], self.vertices[1])
        elif edge_type == EdgeType.MINOR_STARBOARD:
            return (self.vertices[1], self.vertices[2])
        elif edge_type == EdgeType.MINOR_PORT:
            return (self.vertices[2], self.vertices[3])
        elif edge_type == EdgeType.MAJOR_PORT:
            return (self.vertices[3], self.vertices[0])
        else:
            raise ValueError(f"Unknown edge type: {edge_type}")

    # CLAUDE TODO: this should go to the Point class, since it's generic
    def _line_intersection(
        self, line1: Tuple[Point, Point], line2: Tuple[Point, Point]
    ) -> Point:
        """Calculate intersection of two lines.

        Args:
            line1: First line as (point1, point2)
            line2: Second line as (point1, point2)

        Returns:
            Intersection point
        """
        p1, p2 = line1
        p3, p4 = line2

        denom = (p1.x - p2.x) * (p3.y - p4.y) - (p1.y - p2.y) * (p3.x - p4.x)
        if abs(denom) < 1e-10:
            # Lines are parallel - return midpoint as fallback
            return Point.midpoint(p1, p3)

        t = ((p1.x - p3.x) * (p3.y - p4.y) - (p1.y - p3.y) * (p3.x - p4.x)) / denom

        intersection_x = p1.x + t * (p2.x - p1.x)
        intersection_y = p1.y + t * (p2.y - p1.y)
        return Point(intersection_x, intersection_y)

    def _generate_beams(
        self, beam_counts: Tuple[int, int, int, int]
    ) -> Tuple[List[Beam], List[Beam], List[Beam], List[Beam]]:
        """Generate beams for each edge of the facet using axis slicing.

        Args:
            beam_counts: Number of beams for each edge (MAJOR_STARBOARD, MINOR_STARBOARD, MINOR_PORT, MAJOR_PORT)

        Returns:
            Tuple of beam lists, one for each edge
        """
        all_beams = []
        axis = self._get_axis_of_symmetry()

        for edge_idx, beam_count in enumerate(beam_counts):
            edge_type = EdgeType(edge_idx)
            edge_beams = []

            # CLAUDE TODO: there's no reason you should need to do geometry math; that really should be handled in the Point class or one of its constructs.
            # Get edge boundaries
            edge_start, edge_end = self._get_edge_points(edge_type)
            edge_vector = edge_end - edge_start
            edge_length = math.sqrt(edge_vector.x**2 + edge_vector.y**2)

            if edge_length == 0:
                continue  # Skip degenerate edges

            # Calculate beam vectors
            edge_unit = edge_vector / edge_length  # Unit vector along edge
            beam_width = edge_length / beam_count  # Width of each beam

            # Starboard vector: along the edge, one beam width
            starboard_vector = edge_unit * beam_width
            # Forward vector: perpendicular to edge, pointing into facet interior, one beam width
            forward_vector = Point(-edge_unit.y, edge_unit.x) * beam_width

            for beam_idx in range(beam_count):
                # Calculate beam baseline segment on the edge
                t_start = beam_idx / beam_count
                t_end = (beam_idx + 1) / beam_count

                baseline_start = (
                    edge_start + t_start * edge_vector
                )  # port side of baseline
                baseline_end = (
                    edge_start + t_end * edge_vector
                )  # starboard side of baseline

                # Calculate anchor point (center of baseline)
                anchor = Point.midpoint(baseline_start, baseline_end)

                # CLAUDE TODO: note that the offset starboard_axis_intersection - port_axis_intersection is constant for all beams in an edge, and note also that the starboard_axis_intersection of beam_idx=n is the port_axis_intersection of beam_idx=(n+1). use these to calculate the prev_starboard_axis_intersection and the axis_intersection_stride_vector and use them to do this much more simply. we can verify that this agrees with computed math in tests.
                # Create perpendicular rays from baseline endpoints into facet interior
                ray_depth = 100.0  # Large number to ensure intersection # CLAUDE TODO: this should be unnecessary, and the fact that it's here is a sign that either the underlying geometry library you've written is missing something, or you're not using it to its full power here.
                forward_unit = Point(
                    -edge_unit.y, edge_unit.x
                )  # Unit vector into facet interior
                port_ray_end = baseline_start + forward_unit * ray_depth
                starboard_ray_end = baseline_end + forward_unit * ray_depth

                # Find intersections with axis of symmetry
                port_ray = (baseline_start, port_ray_end)
                starboard_ray = (baseline_end, starboard_ray_end)

                port_axis_intersection = self._line_intersection(port_ray, axis)
                starboard_axis_intersection = self._line_intersection(
                    starboard_ray, axis
                )

                # Create single extent segment from axis slicing
                extent_pairs = [(port_axis_intersection, starboard_axis_intersection)]

                # Create beam
                beam = Beam(
                    extent_pairs=extent_pairs,
                    beam_index=beam_idx,
                    edge_index=edge_idx,
                    anchor_point=anchor,
                    starboard_vector=starboard_vector,
                )

                edge_beams.append(beam)

            all_beams.append(edge_beams)

        return tuple(all_beams)

    def get_beams(self) -> Tuple[List[Beam], List[Beam], List[Beam], List[Beam]]:
        """Return tuple of beam lists for each edge."""
        return self.beams

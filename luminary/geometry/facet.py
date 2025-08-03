"""Facet class for quadrilateral subdivisions of triangles."""

from enum import IntEnum
from typing import List, Tuple
import math
from luminary.geometry.point import Point
from luminary.geometry.beam import Beam
from luminary.geometry.primitives import Segment, Vector, Ray, Angle
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
        
        # Named vertex properties for better code clarity
        self.vertex_primary = vertex
        self.vertex_port = midpoint1  # TODO: Verify this is correct port/starboard mapping
        self.vertex_incenter = incenter
        self.vertex_starboard = midpoint2  # TODO: Verify this is correct port/starboard mapping
        
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

    def get_primary_vertex(self) -> Point:
        """Return primary vertex (shared with triangle)."""
        return self.vertex_primary

    def get_incenter(self) -> Point:
        """Return incenter vertex."""
        return self.vertex_incenter

    def get_lateral_vertices(self) -> Tuple[Point, Point]:
        """Return the two lateral vertices."""
        return (self.vertex_port, self.vertex_starboard)

    def _get_axis_of_symmetry(self) -> Segment:
        """Get axis of symmetry from primary vertex to incenter.

        Returns:
            Segment representing the axis line
        """
        return Segment(self.vertex_primary, self.vertex_incenter)

    def _get_edge_points(self, edge_type: EdgeType) -> Segment:
        """Get the segment that defines an edge.

        Args:
            edge_type: Which edge to get segment for

        Returns:
            Segment representing the edge
        """
        match edge_type:
            case EdgeType.MAJOR_STARBOARD:
                return Segment(self.vertex_primary, self.vertex_port)
            case EdgeType.MINOR_STARBOARD:
                return Segment(self.vertex_port, self.vertex_incenter)
            case EdgeType.MINOR_PORT:
                return Segment(self.vertex_incenter, self.vertex_starboard)
            case EdgeType.MAJOR_PORT:
                return Segment(self.vertex_starboard, self.vertex_primary)
            case _:
                raise ValueError(f"Unknown edge type: {edge_type}")

    def _get_edge_vector_counterclockwise(self, edge_type: EdgeType) -> Vector:
        """Get the vector along an edge in counterclockwise direction.

        Args:
            edge_type: Which edge to get vector for

        Returns:
            Vector pointing along the edge in counterclockwise direction
        """
        match edge_type:
            case EdgeType.MAJOR_STARBOARD:
                return self.vertex_port - self.vertex_primary
            case EdgeType.MINOR_STARBOARD:
                return self.vertex_incenter - self.vertex_port
            case EdgeType.MINOR_PORT:
                return self.vertex_starboard - self.vertex_incenter
            case EdgeType.MAJOR_PORT:
                return self.vertex_primary - self.vertex_starboard
            case _:
                raise ValueError(f"Unknown edge type: {edge_type}")

    # CLAUDE TODO: replace all calls to this with the bisector function in primitives.py
    def _deprecated_calculate_angle_bisector(
        self, apex: Point, point1: Point, point2: Point
    ) -> Ray:
        """Calculate the angle bisector ray.

        Args:
            apex: Vertex of the angle
            point1: First point defining the angle
            point2: Second point defining the angle

        Returns:
            Ray starting from apex along the angle bisector direction
        """
        angle = Angle(apex, point1, point2)
        return angle.bisector()

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

        # Calculate lateral angle bisectors for second extent
        # Port lateral angle: at midpoint1, between edges to vertex and incenter
        port_angle = Angle(
            self.vertices[3],  # midpoint1 (port lateral)
            self.vertices[0],  # vertex
            self.vertices[2],  # incenter
        )
        port_bisector = port_angle.bisector()

        # Starboard lateral angle: at midpoint2, between edges to incenter and vertex
        starboard_angle = Angle(
            self.vertices[1],  # midpoint2 (starboard lateral)
            self.vertices[2],  # incenter
            self.vertices[0],  # vertex
        )
        starboard_bisector = starboard_angle.bisector()

        # CLAUDE TODO: Pre-compute bisector rays once per edge (constant for all beams on this edge)

        close_bisector_ray = [
            starboard_bisector,
            starboard_bisector,
            port_bisector,
            port_bisector,
        ]

        # Track sequential beam parity across all edges
        global_beam_parity = 0

        # CLAUDE TODO: make this a nested `for` first over edge_idx and then over beam_counts[edge_idx]
        for edge_idx, beam_count in enumerate(beam_counts):
            edge_type = EdgeType(edge_idx)
            edge_beams = []

            # CLAUDE TODO: there's no reason you should need to do geometry math; that really should be handled in the Point class or one of its constructs.
            # Get edge geometry
            edge_segment = self._get_edge_points(edge_type)
            edge_vector = self._get_edge_vector_counterclockwise(edge_type)
            edge_length = edge_segment.length()
            edge_start = edge_segment.p1  # Starting point of edge

            if edge_length == 0:
                continue  # Skip degenerate edges

            # Calculate beam vectors
            edge_unit = edge_vector.unit_vector()  # Unit vector along edge
            beam_width = edge_length / beam_count  # Width of each beam

            forward_unit = (
                edge_unit.perpendicular_counterclockwise()
            )  # Unit vector into facet interior

            # Beam's starboard vector: along the edge, one beam width
            beamstarboard_vector = edge_unit * beam_width
            # Beam's forward vector: perpendicular to edge, pointing into facet interior, one beam width
            beamforward_vector = forward_unit * beam_width

            # Compute first beam intersections to establish stride vectors
            first_baseline_start = edge_start  # t_start = 0
            first_baseline_end = (
                edge_start + edge_vector / beam_count
            )  # t_end = 1/beam_count

            first_beamport_ray = Ray.from_point_and_direction(
                first_baseline_start, forward_unit
            )
            first_beamstarboard_ray = Ray.from_point_and_direction(
                first_baseline_end, forward_unit
            )

            # First beam axis intersections
            first_beamport_axis = first_beamport_ray.intersection(axis)
            first_beamstarboard_axis = first_beamstarboard_ray.intersection(axis)

            # First beam bisector intersections
            first_beamport_bisector = first_beamport_ray.intersection(
                close_bisector_ray[edge_idx]
            )
            first_beamstarboard_bisector = first_beamstarboard_ray.intersection(
                close_bisector_ray[edge_idx]
            )

            # Check for null intersections and skip this edge if geometry is degenerate
            if (
                first_beamport_axis is None
                or first_beamstarboard_axis is None
                or first_beamport_bisector is None
                or first_beamstarboard_bisector is None
            ):
                all_beams.append([])  # Add empty beam list for this edge
                continue

            # Calculate stride vectors
            axis_stride_vector = first_beamstarboard_axis - first_beamport_axis
            bisector_stride_vector = (
                first_beamstarboard_bisector - first_beamport_bisector
            )

            # Initialize for stride optimization - start with port intersections of first beam
            # so that beam 0's port = prev_starboard works correctly
            prev_axis_beamstarboard = first_beamport_axis
            prev_bisector_beamstarboard = first_beamport_bisector

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
                anchor = baseline_start.midpoint_to(baseline_end)

                # Use stride optimization for all beams uniformly
                beamport_axis_intersection = prev_axis_beamstarboard
                beamport_bisector_intersection = prev_bisector_beamstarboard

                beamstarboard_axis_intersection = (
                    beamport_axis_intersection + axis_stride_vector
                )
                beamstarboard_bisector_intersection = (
                    beamport_bisector_intersection + bisector_stride_vector
                )

                # Update for next iteration
                prev_axis_beamstarboard = beamstarboard_axis_intersection
                prev_bisector_beamstarboard = beamstarboard_bisector_intersection

                # Create dual extent segments with OrientedSegment
                from luminary.geometry.primitives import OrientedSegment

                extent_segments = [
                    OrientedSegment(
                        {
                            "port": beamport_axis_intersection,
                            "starboard": beamstarboard_axis_intersection,
                        }
                    ),  # First extent (axis)
                    OrientedSegment(
                        {
                            "port": beamport_bisector_intersection,
                            "starboard": beamstarboard_bisector_intersection,
                        }
                    ),  # Second extent (bisectors)
                ]

                # Create beam with sequential parity
                beam = Beam(
                    extent_segments=extent_segments,
                    beam_index=beam_idx,
                    edge_index=edge_idx,
                    anchor_point=anchor,
                    starboard_vector=beamstarboard_vector,
                    parity=global_beam_parity,
                )

                edge_beams.append(beam)

                # Alternate parity for next beam
                global_beam_parity = 1 - global_beam_parity

            all_beams.append(edge_beams)

        return tuple(all_beams)

    def get_beams(self) -> Tuple[List[Beam], List[Beam], List[Beam], List[Beam]]:
        """Return tuple of beam lists for each edge."""
        return self.beams

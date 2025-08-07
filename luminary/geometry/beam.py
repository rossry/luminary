"""Beam geometry for light-based facet subdivisions."""

from typing import List, Tuple, Optional
from luminary.geometry.point import Point
from luminary.geometry.primitives import Segment, Vector, OrientedSegment, Polygon
from luminary.writers.svg.svg_exportable import SVGExportable
from luminary.writers.svg.utilities import create_polygon_svg


class Beam(Polygon, SVGExportable):
    """A beam represents a subdivision of a facet based on light source simulation.

    The beam calculates its own geometry from port/starboard extent pairs
    and anchor point with basis vector.
    """

    def __init__(
        self,
        extent_segments: List[
            OrientedSegment
        ],  # Forward boundary segments with port/starboard labels
        beam_index: int,
        edge_index: int,
        anchor_point: Point,
        starboard_vector: Vector,  # Vector along baseline, one beam width
        parity: int,  # 0 or 1, assigned sequentially during generation
        face_index: int,
        facet_index: int,
    ):
        """Initialize a beam with extent segments and calculate full geometry.

        Args:
            extent_segments: List of OrientedSegments with "port"/"starboard" labels.
                           Currently must contain exactly 1 element.
            beam_index: Index of this beam within the edge (0-based)
            edge_index: Index of the parent edge (0-3 for MAJOR_STARBOARD to MAJOR_PORT)
            anchor_point: Reference point on baseline, centered
            starboard_vector: Vector along baseline (starboard direction), one beam width
            parity: 0 or 1, assigned sequentially during generation
            face_index: Index of the parent triangle/face
            facet_index: Index of the parent facet
        """
        # Validate extent requirements for current implementation
        if len(extent_segments) not in (1, 2):
            raise NotImplementedError(
                f"Currently only 1 or 2 extents supported, got {len(extent_segments)} extents"
            )

        # Validate that segments have correct labels
        for segment in extent_segments:
            segment.assert_labels({"port", "starboard"})

        self.extent_segments = extent_segments
        self.beam_index = beam_index
        self.edge_index = edge_index
        self.anchor_point = anchor_point
        self.starboard_vector = (
            starboard_vector  # Points along baseline (starboard direction)
        )
        self.parity = parity
        self.face_index = face_index
        self.facet_index = facet_index
        
        # Create beam ID tuple
        self.beam_id = (face_index, facet_index, edge_index, beam_index)

        # Calculate forward vector (perpendicular to starboard vector, pointing into facet interior)
        self.forward_vector = starboard_vector.perpendicular_counterclockwise()

        # Calculate full vertices from single extent
        vertices = self._calculate_vertices()
        
        # Initialize Polygon with vertices
        super().__init__(vertices)

    def _calculate_vertices(self) -> List[Point]:
        """Calculate beam polygon from extent pairs.

        Creates 4-sided polygon using the appropriate extent(s).
        """
        # Calculate baseline endpoints from anchor along the baseline (starboard direction)
        half_width = self.starboard_vector * 0.5
        baseline_port = self.anchor_point - half_width
        baseline_starboard = self.anchor_point + half_width

        if len(self.extent_segments) == 1:
            # Single extent: use it directly
            extent = self.extent_segments[0]
            forward_port = extent.get_point_by_label("port")
            forward_starboard = extent.get_point_by_label("starboard")

            # Create 4-sided polygon
            vertices = [
                baseline_port,  # Start of baseline (port side)
                baseline_starboard,  # End of baseline (starboard side)
                forward_starboard,  # Forward edge starboard point
                forward_port,  # Forward edge port point
            ]
        else:
            # Dual extents: determine which extent is closer on each side
            extent0 = self.extent_segments[0]
            extent1 = self.extent_segments[1]

            extent0_port = extent0.get_point_by_label("port")
            extent0_starboard = extent0.get_point_by_label("starboard")
            extent1_port = extent1.get_point_by_label("port")
            extent1_starboard = extent1.get_point_by_label("starboard")

            # Calculate distances from baseline corners to extent endpoints
            port_dist_0 = baseline_port.distance(extent0_port)
            port_dist_1 = baseline_port.distance(extent1_port)
            starboard_dist_0 = baseline_starboard.distance(extent0_starboard)
            starboard_dist_1 = baseline_starboard.distance(extent1_starboard)

            # Determine which extent is closer on each side
            closer_port_extent = 0 if port_dist_0 < port_dist_1 else 1
            closer_starboard_extent = 0 if starboard_dist_0 < starboard_dist_1 else 1

            if closer_port_extent == closer_starboard_extent:
                # Same extent is closer on both sides - use that extent
                extent = self.extent_segments[closer_port_extent]
                forward_port = extent.get_point_by_label("port")
                forward_starboard = extent.get_point_by_label("starboard")

                # Create 4-sided polygon
                vertices = [
                    baseline_port,  # Start of baseline (port side)
                    baseline_starboard,  # End of baseline (starboard side)
                    forward_starboard,  # Forward edge starboard point
                    forward_port,  # Forward edge port point
                ]
            else:
                # Different extents are closer - create 5-sided polygon
                # Get the nearest intersections
                port_nearest = self.extent_segments[
                    closer_port_extent
                ].get_point_by_label("port")
                starboard_nearest = self.extent_segments[
                    closer_starboard_extent
                ].get_point_by_label("starboard")

                # Calculate intersection between the two extents
                extent1_extent2_intersection = extent0.intersection(extent1)
                if extent1_extent2_intersection is None:
                    # Parallel lines - use midpoint as fallback
                    extent1_extent2_intersection = extent0.get_point_by_label("port").midpoint_to(
                        extent1.get_point_by_label("port")
                    )

                # Create 5-sided polygon: baseline_port, baseline_starboard, starboard_nearest, intersection, port_nearest
                vertices = [
                    baseline_port,  # Start of baseline (port side)
                    baseline_starboard,  # End of baseline (starboard side)
                    starboard_nearest,  # Starboard nearest intersection
                    extent1_extent2_intersection,  # Intersection between extents
                    port_nearest,  # Port nearest intersection
                ]

        return vertices

    def get_fill_color_multiplier(self) -> float:
        """Calculate color multiplier based on sequential parity.

        Returns:
            1.2 for bright beams (parity 0), 0.8 for dim beams (parity 1)
        """
        return 1.2 if self.parity == 0 else 0.8

    def get_basis_point(self) -> Point:
        """Get the basis point for pattern evaluation.
        
        The basis point is located half a width forward from the anchor point,
        providing a representative coordinate for SDF evaluation.
        
        Returns:
            Point representing the beam's basis coordinate for pattern evaluation
        """
        return self.anchor_point + 0.5 * self.forward_vector

    def generate_samples(self) -> List[Point]:
        """Generate sample points within the beam.

        Places one sample at 0.5w forward of anchor, and another at 1.5w forward
        if the point at 2w forward is still within the beam geometry.

        Returns:
            List of 1-2 sample points
        """
        samples = []

        # First sample at 0.5w forward of anchor
        sample1 = self.anchor_point + 0.5 * self.forward_vector
        samples.append(sample1)

        # Check if point at 2w forward is in geometry
        test_point = self.anchor_point + 2.0 * self.forward_vector

        if self.is_inside(test_point):
            # Add second sample at 1.5w forward
            sample2 = self.anchor_point + 1.5 * self.forward_vector
            samples.append(sample2)

        return samples

    def get_svg(self, base_color: str, beam_colors: dict = None) -> List[str]:
        """Generate SVG representation of the beam.

        Args:
            base_color: Base color from parent facet
            beam_colors: Optional dictionary mapping beam_id to Color objects

        Returns:
            List of SVG element strings
        """
        # Check for pattern color override
        if beam_colors and self.beam_id in beam_colors:
            pattern_color = beam_colors[self.beam_id]
            final_color = pattern_color.to_svg_str()
        else:
            # Apply color multiplier based on parity
            color_multiplier = self.get_fill_color_multiplier()
            # Adjust brightness of base color
            final_color = self._adjust_color_brightness(base_color, color_multiplier)

        # Create beam ID string for SVG
        beam_id_str = f"{self.beam_id[0]}:{self.beam_id[1]}:{self.beam_id[2]}:{self.beam_id[3]}"
        
        # Create polygon SVG with ID and class
        beam_svg = create_polygon_svg(self.vertices, final_color, 0.6)
        
        # Add beam ID and class to the SVG element
        if 'id="' not in beam_svg:
            beam_svg = beam_svg.replace('<polygon', f'<polygon id="beam_{beam_id_str}" class="beam"')

        return [beam_svg]

    def _adjust_color_brightness(self, color_str: str, multiplier: float) -> str:
        """Adjust the brightness of a color by a multiplier using OKLCH.

        Args:
            color_str: Color string (hex like "#FF0000" or named like "red")
            multiplier: Brightness multiplier (1.2 = +20%, 0.8 = -20%)

        Returns:
            Adjusted OKLCH color string for SVG
        """
        from luminary.color import Color

        # Create Color instance from string and adjust lightness
        color = Color.from_string(color_str)
        adjusted_color = color.adjust_lightness(multiplier)

        return adjusted_color.to_svg_str()

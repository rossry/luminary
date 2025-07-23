"""Beam geometry for light-based facet subdivisions."""

from typing import List, Tuple, Optional
from luminary.geometry.point import Point
from luminary.writers.svg.svg_exportable import SVGExportable
from luminary.writers.svg.utilities import create_polygon_svg


class Beam(SVGExportable):
    """A beam represents a subdivision of a facet based on light source simulation.

    The beam calculates its own geometry from port/starboard extent pairs
    and anchor point with basis vector.
    """

    def __init__(
        self,
        extent_pairs: List[
            Tuple[Point, Point]
        ],  # [(port1, starboard1)] - currently must have exactly 1 element
        beam_index: int,
        edge_index: int,
        anchor_point: Point,
        starboard_vector: Point,  # Vector along baseline, one beam width
        parity: int,  # 0 or 1, assigned sequentially during generation
    ):
        """Initialize a beam with extent pairs and calculate full geometry.

        Args:
            extent_pairs: List of (port, starboard) point pairs defining forward boundaries.
                         Currently must contain exactly 1 element.
            beam_index: Index of this beam within the edge (0-based)
            edge_index: Index of the parent edge (0-3 for MAJOR_STARBOARD to MAJOR_PORT)
            anchor_point: Reference point on baseline, centered
            starboard_vector: Vector along baseline (starboard direction), one beam width
            parity: 0 or 1, assigned sequentially during generation
        """
        # Validate extent requirements for current implementation
        if len(extent_pairs) not in (1, 2):
            raise NotImplementedError(
                f"Currently only 1 or 2 extents supported, got {len(extent_pairs)} extents"
            )

        self.extent_pairs = extent_pairs
        self.beam_index = beam_index
        self.edge_index = edge_index
        self.anchor_point = anchor_point
        self.starboard_vector = (
            starboard_vector  # Points along baseline (starboard direction)
        )
        self.parity = parity

        # Calculate forward vector (perpendicular to starboard vector, pointing into facet interior)
        self.forward_vector = Point(-starboard_vector.y, starboard_vector.x)

        # Calculate full vertices from single extent
        self.vertices = self._calculate_vertices()

    def _calculate_vertices(self) -> List[Point]:
        """Calculate beam polygon from extent pairs.

        Creates 4-sided polygon using the appropriate extent(s).
        """
        # Calculate baseline endpoints from anchor along the baseline (starboard direction)
        half_width = self.starboard_vector * 0.5
        baseline_port = self.anchor_point - half_width
        baseline_starboard = self.anchor_point + half_width

        if len(self.extent_pairs) == 1:
            # Single extent: use it directly
            forward_port, forward_starboard = self.extent_pairs[0]
            
            # Create 4-sided polygon
            vertices = [
                baseline_port,      # Start of baseline (port side)
                baseline_starboard, # End of baseline (starboard side)
                forward_starboard,  # Forward edge starboard point
                forward_port,       # Forward edge port point
            ]
        else:
            # Dual extents: determine which extent is closer on each side
            extent0_port, extent0_starboard = self.extent_pairs[0]
            extent1_port, extent1_starboard = self.extent_pairs[1]
            
            # Calculate distances from baseline corners to extent endpoints
            port_dist_0 = Point.distance(baseline_port, extent0_port)
            port_dist_1 = Point.distance(baseline_port, extent1_port)
            starboard_dist_0 = Point.distance(baseline_starboard, extent0_starboard)
            starboard_dist_1 = Point.distance(baseline_starboard, extent1_starboard)
            
            # Determine which extent is closer on each side
            closer_port_extent = 0 if port_dist_0 < port_dist_1 else 1
            closer_starboard_extent = 0 if starboard_dist_0 < starboard_dist_1 else 1
            
            if closer_port_extent == closer_starboard_extent:
                # Same extent is closer on both sides - use that extent
                forward_port, forward_starboard = self.extent_pairs[closer_port_extent]
                
                # Create 4-sided polygon
                vertices = [
                    baseline_port,      # Start of baseline (port side)
                    baseline_starboard, # End of baseline (starboard side)
                    forward_starboard,  # Forward edge starboard point
                    forward_port,       # Forward edge port point
                ]
            else:
                # Different extents are closer - create 5-sided polygon
                # Get the nearest intersections
                port_nearest = self.extent_pairs[closer_port_extent][0]  # port side of closer extent
                starboard_nearest = self.extent_pairs[closer_starboard_extent][1]  # starboard side of closer extent
                
                # Calculate intersection between the two extents
                extent1_extent2_intersection = self._line_intersection(
                    self.extent_pairs[0],  # (extent0_port, extent0_starboard)
                    self.extent_pairs[1]   # (extent1_port, extent1_starboard)
                )
                
                # Create 5-sided polygon: baseline_port, baseline_starboard, starboard_nearest, intersection, port_nearest
                vertices = [
                    baseline_port,               # Start of baseline (port side)
                    baseline_starboard,          # End of baseline (starboard side)
                    starboard_nearest,           # Starboard nearest intersection
                    extent1_extent2_intersection, # Intersection between extents
                    port_nearest,                # Port nearest intersection
                ]

        return vertices

    def _line_intersection(self, line1: Tuple[Point, Point], line2: Tuple[Point, Point]) -> Point:
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
            return Point((p1.x + p3.x) / 2, (p1.y + p3.y) / 2)

        t = ((p1.x - p3.x) * (p3.y - p4.y) - (p1.y - p3.y) * (p3.x - p4.x)) / denom

        intersection_x = p1.x + t * (p2.x - p1.x)
        intersection_y = p1.y + t * (p2.y - p1.y)
        return Point(intersection_x, intersection_y)

    def get_fill_color_multiplier(self) -> float:
        """Calculate color multiplier based on sequential parity.

        Returns:
            1.2 for bright beams (parity 0), 0.8 for dim beams (parity 1)
        """
        return 1.2 if self.parity == 0 else 0.8

    # CLAUDE TODO: point-in-polygonvertexlist should go to the Point class
    def _point_in_geometry(self, point: Point) -> bool:
        """Check if a point is inside the beam's geometry using ray casting."""
        if not self.vertices:
            return False

        x, y = point.x, point.y
        n = len(self.vertices)
        inside = False

        j = n - 1
        for i in range(n):
            xi, yi = self.vertices[i].x, self.vertices[i].y
            xj, yj = self.vertices[j].x, self.vertices[j].y

            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i

        return inside

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

        if self._point_in_geometry(test_point):
            # Add second sample at 1.5w forward
            sample2 = self.anchor_point + 1.5 * self.forward_vector
            samples.append(sample2)

        return samples

    def get_svg(self, base_color: str) -> List[str]:
        """Generate SVG representation of the beam.

        Args:
            base_color: Base color from parent facet

        Returns:
            List of SVG element strings
        """
        # Apply color multiplier based on parity
        color_multiplier = self.get_fill_color_multiplier()

        # Adjust brightness of base color
        adjusted_color = self._adjust_color_brightness(base_color, color_multiplier)

        # Create polygon SVG with adjusted color
        beam_svg = create_polygon_svg(self.vertices, adjusted_color, 0.6)

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

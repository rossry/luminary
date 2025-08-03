"""Tests for Point class."""

import pytest
import math
from luminary.geometry.point import Point


class TestPoint:
    """Test cases for Point class."""

    def test_init(self):
        """Test Point initialization."""
        # Test with color
        p1 = Point(1.0, 2.0, "#FF0000")
        assert p1.x == 1.0
        assert p1.y == 2.0
        assert p1.color == "#FF0000"

        # Test without color
        p2 = Point(3.0, 4.0)
        assert p2.x == 3.0
        assert p2.y == 4.0
        assert p2.color is None

    def test_get_color(self):
        """Test get_color method."""
        p1 = Point(0, 0, "#0000FF")
        assert p1.get_color() == "#0000FF"

        p2 = Point(0, 0)
        assert p2.get_color() is None

    def test_distance(self):
        """Test distance calculation."""
        p1 = Point(0, 0)
        p2 = Point(3, 4)

        # 3-4-5 triangle
        distance = p1.distance(p2)
        assert distance == 5.0

        # Same points
        assert p1.distance(p1) == 0.0

        # Negative coordinates
        p3 = Point(-1, -1)
        p4 = Point(2, 3)
        expected = math.sqrt((2 - (-1)) ** 2 + (3 - (-1)) ** 2)  # sqrt(9 + 16) = 5
        assert p3.distance(p4) == expected

    def test_midpoint(self):
        """Test midpoint calculation."""
        p1 = Point(0, 0, "#FF0000")
        p2 = Point(4, 6, "#00FF00")

        mid = p1.midpoint_to(p2)
        assert mid.x == 2.0
        assert mid.y == 3.0
        assert mid.color is None  # Midpoint should have no color

        # Test with negative coordinates
        p3 = Point(-2, -4)
        p4 = Point(2, 4)
        mid2 = p3.midpoint_to(p4)
        assert mid2.x == 0.0
        assert mid2.y == 0.0

        # Test midpoint of same point
        mid3 = p1.midpoint_to(p1)
        assert mid3.x == p1.x
        assert mid3.y == p1.y

    def test_polar_coordinates_init(self):
        """Test that polar coordinates are calculated correctly at initialization."""
        # Origin point
        p_origin = Point(0, 0)
        assert p_origin.r == 0.0
        assert p_origin.theta == 0.0  # atan2(0, 0) returns 0

        # Point on positive X-axis
        p_x_axis = Point(5, 0)
        assert p_x_axis.r == 5.0
        assert p_x_axis.theta == 0.0

        # Point on positive Y-axis
        p_y_axis = Point(0, 3)
        assert p_y_axis.r == 3.0
        assert abs(p_y_axis.theta - math.pi / 2) < 1e-10

        # Point in first quadrant (3-4-5 triangle)
        p_q1 = Point(3, 4)
        assert p_q1.r == 5.0
        assert abs(p_q1.theta - math.atan2(4, 3)) < 1e-10

        # Point in second quadrant
        p_q2 = Point(-1, 1)
        expected_r = math.sqrt(2)
        expected_theta = math.atan2(1, -1)  # 3π/4
        assert abs(p_q2.r - expected_r) < 1e-10
        assert abs(p_q2.theta - expected_theta) < 1e-10

        # Point in third quadrant
        p_q3 = Point(-3, -4)
        assert p_q3.r == 5.0
        expected_theta_q3 = math.atan2(-4, -3)  # negative angle
        assert abs(p_q3.theta - expected_theta_q3) < 1e-10

        # Point in fourth quadrant
        p_q4 = Point(1, -1)
        expected_r_q4 = math.sqrt(2)
        expected_theta_q4 = math.atan2(-1, 1)  # -π/4
        assert abs(p_q4.r - expected_r_q4) < 1e-10
        assert abs(p_q4.theta - expected_theta_q4) < 1e-10

    def test_get_polar(self):
        """Test get_polar method returns correct tuple."""
        p = Point(3, 4, "#FF0000")
        r, theta = p.get_polar()

        assert r == 5.0
        assert abs(theta - math.atan2(4, 3)) < 1e-10

        # Verify it's the same as accessing properties directly
        assert r == p.r
        assert theta == p.theta

    def test_from_polar_creation(self):
        """Test creating Point from polar coordinates."""
        # Point on positive X-axis
        p1 = Point.from_polar(5, 0)
        assert abs(p1.x - 5.0) < 1e-10
        assert abs(p1.y - 0.0) < 1e-10
        assert p1.r == 5.0
        assert p1.theta == 0.0

        # Point on positive Y-axis
        p2 = Point.from_polar(3, math.pi / 2)
        assert abs(p2.x - 0.0) < 1e-10
        assert abs(p2.y - 3.0) < 1e-10
        assert p2.r == 3.0
        assert abs(p2.theta - math.pi / 2) < 1e-10

        # Point in first quadrant at 45 degrees
        p3 = Point.from_polar(math.sqrt(2), math.pi / 4)
        assert abs(p3.x - 1.0) < 1e-10
        assert abs(p3.y - 1.0) < 1e-10
        assert abs(p3.r - math.sqrt(2)) < 1e-10
        assert abs(p3.theta - math.pi / 4) < 1e-10

        # Point with color
        p4 = Point.from_polar(2, math.pi / 3, "#00FF00")
        expected_x = 2 * math.cos(math.pi / 3)  # 1.0
        expected_y = 2 * math.sin(math.pi / 3)  # sqrt(3)
        assert abs(p4.x - expected_x) < 1e-10
        assert abs(p4.y - expected_y) < 1e-10
        assert p4.color == "#00FF00"

    def test_polar_cartesian_conversion_round_trip(self):
        """Test that converting Cartesian -> Polar -> Cartesian gives original values."""
        test_points = [(0, 0), (1, 0), (0, 1), (3, 4), (-2, 3), (-1, -1), (5, -2)]

        for x, y in test_points:
            # Create point from Cartesian coordinates
            original = Point(x, y, "#TEST")

            # Get polar coordinates
            r, theta = original.get_polar()

            # Create new point from polar coordinates
            reconstructed = Point.from_polar(r, theta, "#TEST")

            # Should match original (within floating point precision)
            assert (
                abs(reconstructed.x - original.x) < 1e-10
            ), f"X mismatch for ({x}, {y})"
            assert (
                abs(reconstructed.y - original.y) < 1e-10
            ), f"Y mismatch for ({x}, {y})"
            assert reconstructed.color == original.color

    def test_polar_edge_cases(self):
        """Test polar coordinate edge cases."""
        # Very small coordinates (near zero)
        p_small = Point(1e-15, 1e-15)
        assert p_small.r >= 0  # Should be positive
        # theta can be anything for very small r, but should be finite
        assert math.isfinite(p_small.theta)

        # Large coordinates
        p_large = Point(1e10, 1e10)
        expected_r = math.sqrt(2e20)
        assert abs(p_large.r - expected_r) < 1e5  # Allow some floating point error
        assert abs(p_large.theta - math.pi / 4) < 1e-10

    def test_is_inside_polygon_rectangle(self):
        """Test point-in-polygon with a simple rectangle."""
        # Rectangle vertices: (0,0), (4,0), (4,3), (0,3)
        rect_vertices = [Point(0, 0), Point(4, 0), Point(4, 3), Point(0, 3)]

        # Points inside rectangle
        inside_points = [
            Point(2, 1.5),  # Center
            Point(1, 1),  # Near corner
            Point(3.5, 2.5),  # Near edge
            Point(0.1, 0.1),  # Very close to corner
        ]
        for point in inside_points:
            assert point.is_inside_polygon(
                rect_vertices
            ), f"Point {point.x}, {point.y} should be inside rectangle"

        # Points outside rectangle
        outside_points = [
            Point(-1, 1),  # Left of rectangle
            Point(5, 1),  # Right of rectangle
            Point(2, -1),  # Below rectangle
            Point(2, 4),  # Above rectangle
            Point(-1, -1),  # Bottom-left outside
            Point(5, 4),  # Top-right outside
        ]
        for point in outside_points:
            assert not point.is_inside_polygon(
                rect_vertices
            ), f"Point {point.x}, {point.y} should be outside rectangle"

        # Points on edges (ray casting can be ambiguous for edge cases)
        # Testing a few that should be deterministic
        edge_point = Point(2, 0)  # On bottom edge
        # Edge behavior can vary, so we just test that it returns a boolean
        result = edge_point.is_inside_polygon(rect_vertices)
        assert isinstance(result, bool)

    def test_is_inside_polygon_triangle(self):
        """Test point-in-polygon with a triangle."""
        # Triangle vertices: (0,0), (3,0), (1.5,3)
        triangle_vertices = [Point(0, 0), Point(3, 0), Point(1.5, 3)]

        # Points inside triangle
        inside_points = [
            Point(1.5, 1),  # Center-ish
            Point(1, 0.5),  # Near base
            Point(1.5, 2),  # Near top
        ]
        for point in inside_points:
            assert point.is_inside_polygon(
                triangle_vertices
            ), f"Point {point.x}, {point.y} should be inside triangle"

        # Points outside triangle
        outside_points = [
            Point(-1, 0),  # Left of triangle
            Point(4, 0),  # Right of triangle
            Point(1.5, -1),  # Below triangle
            Point(1.5, 4),  # Above triangle
            Point(0, 2),  # Left of triangle slope
            Point(3, 2),  # Right of triangle slope
        ]
        for point in outside_points:
            assert not point.is_inside_polygon(
                triangle_vertices
            ), f"Point {point.x}, {point.y} should be outside triangle"

    def test_is_inside_polygon_complex_shape(self):
        """Test point-in-polygon with a more complex (concave) polygon."""
        # L-shaped polygon
        l_vertices = [
            Point(0, 0),
            Point(3, 0),
            Point(3, 1),
            Point(1, 1),
            Point(1, 3),
            Point(0, 3),
        ]

        # Points inside L-shape
        inside_points = [
            Point(0.5, 0.5),  # Bottom-left part
            Point(2, 0.5),  # Bottom-right part
            Point(0.5, 2),  # Top-left part
        ]
        for point in inside_points:
            assert point.is_inside_polygon(
                l_vertices
            ), f"Point {point.x}, {point.y} should be inside L-shape"

        # Points outside L-shape (including the "notch")
        outside_points = [
            Point(2, 2),  # In the notch (outside)
            Point(-1, 1),  # Left of shape
            Point(4, 1),  # Right of shape
            Point(1, 4),  # Above shape
            Point(1, -1),  # Below shape
        ]
        for point in outside_points:
            assert not point.is_inside_polygon(
                l_vertices
            ), f"Point {point.x}, {point.y} should be outside L-shape"

    def test_is_inside_polygon_edge_cases(self):
        """Test edge cases for point-in-polygon algorithm."""
        # Empty polygon
        empty_vertices = []
        test_point = Point(1, 1)
        assert not test_point.is_inside_polygon(empty_vertices)

        # Single point "polygon"
        single_vertex = [Point(0, 0)]
        assert not test_point.is_inside_polygon(single_vertex)

        # Two point "polygon" (line segment)
        line_vertices = [Point(0, 0), Point(2, 0)]
        assert not test_point.is_inside_polygon(line_vertices)

        # Degenerate triangle (collinear points)
        collinear_vertices = [Point(0, 0), Point(1, 1), Point(2, 2)]
        test_point_on_line = Point(0.5, 0.5)
        result = test_point_on_line.is_inside_polygon(collinear_vertices)
        assert isinstance(result, bool)  # Should handle gracefully

    def test_is_inside_polygon_with_colors(self):
        """Test that point colors don't affect polygon testing."""
        # Rectangle with colored vertices
        colored_vertices = [
            Point(0, 0, "#FF0000"),
            Point(2, 0, "#00FF00"),
            Point(2, 2, "#0000FF"),
            Point(0, 2, "#FFFF00"),
        ]

        # Colored test point
        colored_point = Point(1, 1, "#FF00FF")
        assert colored_point.is_inside_polygon(colored_vertices)

        # Uncolored test point
        uncolored_point = Point(1, 1)
        assert uncolored_point.is_inside_polygon(colored_vertices)

    def test_is_inside_polygon_precision(self):
        """Test point-in-polygon with floating point precision challenges."""
        # Very small polygon
        tiny_vertices = [
            Point(0, 0),
            Point(1e-10, 0),
            Point(1e-10, 1e-10),
            Point(0, 1e-10),
        ]
        tiny_point = Point(5e-11, 5e-11)  # Should be inside
        result = tiny_point.is_inside_polygon(tiny_vertices)
        assert isinstance(result, bool)  # Should handle without crashing

        # Very large polygon
        huge_vertices = [Point(0, 0), Point(1e10, 0), Point(1e10, 1e10), Point(0, 1e10)]
        huge_point = Point(5e9, 5e9)  # Should be inside
        assert huge_point.is_inside_polygon(huge_vertices)

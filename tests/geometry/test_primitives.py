"""Tests for geometric primitive classes."""

import pytest
from luminary.geometry.point import Point
from luminary.geometry.primitives import Segment, Ray, Line, Polygon, OrientedSegment


class TestSegment:
    """Test cases for Segment class."""

    def test_segment_init(self):
        """Test Segment initialization."""
        p1, p2 = Point(0, 0), Point(2, 2)
        segment = Segment(p1, p2)
        assert segment.p1 == p1
        assert segment.p2 == p2

    def test_segment_segment_intersection(self):
        """Test intersection between two segments."""
        # Crossing segments
        seg1 = Segment(Point(0, 0), Point(2, 2))
        seg2 = Segment(Point(0, 2), Point(2, 0))
        intersection = seg1.intersection(seg2)
        assert intersection is not None
        assert abs(intersection.x - 1.0) < 1e-10
        assert abs(intersection.y - 1.0) < 1e-10

        # Non-intersecting segments
        seg3 = Segment(Point(0, 0), Point(1, 1))
        seg4 = Segment(Point(2, 2), Point(3, 3))
        assert seg3.intersection(seg4) is None

        # Parallel segments
        seg5 = Segment(Point(0, 0), Point(1, 0))
        seg6 = Segment(Point(0, 1), Point(1, 1))
        assert seg5.intersection(seg6) is None

    def test_segment_ray_intersection(self):
        """Test intersection between segment and ray."""
        segment = Segment(Point(1, 0), Point(1, 2))
        ray = Ray(Point(0, 1), Point(2, 1))  # Ray from (0,1) through (2,1)
        intersection = segment.intersection(ray)
        assert intersection is not None
        assert abs(intersection.x - 1.0) < 1e-10
        assert abs(intersection.y - 1.0) < 1e-10

        # Segment and ray that don't intersect
        ray_miss = Ray(Point(0, 3), Point(2, 3))  # Ray above the segment
        assert segment.intersection(ray_miss) is None

    def test_segment_line_intersection(self):
        """Test intersection between segment and line."""
        segment = Segment(Point(1, 0), Point(1, 2))
        line = Line(Point(0, 1), Point(2, 1))  # Line through (0,1) and (2,1)
        intersection = segment.intersection(line)
        assert intersection is not None
        assert abs(intersection.x - 1.0) < 1e-10
        assert abs(intersection.y - 1.0) < 1e-10


class TestRay:
    """Test cases for Ray class."""

    def test_ray_init(self):
        """Test Ray initialization."""
        p1, p2 = Point(0, 0), Point(1, 1)
        ray = Ray(p1, p2)
        assert ray.p1 == p1
        assert ray.p2 == p2

    def test_ray_segment_intersection(self):
        """Test intersection between ray and segment."""
        ray = Ray(Point(0, 0), Point(2, 2))  # Ray from origin through (2,2)
        segment = Segment(Point(1, 0), Point(1, 3))  # Vertical segment
        intersection = ray.intersection(segment)
        assert intersection is not None
        assert abs(intersection.x - 1.0) < 1e-10
        assert abs(intersection.y - 1.0) < 1e-10

    def test_ray_ray_intersection(self):
        """Test intersection between two rays."""
        ray1 = Ray(Point(0, 0), Point(2, 2))
        ray2 = Ray(Point(0, 2), Point(2, 0))
        intersection = ray1.intersection(ray2)
        assert intersection is not None
        assert abs(intersection.x - 1.0) < 1e-10
        assert abs(intersection.y - 1.0) < 1e-10

        # Rays pointing away from each other
        ray3 = Ray(Point(2, 2), Point(0, 0))  # Backward ray
        assert ray1.intersection(ray3) is None

    def test_ray_line_intersection(self):
        """Test intersection between ray and line."""
        ray = Ray(Point(0, 0), Point(2, 2))
        line = Line(Point(1, 0), Point(1, 3))
        intersection = ray.intersection(line)
        assert intersection is not None
        assert abs(intersection.x - 1.0) < 1e-10
        assert abs(intersection.y - 1.0) < 1e-10


class TestLine:
    """Test cases for Line class."""

    def test_line_init(self):
        """Test Line initialization."""
        p1, p2 = Point(0, 0), Point(1, 1)
        line = Line(p1, p2)
        assert line.p1 == p1
        assert line.p2 == p2

    def test_line_segment_intersection(self):
        """Test intersection between line and segment."""
        line = Line(Point(0, 1), Point(2, 1))  # Horizontal line
        segment = Segment(Point(1, 0), Point(1, 2))  # Vertical segment
        intersection = line.intersection(segment)
        assert intersection is not None
        assert abs(intersection.x - 1.0) < 1e-10
        assert abs(intersection.y - 1.0) < 1e-10

        # Line and segment that don't intersect
        short_segment = Segment(Point(1, 2), Point(1, 3))  # Above intersection
        assert line.intersection(short_segment) is None

    def test_line_ray_intersection(self):
        """Test intersection between line and ray."""
        line = Line(Point(0, 1), Point(2, 1))
        ray = Ray(Point(1, 0), Point(1, 2))
        intersection = line.intersection(ray)
        assert intersection is not None
        assert abs(intersection.x - 1.0) < 1e-10
        assert abs(intersection.y - 1.0) < 1e-10

    def test_line_line_intersection(self):
        """Test intersection between two lines."""
        line1 = Line(Point(0, 0), Point(2, 2))  # Diagonal line
        line2 = Line(Point(0, 2), Point(2, 0))  # Opposite diagonal
        intersection = line1.intersection(line2)
        assert intersection is not None
        assert abs(intersection.x - 1.0) < 1e-10
        assert abs(intersection.y - 1.0) < 1e-10

        # Parallel lines
        line3 = Line(Point(0, 0), Point(1, 0))
        line4 = Line(Point(0, 1), Point(1, 1))
        assert line3.intersection(line4) is None


class TestLinearElementEdgeCases:
    """Test edge cases for all linear elements."""

    def test_parallel_elements(self):
        """Test parallel elements return None for intersections."""
        seg1 = Segment(Point(0, 0), Point(1, 0))
        seg2 = Segment(Point(0, 1), Point(1, 1))
        ray = Ray(Point(0, 2), Point(1, 2))
        line = Line(Point(0, 3), Point(1, 3))

        assert seg1.intersection(seg2) is None
        assert seg1.intersection(ray) is None
        assert seg1.intersection(line) is None
        assert ray.intersection(line) is None

    def test_coincident_elements(self):
        """Test elements that lie on the same line."""
        # Same line, overlapping segments
        seg1 = Segment(Point(0, 0), Point(2, 0))
        seg2 = Segment(Point(1, 0), Point(3, 0))
        # These are parallel with denom=0, so should return None
        assert seg1.intersection(seg2) is None

    def test_endpoint_intersections(self):
        """Test intersections at endpoints."""
        seg1 = Segment(Point(0, 0), Point(1, 1))
        seg2 = Segment(Point(1, 1), Point(2, 0))
        intersection = seg1.intersection(seg2)
        assert intersection is not None
        assert abs(intersection.x - 1.0) < 1e-10
        assert abs(intersection.y - 1.0) < 1e-10


class TestPolygon:
    """Test cases for Polygon class."""

    def test_polygon_init(self):
        """Test Polygon initialization."""
        vertices = [Point(0, 0), Point(2, 0), Point(2, 2), Point(0, 2)]
        polygon = Polygon(vertices)
        assert polygon.vertices == vertices
        assert len(polygon.vertices) == 4

    def test_polygon_is_inside_rectangle(self):
        """Test Polygon.is_inside with a rectangle."""
        # Rectangle vertices: (0,0), (4,0), (4,3), (0,3)
        rect_vertices = [Point(0, 0), Point(4, 0), Point(4, 3), Point(0, 3)]
        rectangle = Polygon(rect_vertices)

        # Point inside rectangle
        inside_point = Point(2, 1.5)
        assert rectangle.is_inside(inside_point)

        # Point outside rectangle
        outside_point = Point(5, 1)
        assert not rectangle.is_inside(outside_point)

    def test_polygon_is_inside_triangle(self):
        """Test Polygon.is_inside with a triangle."""
        # Triangle vertices: (0,0), (3,0), (1.5,3)
        triangle_vertices = [Point(0, 0), Point(3, 0), Point(1.5, 3)]
        triangle = Polygon(triangle_vertices)

        # Point inside triangle
        inside_point = Point(1.5, 1)
        assert triangle.is_inside(inside_point)

        # Point outside triangle
        outside_point = Point(1.5, 4)
        assert not triangle.is_inside(outside_point)

    def test_polygon_empty_vertices(self):
        """Test Polygon with empty vertices list."""
        empty_polygon = Polygon([])
        test_point = Point(1, 1)
        assert not empty_polygon.is_inside(test_point)


class TestOrientedSegment:
    """Test cases for OrientedSegment class."""

    def test_oriented_segment_init_valid(self):
        """Test OrientedSegment initialization with valid dict."""
        labeled_points = {"port": Point(0, 0), "starboard": Point(5, 0)}
        segment = OrientedSegment(labeled_points)

        assert segment.p1 == Point(0, 0)
        assert segment.p2 == Point(5, 0)
        assert segment.p1_label == "port"
        assert segment.p2_label == "starboard"

    def test_oriented_segment_init_wrong_count(self):
        """Test OrientedSegment initialization with wrong number of points."""
        # Too few points
        with pytest.raises(
            ValueError, match="requires exactly 2 labeled points, got 1"
        ):
            OrientedSegment({"port": Point(0, 0)})

        # Too many points
        with pytest.raises(
            ValueError, match="requires exactly 2 labeled points, got 3"
        ):
            OrientedSegment(
                {"port": Point(0, 0), "starboard": Point(5, 0), "center": Point(2.5, 0)}
            )

    def test_oriented_segment_get_point_by_label(self):
        """Test getting points by their labels."""
        labeled_points = {"port": Point(0, 0), "starboard": Point(5, 0)}
        segment = OrientedSegment(labeled_points)

        assert segment.get_point_by_label("port") == Point(0, 0)
        assert segment.get_point_by_label("starboard") == Point(5, 0)

    def test_oriented_segment_get_point_by_invalid_label(self):
        """Test getting point with invalid label raises error."""
        labeled_points = {"port": Point(0, 0), "starboard": Point(5, 0)}
        segment = OrientedSegment(labeled_points)

        with pytest.raises(ValueError, match="Label 'bow' not found"):
            segment.get_point_by_label("bow")

    def test_oriented_segment_assert_labels_valid(self):
        """Test assert_labels with correct labels."""
        labeled_points = {"port": Point(0, 0), "starboard": Point(5, 0)}
        segment = OrientedSegment(labeled_points)

        # Should not raise
        segment.assert_labels({"port", "starboard"})

    def test_oriented_segment_assert_labels_invalid(self):
        """Test assert_labels with incorrect labels."""
        labeled_points = {"port": Point(0, 0), "starboard": Point(5, 0)}
        segment = OrientedSegment(labeled_points)

        with pytest.raises(AssertionError, match="Expected labels"):
            segment.assert_labels({"bow", "stern"})

    def test_oriented_segment_inherits_segment_methods(self):
        """Test that OrientedSegment inherits Segment functionality."""
        labeled_points = {"start": Point(0, 0), "end": Point(3, 4)}
        segment = OrientedSegment(labeled_points)

        # Should inherit length method
        assert segment.length() == 5.0  # 3-4-5 triangle

        # Should inherit intersection method
        other_segment = Segment(Point(0, 2), Point(3, 2))
        intersection = segment.intersection(other_segment)
        assert intersection is not None
        # Line from (0,0) to (3,4) intersects horizontal line y=2 at x=1.5
        assert abs(intersection.x - 1.5) < 0.001
        assert abs(intersection.y - 2.0) < 0.001

    def test_oriented_segment_custom_labels(self):
        """Test OrientedSegment with custom label names."""
        labeled_points = {"start": Point(1, 1), "finish": Point(4, 5)}
        segment = OrientedSegment(labeled_points)

        assert segment.get_point_by_label("start") == Point(1, 1)
        assert segment.get_point_by_label("finish") == Point(4, 5)
        segment.assert_labels({"start", "finish"})

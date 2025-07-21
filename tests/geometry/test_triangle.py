"""Tests for Triangle class."""

import pytest
import math
from luminary.geometry.point import Point
from luminary.geometry.triangle import Triangle, Orientation


class TestTriangle:
    """Test cases for Triangle class."""

    def test_triangle_initialization(self):
        """Test Triangle initialization."""
        p1 = Point(0, 0)
        p2 = Point(3, 0)
        p3 = Point(1.5, 2.598)  # Approximately equilateral triangle
        apex = Point(1.5, 1)

        triangle = Triangle(p1, p2, p3, 42, apex)

        assert triangle.vertices == [p1, p2, p3]
        assert triangle.triangle_id == 42
        assert triangle.apex == apex
        assert triangle.incenter is not None
        assert len(triangle.edge_midpoints) == 3
        assert triangle.orientation in [Orientation.APEXWARD, Orientation.NADIRWARD]
        assert len(triangle.kites) == 3  # Should create 3 kites

    def test_incenter_calculation_equilateral(self):
        """Test incenter calculation for equilateral triangle."""
        # Equilateral triangle with vertices at (0,0), (2,0), (1,√3)
        p1 = Point(0, 0)
        p2 = Point(2, 0)
        p3 = Point(1, math.sqrt(3))
        apex = Point(1, 0.5)

        triangle = Triangle(p1, p2, p3, 1, apex)

        # Incenter should be at centroid for equilateral triangle
        expected_x = (0 + 2 + 1) / 3
        expected_y = (0 + 0 + math.sqrt(3)) / 3

        assert abs(triangle.incenter.x - expected_x) < 0.001
        assert abs(triangle.incenter.y - expected_y) < 0.001

    def test_incenter_calculation_right_triangle(self):
        """Test incenter calculation for right triangle."""
        # Right triangle at origin
        p1 = Point(0, 0)
        p2 = Point(4, 0)
        p3 = Point(0, 3)
        apex = Point(0, 0)

        triangle = Triangle(p1, p2, p3, 2, apex)

        # For a 3-4-5 right triangle, incenter should be at (1, 1)
        assert abs(triangle.incenter.x - 1) < 0.001
        assert abs(triangle.incenter.y - 1) < 0.001

    def test_orientation_apexward(self):
        """Test APEXWARD orientation detection."""
        # Triangle with one vertex pointing toward apex
        apex = Point(0, 0)
        p1 = Point(1, 0)  # Closest vertex to apex
        p2 = Point(2, 2)  # Far vertex
        p3 = Point(2, -2)  # Far vertex

        triangle = Triangle(p1, p2, p3, 3, apex)

        assert triangle.orientation == Orientation.APEXWARD

    def test_orientation_nadirward(self):
        """Test NADIRWARD orientation detection."""
        # Triangle with two vertices closer to apex than incenter
        apex = Point(0, 0)
        p1 = Point(1, 0.5)  # Close vertex
        p2 = Point(1, -0.5)  # Close vertex
        p3 = Point(5, 0)  # Far vertex

        triangle = Triangle(p1, p2, p3, 4, apex)

        assert triangle.orientation == Orientation.NADIRWARD

    def test_edge_midpoints(self):
        """Test edge midpoint calculations."""
        p1 = Point(0, 0)
        p2 = Point(4, 0)
        p3 = Point(2, 4)
        apex = Point(2, 2)

        triangle = Triangle(p1, p2, p3, 5, apex)

        expected_midpoints = [
            Point(2, 0),  # Midpoint of p1-p2
            Point(3, 2),  # Midpoint of p2-p3
            Point(1, 2),  # Midpoint of p1-p3
        ]

        for i, midpoint in enumerate(triangle.edge_midpoints):
            assert abs(midpoint.x - expected_midpoints[i].x) < 0.001
            assert abs(midpoint.y - expected_midpoints[i].y) < 0.001

    def test_degenerate_triangle(self):
        """Test handling of degenerate triangle (zero area)."""
        # Collinear points
        p1 = Point(0, 0)
        p2 = Point(1, 0)
        p3 = Point(2, 0)
        apex = Point(1, 1)

        triangle = Triangle(p1, p2, p3, 6, apex)

        # Should return centroid for degenerate triangle
        expected_x = (0 + 1 + 2) / 3
        expected_y = (0 + 0 + 0) / 3

        assert abs(triangle.incenter.x - expected_x) < 0.001
        assert abs(triangle.incenter.y - expected_y) < 0.001

    def test_svg_generation(self):
        """Test basic SVG generation."""
        p1 = Point(0, 0)
        p2 = Point(10, 0)
        p3 = Point(5, 8)
        apex = Point(5, 4)

        triangle = Triangle(p1, p2, p3, 7, apex)
        svg_elements = triangle.get_svg()

        assert len(svg_elements) == 2
        assert "polygon" in svg_elements[0]
        assert 'fill-opacity="0.4"' in svg_elements[0]
        assert "circle" in svg_elements[1]
        assert 'r="1.5"' in svg_elements[1]

    def test_get_vertices(self):
        """Test get_vertices returns copy."""
        p1 = Point(1, 1)
        p2 = Point(2, 2)
        p3 = Point(3, 3)
        apex = Point(0, 0)

        triangle = Triangle(p1, p2, p3, 8, apex)
        vertices = triangle.get_vertices()

        assert vertices == [p1, p2, p3]
        assert vertices is not triangle.vertices  # Should be a copy

    def test_get_kites(self):
        """Test get_kites returns three kites."""
        p1 = Point(0, 0, "#FF0000")
        p2 = Point(1, 0, "#00FF00")
        p3 = Point(0.5, 1, "#0000FF")
        apex = Point(0.5, 0.5)

        triangle = Triangle(p1, p2, p3, 9, apex)
        kites = triangle.get_kites()

        assert len(kites) == 3  # Triangle should create 3 kites
        assert kites is not triangle.kites  # Should be a copy

        # Check that kites inherit vertex colors (order may vary due to counterclockwise ordering)
        colors = [kite.color for kite in kites]
        expected_colors = {"#FF0000", "#00FF00", "#0000FF"}
        assert set(colors) == expected_colors  # All colors should be present

    def test_kite_labeling_by_orientation(self):
        """Test that kites get correct labels based on triangle orientation."""
        apex = Point(250, 200)

        # APEXWARD triangle should get A-C labels
        t1_p1 = Point(240, 190)  # Close to apex
        t1_p2 = Point(200, 100)  # Far from apex
        t1_p3 = Point(150, 150)  # Far from apex
        triangle1 = Triangle(t1_p1, t1_p2, t1_p3, 1, apex)

        assert triangle1.orientation == Orientation.APEXWARD
        kites1 = triangle1.get_kites()
        assert [kite.label for kite in kites1] == [
            "1A",
            "1B",
            "1C",
        ]  # Labels now include triangle ID

        # NADIRWARD triangle should get D-F labels
        t2_p1 = Point(260, 190)  # Close to apex
        t2_p2 = Point(240, 190)  # Close to apex
        t2_p3 = Point(400, 100)  # Far from apex
        triangle2 = Triangle(t2_p1, t2_p2, t2_p3, 2, apex)

        assert triangle2.orientation == Orientation.NADIRWARD
        kites2 = triangle2.get_kites()
        assert [kite.label for kite in kites2] == [
            "2D",
            "2E",
            "2F",
        ]  # Labels now include triangle ID

    def test_counterclockwise_kite_ordering(self):
        """Test that kites are ordered counterclockwise from A/D kite."""
        apex = Point(5, 5)  # Place apex away from triangle

        # Test APEXWARD triangle - only 1 vertex close to apex
        p1 = Point(4, 4, "red")  # Closest to apex
        p2 = Point(0, 0, "green")  # Far from apex
        p3 = Point(10, 0, "blue")  # Far from apex
        triangle = Triangle(p1, p2, p3, 1, apex)

        assert triangle.orientation == Orientation.APEXWARD
        kites = triangle.get_kites()

        # A kite should be the one closest to apex (p1 = red)
        assert kites[0].color == "red"
        assert kites[0].label == "1A"

        # Verify all three colors are present and counterclockwise ordering
        colors = [kite.color for kite in kites]
        labels = [kite.label for kite in kites]
        assert colors[0] == "red"  # A kite (closest to apex)
        assert labels == ["1A", "1B", "1C"]  # Counterclockwise order
        assert len(set(colors)) == 3  # All three colors present

        # Test NADIRWARD triangle - 2+ vertices close to apex
        p4 = Point(0, 0, "red")  # Furthest from apex
        p5 = Point(4.5, 4.5, "green")  # Close to apex
        p6 = Point(5.5, 5.5, "blue")  # Close to apex
        triangle2 = Triangle(p4, p5, p6, 2, apex)

        assert triangle2.orientation == Orientation.NADIRWARD
        kites2 = triangle2.get_kites()

        # D kite should be the one furthest from apex (p4 = red)
        assert kites2[0].color == "red"
        assert kites2[0].label == "2D"

        # Verify counterclockwise ordering for NADIRWARD
        labels2 = [kite.label for kite in kites2]
        assert labels2 == ["2D", "2E", "2F"]  # Counterclockwise order

    def test_validation_triangle_orientations(self):
        """Test orientations match validation triangles exactly."""
        # Use exact same coordinates as validation to ensure consistency
        apex = Point(250, 200)  # Central reference point

        # Triangle 1: APEXWARD - one vertex close to apex
        t1_p1 = Point(240, 190)  # Close to apex
        t1_p2 = Point(200, 100)  # Far from apex
        t1_p3 = Point(150, 150)  # Far from apex
        triangle1 = Triangle(t1_p1, t1_p2, t1_p3, 1, apex)

        # Triangle 2: NADIRWARD - two vertices close to apex
        t2_p1 = Point(260, 190)  # Close to apex
        t2_p2 = Point(240, 190)  # Close to apex
        t2_p3 = Point(400, 100)  # Far from apex
        triangle2 = Triangle(t2_p1, t2_p2, t2_p3, 2, apex)

        # Triangle 3: Equilateral - depends on apex position
        t3_p1 = Point(350, 300)
        t3_p2 = Point(450, 300)
        t3_p3 = Point(400, 213.4)  # Approximately equilateral
        triangle3 = Triangle(t3_p1, t3_p2, t3_p3, 3, apex)

        # Verify orientations match validation expectations
        assert (
            triangle1.orientation == Orientation.APEXWARD
        ), f"T1 should be APEXWARD, got {triangle1.orientation}"
        assert (
            triangle2.orientation == Orientation.NADIRWARD
        ), f"T2 should be NADIRWARD, got {triangle2.orientation}"
        assert (
            triangle3.orientation == Orientation.NADIRWARD
        ), f"T3 should be NADIRWARD, got {triangle3.orientation}"

    def test_validation_triangle_vertex_distances(self):
        """Test vertex distance logic for validation triangles."""
        apex = Point(250, 200)

        # Triangle 1: APEXWARD - exactly 1 vertex closer than incenter
        t1_p1 = Point(240, 190)  # Close to apex
        t1_p2 = Point(200, 100)  # Far from apex
        t1_p3 = Point(150, 150)  # Far from apex
        triangle1 = Triangle(t1_p1, t1_p2, t1_p3, 1, apex)

        incenter_to_apex = Point.distance(triangle1.incenter, apex)
        vertices_closer = [
            vertex
            for vertex in triangle1.vertices
            if Point.distance(vertex, apex) < incenter_to_apex
        ]
        assert (
            len(vertices_closer) == 1
        ), f"T1 should have exactly 1 vertex closer to apex, got {len(vertices_closer)}"

        # Triangle 2: NADIRWARD - exactly 2 vertices closer than incenter
        t2_p1 = Point(260, 190)  # Close to apex
        t2_p2 = Point(240, 190)  # Close to apex
        t2_p3 = Point(400, 100)  # Far from apex
        triangle2 = Triangle(t2_p1, t2_p2, t2_p3, 2, apex)

        incenter_to_apex = Point.distance(triangle2.incenter, apex)
        vertices_closer = [
            vertex
            for vertex in triangle2.vertices
            if Point.distance(vertex, apex) < incenter_to_apex
        ]
        assert (
            len(vertices_closer) == 2
        ), f"T2 should have exactly 2 vertices closer to apex, got {len(vertices_closer)}"

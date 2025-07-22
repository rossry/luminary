"""Tests for Facet class."""

import pytest
from luminary.geometry.point import Point
from luminary.geometry.facet import Facet


class TestFacet:
    """Test cases for Facet class."""

    def test_facet_initialization(self):
        """Test Facet initialization."""
        vertex = Point(0, 0, "#FF0000")
        midpoint1 = Point(5, 0)
        incenter = Point(3, 3)
        midpoint2 = Point(0, 5)

        facet = Facet(vertex, midpoint1, incenter, midpoint2, "#FF0000", "A")

        assert facet.vertices == [vertex, midpoint1, incenter, midpoint2]
        assert facet.color == "#FF0000"
        assert facet.label == "A"
        assert facet.centroid is not None

    def test_centroid_calculation(self):
        """Test centroid calculation."""
        # Square facet for easy calculation
        vertex = Point(0, 0)
        midpoint1 = Point(4, 0)
        incenter = Point(4, 4)
        midpoint2 = Point(0, 4)

        facet = Facet(vertex, midpoint1, incenter, midpoint2, "#00FF00", "B")

        # Centroid should be at (2, 2) for this square
        assert facet.centroid.x == 2.0
        assert facet.centroid.y == 2.0
        assert facet.centroid.color is None  # Centroid has no color

    def test_centroid_calculation_irregular_facet(self):
        """Test centroid calculation for irregular facet."""
        vertex = Point(1, 1)
        midpoint1 = Point(5, 2)
        incenter = Point(3, 6)
        midpoint2 = Point(2, 4)

        facet = Facet(vertex, midpoint1, incenter, midpoint2, "#0000FF", "D")

        # Centroid = ((1+5+3+2)/4, (1+2+6+4)/4) = (2.75, 3.25)
        assert abs(facet.centroid.x - 2.75) < 0.001
        assert abs(facet.centroid.y - 3.25) < 0.001

    def test_get_vertices_returns_copy(self):
        """Test get_vertices returns copy."""
        vertex = Point(0, 0)
        midpoint1 = Point(1, 0)
        incenter = Point(1, 1)
        midpoint2 = Point(0, 1)

        facet = Facet(vertex, midpoint1, incenter, midpoint2, "#FFFF00", "C")
        vertices = facet.get_vertices()

        assert vertices == facet.vertices
        assert vertices is not facet.vertices  # Should be a copy

    def test_get_centroid(self):
        """Test get_centroid method."""
        vertex = Point(2, 2)
        midpoint1 = Point(6, 2)
        incenter = Point(6, 6)
        midpoint2 = Point(2, 6)

        facet = Facet(vertex, midpoint1, incenter, midpoint2, "#FF00FF", "E")
        centroid = facet.get_centroid()

        assert centroid.x == 4.0
        assert centroid.y == 4.0
        assert centroid is facet.centroid  # Should be same object

    def test_svg_generation(self):
        """Test SVG generation."""
        vertex = Point(0, 0, "#00CED1")
        midpoint1 = Point(10, 0)
        incenter = Point(5, 5)
        midpoint2 = Point(0, 10)

        facet = Facet(vertex, midpoint1, incenter, midpoint2, "#00CED1", "F")
        svg_elements = facet.get_svg()

        assert len(svg_elements) == 2

        # First element should be polygon with 60% opacity
        polygon_svg = svg_elements[0]
        assert "polygon" in polygon_svg
        assert 'fill="#00CED1"' in polygon_svg
        assert 'fill-opacity="0.6"' in polygon_svg
        assert 'points="0,0 10,0 5,5 0,10"' in polygon_svg

        # Second element should be text label with 70% opacity
        text_svg = svg_elements[1]
        assert "text" in text_svg
        assert 'font-size="10"' in text_svg
        assert 'fill="black"' in text_svg
        assert 'fill-opacity="0.7"' in text_svg
        assert ">F<" in text_svg  # Contains the label
        assert 'x="3.75"' in text_svg  # Centroid x position
        assert 'y="3.75"' in text_svg  # Centroid y position

    def test_facet_with_different_labels(self):
        """Test facets with different label types."""
        vertex = Point(0, 0)
        midpoint1 = Point(1, 0)
        incenter = Point(1, 1)
        midpoint2 = Point(0, 1)

        # Test APEXWARD labels (A-C)
        facet_a = Facet(vertex, midpoint1, incenter, midpoint2, "#FF0000", "A")
        facet_b = Facet(vertex, midpoint1, incenter, midpoint2, "#00FF00", "B")
        facet_c = Facet(vertex, midpoint1, incenter, midpoint2, "#0000FF", "C")

        assert facet_a.label == "A"
        assert facet_b.label == "B"
        assert facet_c.label == "C"

        # Test NADIRWARD labels (D-F)
        facet_d = Facet(vertex, midpoint1, incenter, midpoint2, "#FFFF00", "D")
        facet_e = Facet(vertex, midpoint1, incenter, midpoint2, "#FF00FF", "E")
        facet_f = Facet(vertex, midpoint1, incenter, midpoint2, "#00FFFF", "F")

        assert facet_d.label == "D"
        assert facet_e.label == "E"
        assert facet_f.label == "F"

    def test_facet_color_inheritance(self):
        """Test that facet color matches specification."""
        vertex_color = "#228B22"
        vertex = Point(0, 0, vertex_color)
        midpoint1 = Point(1, 0)
        incenter = Point(1, 1)
        midpoint2 = Point(0, 1)

        facet = Facet(vertex, midpoint1, incenter, midpoint2, vertex_color, "A")

        assert facet.color == vertex_color

        svg_elements = facet.get_svg()
        polygon_svg = svg_elements[0]
        assert f'fill="{vertex_color}"' in polygon_svg

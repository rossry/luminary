"""Tests for SVG utility functions."""

import pytest
from luminary.geometry.point import Point
from luminary.writers.svg.utilities import (
    create_svg_header,
    create_rect_svg,
    create_polygon_svg,
    create_circle_svg,
    create_line_svg,
    create_text_svg,
)


class TestSVGUtilities:
    """Test cases for SVG utility functions."""

    def test_create_svg_header(self):
        """Test SVG header generation."""
        result = create_svg_header("-10 -10 120 120", "100%", "400")
        expected = '<svg width="100%" height="400" viewBox="-10 -10 120 120" xmlns="http://www.w3.org/2000/svg">'
        assert result == expected

    def test_create_rect_svg(self):
        """Test rectangle generation."""
        result = create_rect_svg(10, 20, 100, 50, "white")
        expected = '  <rect x="10" y="20" width="100" height="50" fill="white"/>'
        assert result == expected

        # Test with negative coordinates
        result2 = create_rect_svg(-5, -10, 50, 25, "#FF0000")
        expected2 = '  <rect x="-5" y="-10" width="50" height="25" fill="#FF0000"/>'
        assert result2 == expected2

    def test_create_polygon_svg(self):
        """Test polygon generation."""
        points = [Point(0, 0), Point(10, 0), Point(5, 8.66)]

        # Without stroke
        result = create_polygon_svg(points, "#FF0000", 0.5)
        expected = (
            '  <polygon points="0,0 10,0 5,8.66" fill="#FF0000" fill-opacity="0.5"/>'
        )
        assert result == expected

        # With stroke
        result2 = create_polygon_svg(points, "#00FF00", 0.8, "#000000")
        expected2 = '  <polygon points="0,0 10,0 5,8.66" fill="#00FF00" fill-opacity="0.8" stroke="#000000"/>'
        assert result2 == expected2

    def test_create_circle_svg(self):
        """Test circle generation."""
        center = Point(50, 50)

        # Without stroke
        result = create_circle_svg(center, 10, "#0000FF")
        expected = '  <circle cx="50" cy="50" r="10" fill="#0000FF"/>'
        assert result == expected

        # With stroke
        result2 = create_circle_svg(center, 15, "red", "black", 2)
        expected2 = '  <circle cx="50" cy="50" r="15" fill="red" stroke="black" stroke-width="2"/>'
        assert result2 == expected2

        # With stroke but zero width (should ignore stroke)
        result3 = create_circle_svg(center, 5, "green", "blue", 0)
        expected3 = '  <circle cx="50" cy="50" r="5" fill="green"/>'
        assert result3 == expected3

    def test_create_line_svg(self):
        """Test line generation."""
        p1 = Point(0, 0)
        p2 = Point(100, 50)

        result = create_line_svg(p1, p2, "black", 2)
        expected = (
            '  <line x1="0" y1="0" x2="100" y2="50" stroke="black" stroke-width="2"/>'
        )
        assert result == expected

        # Test with negative coordinates
        p3 = Point(-10, -5)
        p4 = Point(10, 5)
        result2 = create_line_svg(p3, p4, "#FF00FF", 1.5)
        expected2 = '  <line x1="-10" y1="-5" x2="10" y2="5" stroke="#FF00FF" stroke-width="1.5"/>'
        assert result2 == expected2

    def test_create_text_svg(self):
        """Test text generation."""
        position = Point(25, 30)

        result = create_text_svg("Hello", position, 12, "black", 0.7)
        expected = '  <text x="25" y="30" font-family="Arial" font-size="12" fill="black" fill-opacity="0.7" text-anchor="middle">Hello</text>'
        assert result == expected

        # Test with different parameters
        result2 = create_text_svg("A", Point(0, 0), 10, "#FF0000", 1.0)
        expected2 = '  <text x="0" y="0" font-family="Arial" font-size="10" fill="#FF0000" fill-opacity="1.0" text-anchor="middle">A</text>'
        assert result2 == expected2

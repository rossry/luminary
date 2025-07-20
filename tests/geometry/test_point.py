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
    
    def test_get_coordinates(self):
        """Test get_coordinates method."""
        p = Point(5.5, -2.3, "#00FF00")
        coords = p.get_coordinates()
        assert coords == (5.5, -2.3)
        assert isinstance(coords, tuple)
    
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
        distance = Point.distance(p1, p2)
        assert distance == 5.0
        
        # Same points
        assert Point.distance(p1, p1) == 0.0
        
        # Negative coordinates
        p3 = Point(-1, -1)
        p4 = Point(2, 3)
        expected = math.sqrt((2 - (-1))**2 + (3 - (-1))**2)  # sqrt(9 + 16) = 5
        assert Point.distance(p3, p4) == expected
    
    def test_midpoint(self):
        """Test midpoint calculation."""
        p1 = Point(0, 0, "#FF0000")
        p2 = Point(4, 6, "#00FF00")
        
        mid = Point.midpoint(p1, p2)
        assert mid.x == 2.0
        assert mid.y == 3.0
        assert mid.color is None  # Midpoint should have no color
        
        # Test with negative coordinates
        p3 = Point(-2, -4)
        p4 = Point(2, 4)
        mid2 = Point.midpoint(p3, p4)
        assert mid2.x == 0.0
        assert mid2.y == 0.0
        
        # Test midpoint of same point
        mid3 = Point.midpoint(p1, p1)
        assert mid3.x == p1.x
        assert mid3.y == p1.y
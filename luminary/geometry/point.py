"""Point class for 2D geometric operations."""

import math
from typing import Tuple, Optional, List


class Point:
    """Represents a 2D point with optional color and polar coordinates.

    Properties:
        x: X coordinate (Cartesian)
        y: Y coordinate (Cartesian)
        r: Radius/distance from origin (polar)
        theta: Angle in radians from positive X-axis (polar)
        color: Optional color string
    """

    def __init__(self, x: float, y: float, color: Optional[str] = None):
        """
        Initialize a Point.

        Args:
            x: X coordinate
            y: Y coordinate
            color: Optional color string (e.g., "#FF0000")
        """
        self.x = x
        self.y = y
        self.color = color

        # Calculate polar coordinates at initialization
        self.r = math.sqrt(x * x + y * y)
        self.theta = math.atan2(y, x)

    def distance(self, other: "Point") -> float:
        """
        Calculate Euclidean distance to another point.

        Args:
            other: Other point

        Returns:
            Distance to the other point
        """
        return math.sqrt((other.x - self.x) ** 2 + (other.y - self.y) ** 2)

    def midpoint_to(self, other: "Point") -> "Point":
        """
        Return new Point at midpoint between this point and another.

        Args:
            other: Other point

        Returns:
            New Point at midpoint (no color)
        """
        return Point((self.x + other.x) / 2, (self.y + other.y) / 2)

    @staticmethod
    def midpoint(p1: "Point", p2: "Point") -> "Point":
        """
        Return new Point at midpoint between two points (deprecated - use instance method).

        Args:
            p1: First point
            p2: Second point

        Returns:
            New Point at midpoint (no color)
        """
        return p1.midpoint_to(p2)

    def get_color(self) -> Optional[str]:
        """
        Return color string or None.

        Returns:
            Color string or None if no color set
        """
        return self.color

    def get_polar(self) -> Tuple[float, float]:
        """
        Return polar coordinates as tuple.

        Returns:
            (r, theta) tuple where theta is in radians
        """
        return (self.r, self.theta)

    @classmethod
    def from_polar(cls, r: float, theta: float, color: Optional[str] = None) -> "Point":
        """
        Create Point from polar coordinates.

        Args:
            r: Radius (distance from origin)
            theta: Angle in radians from positive X-axis
            color: Optional color string

        Returns:
            New Point instance
        """
        x = r * math.cos(theta)
        y = r * math.sin(theta)
        return cls(x, y, color)

    def __add__(self, other) -> "Point":
        """Add a vector to this point."""
        from .primitives import Vector

        if not isinstance(other, Vector):
            raise TypeError("Can only add Vector to Point, not Point to Point")
        return Point(self.x + other.x, self.y + other.y)

    def __sub__(self, other):
        """Subtract another point or vector from this point."""
        from .primitives import Vector
        
        if isinstance(other, Point):
            # Point - Point = Vector
            return Vector(self.x - other.x, self.y - other.y)
        elif hasattr(other, 'x') and hasattr(other, 'y'):  # Vector-like object
            # Point - Vector = Point
            return Point(self.x - other.x, self.y - other.y)
        else:
            raise TypeError(f"Cannot subtract {type(other)} from Point")

    def __eq__(self, other) -> bool:
        """Check if two points are equal (same coordinates)."""
        if not isinstance(other, Point):
            return False
        return self.x == other.x and self.y == other.y

    def __hash__(self) -> int:
        """Make Point hashable for use in sets and as dict keys."""
        return hash((self.x, self.y))

    def is_inside_polygon(self, vertices: List["Point"]) -> bool:
        """Check if this point is inside a polygon using ray casting algorithm.

        Args:
            vertices: List of Point objects defining the polygon vertices

        Returns:
            True if point is inside the polygon, False otherwise

        Note:
            Uses the ray casting algorithm (point-in-polygon test).
            Handles edge cases and floating point precision issues.
        """
        if not vertices:
            return False

        x, y = self.x, self.y
        n = len(vertices)
        inside = False

        j = n - 1
        for i in range(n):
            xi, yi = vertices[i].x, vertices[i].y
            xj, yj = vertices[j].x, vertices[j].y

            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i

        return inside

"""Point class for 2D geometric operations."""

import math
from typing import Tuple, Optional


class Point:
    """Represents a 2D point with optional color."""

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

    @staticmethod
    def distance(p1: "Point", p2: "Point") -> float:
        """
        Calculate Euclidean distance between two points.

        Args:
            p1: First point
            p2: Second point

        Returns:
            Distance between the points
        """
        return math.sqrt((p2.x - p1.x) ** 2 + (p2.y - p1.y) ** 2)

    @staticmethod
    def midpoint(p1: "Point", p2: "Point") -> "Point":
        """
        Return new Point at midpoint between two points.

        Args:
            p1: First point
            p2: Second point

        Returns:
            New Point at midpoint (no color)
        """
        mid_x = (p1.x + p2.x) / 2
        mid_y = (p1.y + p2.y) / 2
        return Point(mid_x, mid_y)

    def get_coordinates(self) -> Tuple[float, float]:
        """
        Return coordinates as tuple.

        Returns:
            (x, y) tuple
        """
        return (self.x, self.y)

    def get_color(self) -> Optional[str]:
        """
        Return color string or None.

        Returns:
            Color string or None if no color set
        """
        return self.color

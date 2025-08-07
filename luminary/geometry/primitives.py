"""Minimal geometric primitive classes for 2D operations."""

from typing import List, Optional, Tuple
from .point import Point


class Vector:
    """Represents a 2D vector with direction and magnitude."""

    def __init__(self, x: float, y: float):
        """Initialize a vector with x and y components.

        Args:
            x: X component
            y: Y component
        """
        self.x = x
        self.y = y

    def length(self) -> float:
        """Calculate the length/magnitude of this vector.

        Returns:
            Length of the vector
        """
        import math

        return math.sqrt(self.x * self.x + self.y * self.y)

    def __add__(self, other: "Vector") -> "Vector":
        """Add two vectors."""
        return Vector(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Vector") -> "Vector":
        """Subtract one vector from another."""
        return Vector(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> "Vector":
        """Multiply vector by a scalar."""
        return Vector(self.x * scalar, self.y * scalar)

    def __rmul__(self, scalar: float) -> "Vector":
        """Right multiply vector by a scalar."""
        return self.__mul__(scalar)

    def __truediv__(self, scalar: float) -> "Vector":
        """Divide vector by a scalar."""
        return Vector(self.x / scalar, self.y / scalar)

    def unit_vector(self) -> "Vector":
        """Return a unit vector in the same direction.

        Returns:
            Unit vector with length 1, or zero vector if this vector has zero length
        """
        length = self.length()
        if length == 0:
            return Vector(0, 0)
        return self / length

    def perpendicular_counterclockwise(self) -> "Vector":
        """Return a vector perpendicular to this one, rotated 90 degrees counterclockwise.

        Returns:
            Vector perpendicular to this one
        """
        return Vector(-self.y, self.x)

    def cross_product(self, other: "Vector") -> float:
        """Calculate 2D cross product (z-component of 3D cross product).

        Args:
            other: Other vector

        Returns:
            Cross product value (positive = counterclockwise, negative = clockwise)
        """
        return self.x * other.y - self.y * other.x


class Angle:
    """Represents an angle defined by three points: apex and two arms."""

    def __init__(self, apex: Point, point1: Point, point2: Point):
        """Initialize an angle.

        Args:
            apex: Vertex of the angle
            point1: First point defining one arm of the angle
            point2: Second point defining the other arm of the angle
        """
        self.apex = apex
        self.point1 = point1
        self.point2 = point2

    def bisector(self) -> "Ray":
        """Calculate the angle bisector.

        Returns:
            Ray starting from apex along the angle bisector direction
        """
        # Get vectors from apex to the two points
        vec1 = self.point1 - self.apex
        vec2 = self.point2 - self.apex

        # Normalize the vectors
        unit1 = vec1.unit_vector()
        unit2 = vec2.unit_vector()

        if vec1.length() == 0 or vec2.length() == 0:
            # Degenerate case - return arbitrary direction
            return Ray.from_point_and_direction(self.apex, Vector(1, 0))

        # Angle bisector is the average of unit vectors
        bisector = unit1 + unit2
        bisector_len = bisector.length()

        if bisector_len == 0:
            # Vectors are opposite - return perpendicular
            perp_direction = unit1.perpendicular_counterclockwise()
            return Ray.from_point_and_direction(self.apex, perp_direction)

        # Create ray from apex in the bisector direction
        return Ray.from_point_and_direction(self.apex, bisector)


class LinearElement:
    """Base class for linear geometric elements defined by two points."""

    def __init__(self, p1: Point, p2: Point):
        """Initialize with two defining points.

        Args:
            p1: First point
            p2: Second point
        """
        self.p1 = p1
        self.p2 = p2

    def _line_intersection_t(
        self, other: "LinearElement"
    ) -> Optional[Tuple[float, float]]:
        """Calculate parametric intersection values for two linear elements.

        Args:
            other: Other linear element

        Returns:
            (t1, t2) where intersection = p1 + t1*(p2-p1) = other.p1 + t2*(other.p2-other.p1)
            None if lines are parallel
        """
        # Line 1: p1 + t1 * (p2 - p1)
        # Line 2: other.p1 + t2 * (other.p2 - other.p1)
        vec1 = self.p2 - self.p1  # Direction vector of line 1
        vec2 = other.p2 - other.p1  # Direction vector of line 2

        denom = vec1.cross_product(vec2)
        if abs(denom) < 1e-10:
            return None  # Parallel lines

        vec3 = other.p1 - self.p1  # Vector from line1 start to line2 start
        t1 = vec3.cross_product(vec2) / denom
        t2 = vec3.cross_product(vec1) / denom

        return (t1, t2)


class Segment(LinearElement):
    """Line segment between two points."""

    def length(self) -> float:
        """Calculate the length of this segment.

        Returns:
            Length of the segment
        """
        return self.p1.distance(self.p2)

    def intersection(self, other: "LinearElement", ignore_bounds: bool = False) -> Optional[Point]:
        """Find intersection with another linear element if it exists on this segment.

        Args:
            other: Other linear element (Segment, Ray, or Line)

        Returns:
            Intersection point if it exists on this segment, None otherwise
        """
        t_values = self._line_intersection_t(other)
        if t_values is None:
            return None

        t1, t2 = t_values

        if not ignore_bounds:
            # Check if intersection is on this segment (t1 in [0, 1]) with tolerance
            if not (-1e-10 <= t1 <= 1 + 1e-10):
                return None

            # Check if intersection is valid for the other element
            if isinstance(other, Segment):
                if not (-1e-10 <= t2 <= 1 + 1e-10):
                    return None
            elif isinstance(other, Ray):
                if t2 < -1e-10:
                    return None
            # Line has no restrictions on t2

        # Calculate intersection point
        return Point(
            self.p1.x + t1 * (self.p2.x - self.p1.x),
            self.p1.y + t1 * (self.p2.y - self.p1.y),
        )


class Ray(LinearElement):
    """Ray starting at p1 and passing through p2."""

    @classmethod
    def from_point_and_direction(cls, start: Point, direction: Vector) -> "Ray":
        """Create a ray from a starting point and direction vector.

        Args:
            start: Starting point of the ray
            direction: Direction vector (will be normalized internally)

        Returns:
            Ray starting from start point in the given direction
        """
        # Create a second point along the direction to define the ray
        unit_direction = direction.unit_vector()
        end_point = start + unit_direction
        return cls(start, end_point)

    def direction_vector(self) -> Vector:
        """Get the direction vector of this ray.

        Returns:
            Unit vector pointing in the direction of the ray
        """
        direction = self.p2 - self.p1
        return direction.unit_vector()

    def intersection(self, other: "LinearElement", ignore_bounds: bool = False) -> Optional[Point]:
        """Find intersection with another linear element if it exists on this ray.

        Args:
            other: Other linear element (Segment, Ray, or Line)

        Returns:
            Intersection point if it exists on this ray, None otherwise
        """
        t_values = self._line_intersection_t(other)
        if t_values is None:
            return None

        t1, t2 = t_values

        if not ignore_bounds:
            # Check if intersection is on this ray (t1 >= 0) with tolerance
            if t1 < -1e-10:
                return None

            # Check if intersection is valid for the other element
            if isinstance(other, Segment):
                if not (-1e-10 <= t2 <= 1 + 1e-10):
                    return None
            elif isinstance(other, Ray):
                if t2 < -1e-10:
                    return None
            # Line has no restrictions on t2

        # Calculate intersection point
        return Point(
            self.p1.x + t1 * (self.p2.x - self.p1.x),
            self.p1.y + t1 * (self.p2.y - self.p1.y),
        )


class Line(LinearElement):
    """Infinite line passing through two points."""

    def intersection(self, other: "LinearElement", ignore_bounds: bool = False) -> Optional[Point]:
        """Find intersection with another linear element.

        Args:
            other: Other linear element (Segment, Ray, or Line)

        Returns:
            Intersection point if lines are not parallel, None otherwise
        """
        t_values = self._line_intersection_t(other)
        if t_values is None:
            return None

        t1, t2 = t_values

        if not ignore_bounds:
            # Check if intersection is valid for the other element
            if isinstance(other, Segment):
                if not (-1e-10 <= t2 <= 1 + 1e-10):
                    return None
            elif isinstance(other, Ray):
                if t2 < -1e-10:
                    return None
            # Line-Line intersection always exists if not parallel

        # Calculate intersection point
        return Point(
            self.p1.x + t1 * (self.p2.x - self.p1.x),
            self.p1.y + t1 * (self.p2.y - self.p1.y),
        )


class Polygon:
    """Represents a polygon defined by a sequence of vertices."""

    def __init__(self, vertices: List[Point]):
        """Initialize a polygon with vertices.

        Args:
            vertices: List of points defining the polygon boundary
        """
        self.vertices = vertices

    def is_inside(self, point: Point) -> bool:
        """Check if a point is inside the polygon.

        Args:
            point: Point to test

        Returns:
            True if point is inside the polygon
        """
        return point.is_inside_polygon(self.vertices)


class OrientedSegment(Segment):
    """Segment with semantic labels for endpoints."""

    def __init__(self, labeled_points: dict[str, Point]):
        """Initialize an oriented segment with labeled endpoints.

        Args:
            labeled_points: Dictionary mapping labels to points (must contain exactly 2 entries)
                          e.g., {"port": Point(0, 0), "starboard": Point(5, 0)}

        Raises:
            ValueError: If dictionary doesn't contain exactly 2 entries
        """
        if len(labeled_points) != 2:
            raise ValueError(
                f"OrientedSegment requires exactly 2 labeled points, got {len(labeled_points)}"
            )

        # Convert dict to ordered list for parent class
        labels = list(labeled_points.keys())
        points = list(labeled_points.values())

        super().__init__(points[0], points[1])
        self.p1_label = labels[0]
        self.p2_label = labels[1]
        self._labeled_points = labeled_points

    def get_point_by_label(self, label: str) -> Point:
        """Get point by its semantic label.

        Args:
            label: The label to look up

        Returns:
            Point with the given label

        Raises:
            ValueError: If label doesn't match either endpoint
        """
        if label not in self._labeled_points:
            available_labels = list(self._labeled_points.keys())
            raise ValueError(
                f"Label '{label}' not found. Available labels: {available_labels}"
            )
        return self._labeled_points[label]

    def assert_labels(self, expected_labels: set[str]) -> None:
        """Assert that the segment has the expected labels.

        Args:
            expected_labels: Set of expected labels (must contain exactly 2 labels)

        Raises:
            AssertionError: If labels don't match expected set
        """
        actual_labels = set(self._labeled_points.keys())
        assert (
            actual_labels == expected_labels
        ), f"Expected labels {expected_labels}, got {actual_labels}"

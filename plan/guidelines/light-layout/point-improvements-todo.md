# Point Class Improvements TODO

## Overview
Enhance the Point class to provide better abstraction and move geometry operations to the appropriate level. This improves code organization and reduces duplicate coordinate manipulation throughout the geometry module.

## Tasks

### 1. Add Polar Coordinates Support
- **File**: `luminary/geometry/point.py:7`
- **Task**: Calculate polar coordinates (r, θ) at Point initialization time
- **Requirements**: 
  - Add `r` and `theta` properties to Point class
  - Calculate during `__init__`
  - Write comprehensive pytest tests for polar coordinate accuracy
  - Handle edge cases (origin, negative coordinates)

### 2. Improve Point Arithmetic
- **File**: `luminary/geometry/point.py:50` 
- **Task**: Use point addition instead of coordinate math in midpoint calculation
- **Requirements**:
  - Refactor `Point.midpoint()` to use `+` and `/` operators on Point objects
  - Ensure existing Point arithmetic operators work correctly
  - Maintain backward compatibility

### 3. Standardize Coordinate Access Pattern
- **File**: `luminary/geometry/point.py:55`
- **Task**: Decide on consistent Point coordinate access (.x/.y vs methods)
- **Requirements**:
  - Audit all Point coordinate access across codebase
  - Choose between direct property access vs getter methods
  - Document the decision and enforce consistency
  - Update any inconsistent usage

### 4. Move Point-in-Polygon to Point Class
- **File**: `luminary/geometry/beam.py:161`
- **Task**: Move `_point_in_geometry()` to Point class as a generic method
- **Requirements**:
  - Create `Point.is_inside_polygon(vertices: List[Point]) -> bool`
  - Use ray casting algorithm (maintain existing logic)
  - Remove beam-specific implementation
  - Update beam class to use new Point method

### 5. Move Line Intersection to Point Class
- **File**: `luminary/geometry/facet.py:180`
- **Task**: Move `_line_intersection()` to Point class (it's generic geometry)
- **Requirements**:
  - Create `Point.line_intersection(line1: Tuple[Point, Point], line2: Tuple[Point, Point]) -> Point`
  - Handle parallel lines and edge cases
  - Remove facet-specific implementation
  - Update facet and beam classes to use new Point method

### 6. Move Geometry Math to Point Class
- **File**: `luminary/geometry/facet.py:263`
- **Task**: Replace manual coordinate manipulation with Point class methods
- **Requirements**:
  - Identify geometric operations that should be Point methods
  - Create methods like `Point.distance_to()`, `Point.vector_to()`, `Point.normalize()`
  - Refactor facet beam generation to use Point methods
  - Reduce raw coordinate access in geometry calculations

## Implementation Notes

- Maintain backward compatibility during transitions
- Add comprehensive tests for all new Point methods
- Consider performance implications of new calculations
- Ensure all geometry operations have consistent error handling
- Document new Point class capabilities in docstrings

## Testing Requirements

- Unit tests for polar coordinate calculations
- Tests for geometric method accuracy
- Performance tests for critical path operations
- Integration tests to ensure no regressions in existing functionality
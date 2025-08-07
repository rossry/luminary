# Naming and Magic Number Cleanup TODO

## Overview
Improve code readability and maintainability by eliminating magic indices, clarifying variable names, and making the codebase more self-documenting. This focuses on the facet and triangle classes where coordinate access patterns need clarification.

## Tasks

### 1. Facet Parameter Renaming
Clarify the semantic meaning of facet constructor parameters.

**Files**: `luminary/geometry/facet.py:27-30`

- **Task 1**: Rename `vertex` → `vertex_primary`
  - Update constructor parameter name
  - Update all references within facet class
  - Update docstrings to clarify this is the triangle vertex

- **Task 2**: Rename `midpoint1` → `vertex_port` 
  - **CRITICAL**: First verify port/starboard logic by inspecting actual usage
  - Trace through facet creation in triangle.py to ensure correct mapping
  - Update constructor parameter name and references
  - Add clear documentation about port/starboard convention

- **Task 3**: Rename `incenter` → `vertex_incenter`
  - Update constructor parameter name
  - Update all references within facet class
  - Maintain clarity that this is the triangle's incenter point

- **Task 4**: Rename `midpoint2` → `vertex_starboard`
  - Update constructor parameter name and references
  - Ensure consistent with port/starboard verification from Task 2

### 2. Eliminate Magic Index Access
Replace array index access with named variables for better readability.

**Files**: `luminary/geometry/facet.py:97, 102, 107, 112`

- **Task 1**: Fix `get_primary_vertex()` method
  - Replace `return self.vertices[0]` with named variable access
  - Use `self.vertex_primary` after parameter renaming

- **Task 2**: Fix `get_incenter()` method  
  - Replace `return self.vertices[2]` with named variable access
  - Use `self.vertex_incenter` after parameter renaming

- **Task 3**: Fix `get_lateral_vertices()` method
  - Replace `return (self.vertices[1], self.vertices[3])` with named variables
  - Use `(self.vertex_port, self.vertex_starboard)` after parameter renaming

- **Task 4**: Fix `_get_axis_of_symmetry()` method
  - Replace `return (self.vertices[0], self.vertices[2])` with named variables
  - Use `(self.vertex_primary, self.vertex_incenter)` after parameter renaming

### 3. Triangle Midpoint Logic Cleanup
Simplify triangle facet creation logic using modular arithmetic.

**File**: `luminary/geometry/triangle.py:208`

- **Task**: Replace lookup-style midpoint assignment with calculated indices
- **Requirements**:
  - Use modular arithmetic: `midpoint1_idx = vertex_idx`, `midpoint2_idx = (vertex_idx + 2) % 3`
  - Add clear port/starboard naming conventions
  - Document the mathematical relationship between vertex and midpoint indices
  - Eliminate the manual if/elif chains for midpoint selection

## Implementation Notes

### Port/Starboard Convention
- **CRITICAL**: Verify current port/starboard assignments are correct before renaming
- Document the geometric convention clearly (e.g., "port = left when looking from vertex toward incenter")
- Ensure consistency across all geometry classes

### Backward Compatibility
- Update all callers when changing constructor parameters
- Maintain the `vertices` tuple for any external code that might depend on it
- Consider deprecation warnings if this is a public API

### Testing Requirements
- Verify that all geometric calculations remain correct after renaming
- Add tests that explicitly verify port/starboard assignments
- Test that magic index elimination doesn't break facet geometry
- Ensure triangle facet creation still produces correct results

## Dependencies
- Should be done after point-improvements to take advantage of improved Point class
- May inform functional-python improvements by clarifying data structures
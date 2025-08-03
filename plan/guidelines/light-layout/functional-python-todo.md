# Functional Python Improvements TODO

## Overview
Modernize the codebase by adopting contemporary Python features and optimizing algorithmic structures. This focuses on using match/case statements and improving loop organization for better performance and readability.

## Tasks

### 1. Replace if/elif Chains with Match/Case
Use Python 3.10+ pattern matching for cleaner, more maintainable code.

**File**: `luminary/geometry/facet.py:130`

- **Task**: Convert `_get_edge_points()` method to use match/case
- **Current**: Long if/elif chain for `EdgeType` enumeration
- **Target**: Clean match/case statement:
  ```python
  match edge_type:
      case EdgeType.MAJOR_STARBOARD:
          return (self.vertex_primary, self.vertex_port)
      case EdgeType.MINOR_STARBOARD:
          return (self.vertex_port, self.vertex_incenter)
      # etc.
  ```
- **Requirements**:
  - Verify Python 3.10+ compatibility requirement
  - Maintain exact same logic and return values
  - Update any similar patterns found elsewhere in codebase

### 2. Optimize Beam Generation Loop Structure
Improve algorithm organization and computational efficiency in beam generation.

**File**: `luminary/geometry/facet.py:258`

- **Task**: Restructure as nested loops with edge-first iteration
- **Current**: Single loop with enumeration over beam counts
- **Target**: Nested structure:
  ```python
  for edge_idx, beam_count in enumerate(beam_counts):
      # Edge-specific setup here
      for beam_idx in range(beam_count):
          # Individual beam creation here
  ```
- **Requirements**:
  - Maintain sequential parity tracking across all beams
  - Preserve exact beam ordering and geometry
  - Consider opportunities for edge-level optimizations

### 3. Pre-compute Edge-Constant Values
Optimize performance by calculating edge-invariant values once per edge.

**File**: `luminary/geometry/facet.py:235`

- **Task**: Pre-compute bisector lines that are constant for all beams on an edge
- **Current**: Bisector lines calculated in setup, but could be optimized further
- **Requirements**:
  - Identify values that don't change within an edge's beam loop
  - Calculate once per edge, reuse for all beams on that edge
  - Measure performance impact on high beam count configurations
  - Maintain mathematical correctness

## Implementation Strategy

### Performance Considerations
- Profile beam generation performance before and after changes
- Focus on configurations with high beam counts (e.g., [19, 11, 11, 19])
- Consider memory vs computation tradeoffs for pre-computed values

### Code Organization
- Group related optimizations together in commits
- Ensure each change can be independently verified
- Maintain clear separation between algorithmic and structural improvements

### Compatibility Requirements
- Verify Python version requirements for match/case
- Update project dependencies if needed
- Provide fallback implementations if supporting older Python versions

## Testing Requirements

### Performance Testing
- Benchmark beam generation with various beam count configurations
- Measure memory usage for pre-computed optimizations
- Verify no regressions in generation speed

### Correctness Testing
- Ensure match/case produces identical results to if/elif chains
- Verify nested loop restructuring doesn't change beam ordering
- Test edge cases and boundary conditions

### Integration Testing
- Generate comparison SVGs before and after changes
- Verify visual output remains identical
- Test with various triangle and facet configurations

## Dependencies
- Should be done after naming-cleanup to benefit from clearer variable names
- May benefit from point-improvements if geometric calculations are optimized
- Consider coordination with any broader Python version upgrades

## Future Opportunities
- Look for other areas where match/case could improve readability
- Consider functional programming patterns (map, filter, reduce) where appropriate
- Evaluate opportunities for list comprehensions vs explicit loops
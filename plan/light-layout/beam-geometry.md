# Beam Geometry Implementation Plan

## Responsibility Split

### Facet Responsibilities
- **Edge Division**: Divide each facet edge into N equal segments for beam baselines
- **Extent Calculation**: For each beam, provide list of extent segments that limit forward extension
  - Each extent segment has start point on beam's port border, end point on beam's starboard border
  - Currently: Single extent from axis of symmetry (primary vertex → incenter) sliced between port/starboard borders
- **Reference Frame Setup**: Calculate anchor points and beam width vectors

### Beam Responsibilities  
- **Forward Edge Determination**: Process extent segments to find actual forward boundary
  - Determine which extent points are closest (most relevant)
  - Detect if extents intersect to create 5-sided polygon
  - Handle extent processing logic
- **Polygon Construction**: Create final beam polygon from baseline + forward edge
- **Sample Generation**: Place sample points within beam using reference frame
- **Color Calculation**: Apply parity-based brightness adjustments

## Technical Terms

### Core Concepts
- **Extent Segment**: Line segment that may limit how far forward a beam extends
  - Start point: On beam's port border
  - End point: On beam's starboard border
  - Represents potential forward boundary constraint

- **Beam Baseline**: Segment on facet edge between beam's port and starboard boundaries
- **Forward Edge**: Actual front boundary of beam, determined from extent processing
- **Anchor Point**: Reference point on baseline, centered within beam
- **Beam Width Vector**: Vector representing one beam width (baseline length)

### Beam Structure
- **4-Sided Beam**: Baseline + two sides + single forward edge
- **5-Sided Beam**: When extent intersections create additional forward vertex
- **Extent List**: List of extent segments provided by facet (currently always length 1)

## Current Implementation: Placeholder Beams

### Facet._generate_beams()
1. **Edge Setup**: Calculate edge vector, beam divisions, anchor points
2. **Single Extent Generation**: For each beam:
   - Calculate where axis of symmetry intersects beam's port border
   - Calculate where axis of symmetry intersects beam's starboard border
   - Create single extent segment between these intersection points
3. **Beam Creation**: Pass extent list (length 1) to Beam constructor

### Beam.__init__()
1. **Extent Validation**: Crash with `NotImplementedError` if extent list length ≠ 1
2. **Forward Edge Assignment**: Use first (and only) extent segment as forward edge
3. **Polygon Assembly**: Create 4-sided polygon: baseline → port side → forward edge → starboard side
4. **Reference Frame**: Store anchor point and beam width vector for sample generation

## Geometric Algorithm

### Axis Slicing (Facet)
```
For beam with baseline from port_point to starboard_point:
1. Extend perpendicular rays from port_point and starboard_point into facet interior
2. Find where these rays intersect the axis of symmetry
3. Create extent segment between these intersection points
```

### Forward Edge Processing (Beam)
```
Given single extent segment (port_extent, starboard_extent):
1. Verify extent list has exactly one element
2. Use extent segment directly as forward edge
3. Create polygon: [port_baseline, starboard_baseline, starboard_extent, port_extent]
```

## Testing Strategy

### Geometric Validation
- **Axis Intersection**: Verify axis slicing produces valid extent segments
- **Polygon Validity**: Check beam polygons have correct winding and no self-intersections
- **Anchor Positioning**: Verify anchors are centered on baselines
- **Sample Containment**: Ensure generated samples fall within beam polygons

### Edge Cases
- **Degenerate Geometry**: Handle zero-length edges or parallel lines
- **Extent Validation**: Test NotImplementedError for multi-extent cases
- **Boundary Beams**: Verify correct behavior at facet corners

### Integration Tests
- **Known Geometries**: Test with predictable facet shapes
- **Multiple Beam Counts**: Verify different beam count configurations
- **Visual Output**: SVG rendering for manual verification

## Future Extensions (Not Implemented Now)

### Multi-Extent Processing
- When extent list length > 1, Beam will need to:
  - Find closest extent points from baseline
  - Detect extent segment intersections
  - Create 5-sided polygons when intersections occur within beam width
  - This complexity is deferred until needed

### Performance Optimizations
- **Per-Edge Constants**: Share edge vectors and unit calculations across beams
- **Stride Arithmetic**: Use arithmetic progression for regular beam spacing
- **Intersection Caching**: Cache axis calculations reused across beams

## Implementation Steps

1. **Facet.\_generate_beams()**: Implement axis slicing and single extent generation
2. **Beam.__init__()**: Implement extent validation and 4-sided polygon creation
3. **Beam.generate_samples()**: Use reference frame for sample placement
4. **Integration**: Update Facet.__init__ to generate beams at creation time
5. **Testing**: Validate geometry with known test cases
6. **Visual Verification**: Generate SVG output for manual inspection

## Success Criteria

- [ ] Each beam has exactly one extent segment from axis slicing
- [ ] Beam polygons are valid 4-sided shapes with correct winding
- [ ] Sample points fall within beam boundaries
- [ ] Color parity produces alternating brightness
- [ ] NotImplementedError raised for multi-extent cases
- [ ] Performance acceptable for typical facet counts with default beam settings
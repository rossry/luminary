# Light Layout Feature: Facets and Beams

## Overview

The Light Layout feature introduces advanced geometric subdivision of the Luminary pentagon patterns to simulate lighting effects. This feature renames "kites" to "facets" and subdivides each facet into "beams" - regions that would be lit by a single light source.

## Terminology Changes

### Current → New
- **Kite** → **Facet**: The 4-sided geometric shapes that extend from triangle edges
- **New: Beam**: Subdivision regions within each facet, representing areas lit by single light sources

## Geometric Specifications

### Facet Structure
Each facet has:
- **4 vertices**: Primary vertex (shared with triangle), incenter, 2 lateral vertices  
- **4 edges** in canonical order:
  - `[0]` Major Starboard (right major edge)
  - `[1]` Minor Starboard (right minor edge) 
  - `[2]` Minor Port (left minor edge)
  - `[3]` Major Port (left major edge)
- **Axis of symmetry**: Line from primary vertex through triangle's incenter
- **2 major edges**: Longer edges adjacent to primary vertex
- **2 minor edges**: Shorter edges adjacent to incenter

### Beam Subdivision Algorithm

Each edge of a facet is subdivided into N beams (where N is configurable per edge):

1. **Base**: Each beam has equal width (1/N) along its parent edge
2. **Sides**: Left and right boundaries are perpendicular to the base edge
3. **Top boundary**: Determined by the closer of:
   - The facet's axis of symmetry (primary vertex → incenter line)
   - The angle bisector from the edge's "near lateral vertex"
4. **5-sided beams**: When both axis and angle bisector intersect within the beam's width, create a 5-sided polygon with both intersection points

### Beam Identification
- **Within edge**: Zero-indexed (0, 1, 2, ..., N-1)
- **Color calculation**: Parent facet color ±20% based on `(beam_index + edge_index) % 2`
  - Even parity: 20% lighter (mix towards #ffffff)
  - Odd parity: 20% darker (mix towards #000000)

## Configuration System

### Main Configuration Schema
```json
{
  "geometry": {
    "default_beam_counts": [7, 4, 4, 7], // [major_starboard, minor_starboard, minor_port, major_port]
    "triangles": [...],
    "points": [...]
  }
}
```

### Layout Override Files
Companion files named `config_name.layout.json`:
```json
{
  "facet_overrides": {
    "02A": [5, 3, 3, 5],  // Override beam counts for specific facet
    "1BC": [8, 6, 6, 8],  // Facet ID format: [series][triangle_index][facet_letter]
  }
}
```

### Facet ID Format
- **Pattern**: `[series][triangle_index][facet_letter]`
- **Examples**: "02A", "1BC", "43D" 
- **Synonyms**: DEF letters synonymized to ABC for convenience

## Rendering Specifications

### Regular SVG Output
- Unchanged behavior: renders facets as filled polygons
- File naming: `config_name.svg`

### Extended SVG Output  
- **Activation**: `--extended` CLI flag
- **Content**: Individual beam polygons (fills only, no stroke edges)
- **File naming**: `config_name.extended.svg`
- **Index support**: Side-by-side display with regular SVG

### Color Inheritance
Beams inherit parent facet colors with brightness modulation based on position parity.

## Future Considerations

### Triangle Species (Planned)
```json
// Future enhancement - not implemented initially
{
  "triangle_species": {
    "equilateral": {"default_beam_counts": [7, 4, 4, 7]},
    "isosceles": {"default_beam_counts": [9, 6, 6, 9]}
  }
}
```

## Implementation Hierarchy

```
Net
├── Triangles
│   ├── Facets (formerly Kites)  
│   │   ├── Beams (new subdivision)
│   │   │   ├── Geometric boundaries
│   │   │   ├── Color calculation  
│   │   │   └── SVG rendering
```

All beam generation occurs at load time, creating the complete geometric hierarchy before any rendering operations.

## References

- [Shared Claude Conversation](https://claude.ai/share/03929876-b16b-49b8-b01e-6a713445015b): Triangle incenters, kites, and beam geometry collaboration
- Related to lightmapping and computational graphics techniques for realistic lighting simulation
# Development To-Do List: SVG Pentagon Pattern Generator

## Chapter 1: Foundation Infrastructure

### Feature 1.1: Point Class Implementation
**PR Title**: `feat: implement Point class with basic operations`
- Implement `Point.__init__(x, y, color=None)`
- Implement `Point.get_coordinates()` and `Point.get_color()`
- Implement `Point.distance()` static method
- Implement `Point.midpoint()` static method

**Test**: Create a simple script that creates Points and prints distances/midpoints to verify calculations.

### Feature 1.2: Basic SVG Utilities
**PR Title**: `feat: add basic SVG generation utilities`
- Implement static SVG helper functions:
  - `create_polygon_svg()`
  - `create_circle_svg()`  
  - `create_line_svg()`
  - `create_text_svg()`
  - `create_rect_svg()`
  - `create_svg_header()`

**Test**: Generate a simple SVG with one polygon, one circle, one line, and one text element to verify SVG syntax is correct.

### Feature 1.3: Orientation Enum
**PR Title**: `feat: implement Orientation enum for triangle classification`
- Create `Orientation` enum with `APEXWARD` and `NADIRWARD` values

**Test**: Simple instantiation test, no visual component needed.

## Chapter 2: Geometric Calculations

### Feature 2.1: Incenter Calculation
**PR Title**: `feat: implement triangle incenter calculation`
- Implement `Triangle.calculate_incenter()` static method
- Handle edge cases (degenerate triangles, very small triangles)

**Test**: Create 3-5 test triangles with known incenters, generate SVG showing triangle + incenter dot to verify positions are correct.

### Feature 2.2: Orientation Detection
**PR Title**: `feat: implement triangle orientation detection`
- Implement `Triangle.determine_orientation()` static method
- Test against center point to classify as APEXWARD/NADIRWARD

**Test**: Create triangles pointing toward/away from a center point, generate SVG with different colors for each orientation to verify classification.

### Feature 2.3: Label Generation Logic
**PR Title**: `feat: implement kite label generation rules`
- Implement `Triangle.get_kite_labels()` static method
- Encode all the A-C vs D-F rules based on triangle ID and orientation

**Test**: Create a reference table of triangle IDs → expected labels, verify function output matches expected results.

## Chapter 3: Triangle Implementation

### Feature 3.1: Triangle Class Structure
**PR Title**: `feat: implement Triangle class with basic constructor`
- Implement `Triangle.__init__()`
- Calculate and store incenter, edge midpoints, orientation
- Store triangle ID and vertex points
- Do NOT create kites yet

**Test**: Create 2-3 triangles, generate SVG showing triangles with incenter dots and altitude lines to verify geometry is correct.

### Feature 3.2: Triangle SVG Generation
**PR Title**: `feat: implement Triangle.get_svg() for basic elements`
- Implement triangle fill generation (40% black)
- Implement incenter dot generation (black circle, radius 1.5)
- Implement altitude line generation (incenter to edge midpoints)
- Return elements in proper back-to-front order

**Test**: Generate SVG with 3-5 triangles showing fills, incenters, and altitude lines. Verify layering and styling.

## Chapter 4: Kite System

### Feature 4.1: Kite Class Implementation
**PR Title**: `feat: implement Kite class with polygon generation`
- Implement `Kite.__init__()` with vertex ordering: vertex→midpoint→incenter→midpoint
- Implement `Kite.calculate_centroid()` static method
- Implement `Kite.get_svg()` for polygon only (no labels yet)

**Test**: Create one triangle manually, create its 3 kites manually, generate SVG showing triangle + 3 colored kite overlays to verify geometry and colors.

### Feature 4.2: Kite Label Generation
**PR Title**: `feat: add kite text label generation`
- Add label text generation to `Kite.get_svg()`
- Position labels at centroids
- Apply proper styling (font-size 10, black, 70% opacity)

**Test**: Same test as 4.1 but now with labels visible. Verify labels are positioned correctly and have right text.

### Feature 4.3: Triangle-Kite Integration
**PR Title**: `feat: integrate kite creation into Triangle class`
- Modify `Triangle.__init__()` to create 3 Kite objects
- Update `Triangle.get_svg()` to include kite elements
- Ensure proper layering: triangle fill → kite polygons → incenter/altitudes → kite labels

**Test**: Create 2-3 triangles with full kite subdivisions, generate SVG to verify complete triangle rendering with proper layering.

## Chapter 5: JSON and Net Integration

### Feature 5.1: JSON Parser
**PR Title**: `feat: implement JSON configuration parser`
- Create JSON parsing logic for points, triangle_series, config, geometric_lines
- Implement triangle ID calculation from series position
- Handle Point creation from JSON data

**Test**: Parse the test specification JSON, print parsed data structures to verify correct parsing.

### Feature 5.2: Net Class Basic Structure
**PR Title**: `feat: implement Net class with triangle creation`
- Implement `Net.__init__()` to parse JSON and create Triangle objects
- Implement triangle ID calculation logic (series_index * 10 + position + offset)
- Do NOT implement full SVG generation yet

**Test**: Load test JSON, create Net object, verify all 33 triangles are created with correct IDs.

### Feature 5.3: Geometric Lines Rendering
**PR Title**: `feat: implement geometric line structure rendering`
- Add geometric line rendering to Net class
- Implement background rectangle generation

**Test**: Generate SVG with just background + geometric lines to verify structural framework matches reference.

### Feature 5.4: Vertex Circles Rendering
**PR Title**: `feat: implement vertex circle rendering`
- Add vertex circle generation (colored, no fill, stroke-width 4, radius 8)

**Test**: Generate SVG with background + lines + vertex circles to verify colors and positioning.

## Chapter 6: Final Assembly

### Feature 6.1: Complete SVG Assembly
**PR Title**: `feat: implement complete SVG generation in Net.generate_svg()`
- Assemble all components in proper order
- Ensure proper layering from back to front
- Add SVG header and footer

**Test**: Generate complete SVG from test specification, compare visually with reference SVG. All elements should be present and properly layered.

### Feature 6.2: File Output
**PR Title**: `feat: add file output functionality`
- Implement `Net.save_to_file()`
- Add main script entry point to load JSON and generate SVG file

**Test**: Run complete pipeline: load test JSON → generate SVG → save to file → open in browser to verify final output.

### Feature 6.3: Final Validation and Cleanup
**PR Title**: `feat: final validation and code cleanup`
- Verify output matches reference SVG exactly
- Add docstrings and type hints
- Clean up any remaining issues
- Optimize performance if needed

**Test**: Side-by-side visual comparison of generated SVG vs reference SVG. Every element should match exactly in position, color, and styling.

## Testing Strategy Notes

### Visual Inspection Guidelines
- At each stage, generate test SVGs and open in a web browser
- Use different background colors temporarily to verify layering
- Test with simplified data (fewer triangles) before using full specification
- Compare triangle fills, kite colors, label positions, and line endpoints
- Verify SVG validates as proper XML

### Incremental Complexity
- Start with 1 triangle, then 3 triangles, then full set
- Test edge cases: triangles near boundaries, very small triangles
- Verify color inheritance from vertices to kites works correctly
- Test both APEXWARD and NADIRWARD triangles in isolation

### Debug Outputs
- Add temporary debug circles/lines to visualize incenters, midpoints
- Use temporary color coding to verify orientation detection
- Print intermediate calculations for manual verification
- Generate simplified SVGs with just one component type at a time
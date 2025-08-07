# SVG Pentagon Pattern Generator - Implementation Specification

## Overview
Create a Python script that generates an SVG representation of a pentagon-based geometric pattern. The system consists of triangles grouped into series, each subdivided into 3 quadrilaterals (kites), with specific coloring and labeling schemes. The output on the provided test specification must be visually identical to a reference static SVG.

## Input Specification
The program reads a JSON file with this structure:
```json
{
  "points": [
    {"x": 100, "y": 20, "color": "#00CED1"},
    {"x": 176.08, "y": 75.28, "color": "#228B22"},
    ...
  ],
  "triangle_series": [
    [{"vertices": [0, 1, 2]}, {"vertices": [1, 3, 4]}, ...],
    [{"vertices": [5, 6, 7]}, {"vertices": [8, 9, 10]}, ...],
    ...
  ],
  "config": {
    "center_point": {"x": 100, "y": 100},
    "width": "100%", 
    "height": "400",
    "viewBox": "-450 -100 1100 370"
  },
  "geometric_lines": [
    [0, 1], [1, 2], [2, 3], ...
  ]
}
```

Triangle IDs are computed as: `(series_index * 10) + triangle_index_in_series + series_offset` where series_offset maps series 0→10, 1→20, 2→30, etc.

## Class Specifications

### Point Class
```python
class Point:
    def __init__(self, x: float, y: float, color: str = None)
    
    @staticmethod
    def distance(p1: Point, p2: Point) -> float
        # Calculate Euclidean distance between two points
    
    @staticmethod  
    def midpoint(p1: Point, p2: Point) -> Point
        # Return new Point at midpoint, no color
    
    def get_coordinates(self) -> tuple[float, float]
        # Return (x, y) tuple
    
    def get_color(self) -> str
        # Return color string or None
```

### Orientation Enum
```python
from enum import Enum

class Orientation(Enum):
    APEXWARD = "apexward"    # Pointing toward center
    NADIRWARD = "nadirward"  # Pointing away from center
```

### Triangle Class
```python
class Triangle:
    def __init__(self, p1: Point, p2: Point, p3: Point, triangle_id: int, center_point: Point)
        # Store vertices, calculate incenter, edge midpoints, orientation
        # Create 3 Kite objects with proper labeling
    
    @staticmethod
    def calculate_incenter(p1: Point, p2: Point, p3: Point) -> Point
        # Calculate incenter using standard formula:
        # I = (a*A + b*B + c*C) / (a + b + c)
        # where a,b,c are opposite side lengths
    
    @staticmethod
    def determine_orientation(triangle_vertices: list[Point], center: Point) -> Orientation
        # Return Orientation.APEXWARD or Orientation.NADIRWARD 
        # If centroid is closer to center than any vertex, return APEXWARD
    
    @staticmethod
    def get_kite_labels(triangle_id: int, orientation: Orientation) -> list[str]
        # Return labels based on rules:
        # NADIRWARD triangles (10s except 10, 30/31/34/35, X0/X1 of 40+): ["D", "E", "F"]
        # APEXWARD triangles (20s, 32/33, X2/X3 of 40+): ["A", "B", "C"]
        # Labels assigned counterclockwise starting from appropriate vertex
    
    @staticmethod
    def create_polygon_svg(points: list[Point], fill: str, opacity: float, stroke: str = "none") -> str
        # Generate SVG polygon element
    
    @staticmethod  
    def create_circle_svg(center: Point, radius: float, fill: str, stroke: str = "none", stroke_width: float = 0) -> str
        # Generate SVG circle element
    
    @staticmethod
    def create_line_svg(p1: Point, p2: Point, stroke_color: str, stroke_width: float) -> str
        # Generate SVG line element
    
    def get_svg(self) -> list[str]
        # Return SVG elements in back-to-front order:
        # 1. Triangle fill (40% black)
        # 2. All kite polygons 
        # 3. Incenter dot (black circle, radius 1.5)
        # 4. Altitude lines (black, width 1, incenter to edge midpoints)
        # 5. All kite labels
    
    def get_vertices(self) -> list[Point]
    def get_kites(self) -> list[Kite]
```

### Kite Class
```python
class Kite:
    def __init__(self, vertex: Point, midpoint1: Point, incenter: Point, midpoint2: Point, color: str, label: str)
        # Store vertices in order: vertex → midpoint1 → incenter → midpoint2
        # Calculate centroid for label positioning
    
    @staticmethod
    def calculate_centroid(vertices: list[Point]) -> Point
        # Return average of vertex coordinates
    
    @staticmethod
    def create_polygon_svg(points: list[Point], fill: str, opacity: float) -> str
        # Generate SVG polygon with specified fill and opacity
    
    @staticmethod
    def create_text_svg(text: str, position: Point, font_size: int, color: str, opacity: float) -> str
        # Generate SVG text element, centered at position
    
    def get_svg(self) -> list[str]
        # Return SVG elements in order:
        # 1. Colored polygon (60% opacity)
        # 2. Text label (font-size 10, black, 70% opacity, centered at centroid)
    
    def get_centroid(self) -> Point
    def get_vertices(self) -> list[Point]
```

### Net Class
```python
class Net:
    def __init__(self, json_file_path: str)
        # Parse JSON, create Point objects, create Triangle objects from series
        # Store geometric line definitions
    
    @staticmethod
    def create_svg_header(viewbox: str, width: str, height: str) -> str
        # Generate opening SVG tag with namespace
    
    @staticmethod
    def create_rect_svg(x: float, y: float, width: float, height: float, fill: str) -> str
        # Generate background rectangle
    
    @staticmethod
    def create_line_svg(p1: Point, p2: Point, stroke_color: str, stroke_width: float) -> str
        # Generate structural line elements
    
    @staticmethod  
    def create_circle_svg(center: Point, radius: float, fill: str, stroke: str, stroke_width: float) -> str
        # Generate vertex circle elements
    
    def generate_svg(self) -> str
        # Assemble complete SVG in order:
        # 1. SVG header
        # 2. White background rectangle
        # 3. Black geometric lines (stroke-width 2)
        # 4. All triangle SVG elements (preserves internal ordering)
        # 5. Colored vertex circles (stroke-width 4, radius 8, no fill)
        # 6. Closing SVG tag
    
    def save_to_file(self, filename: str) -> None
        # Write SVG string to file
```

## Critical Implementation Details

### Kite Construction Logic
For each triangle, create 3 kites with vertices in order: **vertex → midpoint → incenter → midpoint**
1. **First kite**: vertex1 → midpoint(v1,v2) → incenter → midpoint(v1,v3)
2. **Second kite**: vertex2 → midpoint(v2,v3) → incenter → midpoint(v1,v2)  
3. **Third kite**: vertex3 → midpoint(v1,v3) → incenter → midpoint(v2,v3)

Each kite inherits the color from its corresponding vertex.

### Label Assignment Rules
- **NADIRWARD triangles** get D-F labels (D points away from center)
- **APEXWARD triangles** get A-C labels (A points toward center)
- Labels proceed counterclockwise from the designated starting vertex
- **NADIRWARD triangles**: 10 series (except 10), 30/31/34/35, 40/41/50/51/60/61
- **APEXWARD triangles**: 20 series, 32/33, 42/43/52/53/62/63

### SVG Layer Ordering (back to front)
1. White background
2. Black geometric lines
3. Triangle fills (40% black)
4. Kite polygons (60% opacity, colored)
5. Incenter dots (black circles)
6. Altitude lines (black lines)
7. Vertex circles (colored, no fill)
8. All text labels

### Geometric Calculations
- **Incenter formula**: `I = (a*A + b*B + c*C) / (a+b+c)` where a,b,c are side lengths opposite vertices A,B,C
- **Edge midpoints**: Simple average of endpoint coordinates
- **Orientation**: Compare triangle centroid distance to center vs vertex distances

### SVG Formatting Requirements
- Use `fill-opacity` for transparency, not alpha channels
- Text elements: `text-anchor="middle"`, Arial font
- Circle elements for vertex: `fill="none"` 
- Line elements: `stroke-width` as specified
- Polygon points: space-separated coordinate pairs

## Test Specification JSON

```json
{
  "points": [
    {"x": 100, "y": -80.7, "color": "#00CED1"},
    {"x": 100, "y": 20, "color": "#5B0082"},
    {"x": 14.1, "y": -18.2, "color": "#D2B48C"},
    {"x": 185.9, "y": -18.2, "color": "#800000"},
    {"x": 260.603, "y": 73.260, "color": "#FFB6C1"},
    {"x": -60.603, "y": 73.260, "color": "#FFB6C1"},
    {"x": 176.08, "y": 75.28, "color": "#228B22"},
    {"x": 23.92, "y": 75.28, "color": "#228B22"},
    {"x": 52.98, "y": 164.72, "color": "#4169E1"},
    {"x": 147.02, "y": 164.72, "color": "#FFD700"},
    {"x": 100, "y": 246.4, "color": "#FF8C00"},
    {"x": 194.247, "y": 246.2, "color": "#CCCCFF"},
    {"x": 5.753, "y": 246.2, "color": "#CCCCFF"},
    {"x": 241.197, "y": 164.72, "color": "#DC143C"},
    {"x": -41.197, "y": 164.72, "color": "#DC143C"},
    {"x": 288.286, "y": 246.2, "color": "#CCFF00"},
    {"x": -88.286, "y": 246.2, "color": "#CCFF00"},
    {"x": 335.305, "y": 164.72, "color": "#FFFFFF"},
    {"x": -135.305, "y": 164.72, "color": "#FFFFFF"},
    {"x": 382.035, "y": 246.4, "color": "#87CEEB"},
    {"x": -182.035, "y": 246.4, "color": "#87CEEB"},
    {"x": 428.765, "y": 164.72, "color": "#C0C0C0"},
    {"x": -228.765, "y": 164.72, "color": "#C0C0C0"},
    {"x": 475.490, "y": 246.4, "color": "#32CD32"},
    {"x": -275.490, "y": 246.4, "color": "#32CD32"},
    {"x": 522.214, "y": 164.72, "color": "#DAA520"},
    {"x": -322.214, "y": 164.72, "color": "#DAA520"},
    {"x": 568.939, "y": 246.4, "color": "#FF00FF"},
    {"x": -368.939, "y": 246.4, "color": "#FF00FF"},
    {"x": 615.663, "y": 164.72, "color": "#008098"},
    {"x": -415.663, "y": 164.72, "color": "#008098"}
  ],
  "triangle_series": [
    [
      {"vertices": [9, 8, 10]},
      {"vertices": [6, 9, 13]},
      {"vertices": [8, 7, 14]},
      {"vertices": [1, 6, 3]},
      {"vertices": [7, 1, 2]}
    ],
    [
      {"vertices": [12, 10, 8]},
      {"vertices": [11, 10, 9]},
      {"vertices": [14, 12, 8]},
      {"vertices": [13, 11, 9]},
      {"vertices": [7, 5, 14]},
      {"vertices": [6, 4, 13]},
      {"vertices": [2, 5, 7]},
      {"vertices": [3, 4, 6]},
      {"vertices": [0, 2, 1]},
      {"vertices": [0, 3, 1]}
    ],
    [
      {"vertices": [12, 14, 16]},
      {"vertices": [11, 13, 15]},
      {"vertices": [14, 16, 18]},
      {"vertices": [13, 15, 17]},
      {"vertices": [5, 18, 14]},
      {"vertices": [4, 17, 13]}
    ],
    [
      {"vertices": [16, 17, 19]},
      {"vertices": [15, 18, 20]},
      {"vertices": [18, 20, 22]},
      {"vertices": [17, 19, 21]}
    ],
    [
      {"vertices": [20, 22, 24]},
      {"vertices": [19, 21, 23]},
      {"vertices": [22, 24, 26]},
      {"vertices": [21, 23, 25]}
    ],
    [
      {"vertices": [24, 26, 28]},
      {"vertices": [23, 25, 27]},
      {"vertices": [26, 28, 30]},
      {"vertices": [25, 27, 29]}
    ]
  ],
  "config": {
    "center_point": {"x": 100, "y": 100},
    "width": "100%",
    "height": "400",
    "viewBox": "-450 -100 1100 370"
  },
  "geometric_lines": [
    [1, 6], [1, 7], [6, 9], [7, 8], [9, 8], [6, 13], [7, 14], [13, 9], [14, 8], [9, 11], [8, 12], [11, 10], [12, 10], [0, 1], [0, 2], [0, 3], [2, 1], [3, 1], [2, 5], [3, 4], [5, 7], [4, 6], [5, 14], [4, 13], [11, 13], [12, 14], [13, 15], [14, 16], [15, 11], [16, 12], [4, 17], [5, 18], [13, 17], [14, 18], [15, 17], [16, 18], [17, 19], [18, 20], [19, 15], [20, 16], [19, 21], [20, 22], [21, 17], [22, 18], [21, 23], [22, 24], [23, 19], [24, 20], [23, 25], [24, 26], [25, 21], [26, 22], [25, 27], [26, 28], [27, 23], [28, 24], [27, 29], [28, 30], [29, 25], [30, 26]
  ]
}
```

## Output Requirements
The generated SVG using this test specification must be visually identical to the reference static SVG, with all triangles properly subdivided into colored kites, correctly labeled, and layered appropriately.

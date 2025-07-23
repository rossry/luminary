"""Validation module for generating test SVGs and visual inspection."""

import hashlib
from pathlib import Path
from typing import List
from luminary.geometry.point import Point
from luminary.writers.svg.utilities import (
    create_svg_header,
    create_polygon_svg,
    create_circle_svg,
    create_line_svg,
    create_text_svg,
)
from luminary.geometry.triangle import Triangle, Orientation
from luminary.geometry.net import Net
from luminary.color import Color


def create_validation_svgs() -> None:
    """Generate validation SVGs for visual inspection."""
    output_dir = Path("output/validation")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Validation 1: Point operations visualization
    create_point_operations_svg(output_dir)

    # Validation 2: SVG utilities demonstration
    create_svg_utilities_demo(output_dir)

    # Validation 3: Complex shapes test
    create_complex_shapes_svg(output_dir)

    # Validation 4: Triangle geometry test
    create_triangle_geometry_svg(output_dir)

    # Validation 5: Facet subdivision test
    create_facet_subdivision_svg(output_dir)

    # Validation 7: OKLCH color validation
    create_oklch_color_validation_svg(output_dir)

    # Validation 6: Net reference validation
    create_net_reference_svg(output_dir)

    # Create individual description files
    create_description_files(output_dir)

    # Create HTML index
    create_html_index(output_dir)


def create_point_operations_svg(output_dir: Path) -> None:
    """Create SVG showing Point class operations."""
    # Test points
    p1 = Point(50, 50, "#FF6B6B")
    p2 = Point(150, 100, "#4ECDC4")
    p3 = Point(100, 25, "#45B7D1")

    # Calculate midpoints
    mid12 = Point.midpoint(p1, p2)
    mid23 = Point.midpoint(p2, p3)
    mid13 = Point.midpoint(p1, p3)

    # Create white background using polygon instead of rect
    bg_points = [Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)]

    svg_elements = [
        create_svg_header("0 0 200 150", "400px", "300px"),
        create_polygon_svg(bg_points, "white", 1.0),
        # Draw lines between points
        create_line_svg(p1, p2, "#CCCCCC", 1),
        create_line_svg(p2, p3, "#CCCCCC", 1),
        create_line_svg(p1, p3, "#CCCCCC", 1),
        # Draw original points
        create_circle_svg(p1, 8, p1.color or "black"),
        create_circle_svg(p2, 8, p2.color or "black"),
        create_circle_svg(p3, 8, p3.color or "black"),
        # Draw midpoints
        create_circle_svg(mid12, 4, "black"),
        create_circle_svg(mid23, 4, "black"),
        create_circle_svg(mid13, 4, "black"),
        # Labels
        create_text_svg("P1", Point(p1.x, p1.y - 15), 12, "black", 1.0),
        create_text_svg("P2", Point(p2.x, p2.y - 15), 12, "black", 1.0),
        create_text_svg("P3", Point(p3.x, p3.y - 15), 12, "black", 1.0),
        create_text_svg("M12", Point(mid12.x, mid12.y + 20), 10, "black", 0.8),
        create_text_svg("M23", Point(mid23.x, mid23.y + 20), 10, "black", 0.8),
        create_text_svg("M13", Point(mid13.x, mid13.y + 20), 10, "black", 0.8),
        "</svg>",
    ]

    with open(output_dir / "01_point_operations.svg", "w") as f:
        f.write("\n".join(svg_elements))


def create_svg_utilities_demo(output_dir: Path) -> None:
    """Create SVG demonstrating all utility functions."""
    # Background
    bg_points = [Point(0, 0), Point(300, 0), Point(300, 200), Point(0, 200)]

    svg_elements = [
        create_svg_header("0 0 300 200", "600px", "400px"),
        create_polygon_svg(bg_points, "#F8F9FA", 1.0),
        # Polygon (triangle)
        create_polygon_svg(
            [Point(50, 50), Point(100, 50), Point(75, 25)], "#FF6B6B", 0.7
        ),
        # Polygon (pentagon)
        create_polygon_svg(
            [
                Point(150, 40),
                Point(170, 55),
                Point(160, 75),
                Point(140, 75),
                Point(130, 55),
            ],
            "#4ECDC4",
            0.6,
            "black",
        ),
        # Circles
        create_circle_svg(Point(250, 40), 20, "#45B7D1", "navy", 2),
        create_circle_svg(Point(50, 120), 15, "none", "#FF6B6B", 3),
        # Lines
        create_line_svg(Point(120, 90), Point(180, 130), "purple", 3),
        create_line_svg(Point(200, 90), Point(280, 90), "#FF9F43", 5),
        # Text samples
        create_text_svg("Triangle", Point(75, 90), 14, "black", 1.0),
        create_text_svg("Pentagon", Point(150, 100), 12, "darkgreen", 0.8),
        create_text_svg("Circles", Point(250, 80), 10, "navy", 1.0),
        create_text_svg("Lines + Text", Point(200, 150), 16, "purple", 0.9),
        "</svg>",
    ]

    with open(output_dir / "02_svg_utilities.svg", "w") as f:
        f.write("\n".join(svg_elements))


def create_complex_shapes_svg(output_dir: Path) -> None:
    """Create SVG with complex layered shapes."""
    # Background
    bg_points = [Point(0, 0), Point(400, 0), Point(400, 300), Point(0, 300)]

    svg_elements = [
        create_svg_header("0 0 400 300", "800px", "600px"),
        create_polygon_svg(bg_points, "#2C3E50", 1.0),
        # Background star shape
        create_polygon_svg(
            [
                Point(200, 50),
                Point(220, 120),
                Point(280, 120),
                Point(235, 160),
                Point(250, 230),
                Point(200, 190),
                Point(150, 230),
                Point(165, 160),
                Point(120, 120),
                Point(180, 120),
            ],
            "#F39C12",
            0.3,
        ),
        # Overlapping circles with transparency (using circle approximation with polygons)
        # Red circle (approximated as octagon)
        create_polygon_svg(
            [
                Point(100, 150),
                Point(129, 129),
                Point(150, 100),
                Point(171, 129),
                Point(200, 150),
                Point(171, 171),
                Point(150, 200),
                Point(129, 171),
            ],
            "#E74C3C",
            0.6,
        ),
        # Blue circle (approximated as octagon)
        create_polygon_svg(
            [
                Point(150, 150),
                Point(179, 129),
                Point(200, 100),
                Point(221, 129),
                Point(250, 150),
                Point(221, 171),
                Point(200, 200),
                Point(179, 171),
            ],
            "#3498DB",
            0.6,
        ),
        # Green circle (approximated as octagon)
        create_polygon_svg(
            [
                Point(200, 150),
                Point(229, 129),
                Point(250, 100),
                Point(271, 129),
                Point(300, 150),
                Point(271, 171),
                Point(250, 200),
                Point(229, 171),
            ],
            "#2ECC71",
            0.6,
        ),
        # Inner triangular pattern
        create_polygon_svg(
            [Point(175, 125), Point(200, 175), Point(150, 175)], "#FFFFFF", 0.8
        ),
        create_polygon_svg(
            [Point(225, 125), Point(250, 175), Point(200, 175)], "#FFFFFF", 0.8
        ),
        # Border lines
        create_line_svg(Point(50, 50), Point(350, 50), "#ECF0F1", 2),
        create_line_svg(Point(350, 50), Point(350, 250), "#ECF0F1", 2),
        create_line_svg(Point(350, 250), Point(50, 250), "#ECF0F1", 2),
        create_line_svg(Point(50, 250), Point(50, 50), "#ECF0F1", 2),
        # Corner circles
        create_circle_svg(Point(50, 50), 8, "#E67E22"),
        create_circle_svg(Point(350, 50), 8, "#E67E22"),
        create_circle_svg(Point(350, 250), 8, "#E67E22"),
        create_circle_svg(Point(50, 250), 8, "#E67E22"),
        # Title
        create_text_svg("Complex Layered Shapes", Point(200, 30), 18, "#ECF0F1", 1.0),
        create_text_svg(
            "Foundation Infrastructure Test", Point(200, 280), 14, "#BDC3C7", 0.8
        ),
        "</svg>",
    ]

    with open(output_dir / "03_complex_shapes.svg", "w") as f:
        f.write("\n".join(svg_elements))


def create_triangle_geometry_svg(output_dir: Path) -> None:
    """Create SVG demonstrating Triangle geometry calculations."""
    # Background
    bg_points = [Point(0, 0), Point(500, 0), Point(500, 400), Point(0, 400)]

    # Test triangles with different orientations and shapes
    apex = Point(250, 200)  # Central reference point

    # Triangle 1: APEXWARD - right triangle with one vertex close to apex
    t1_p1 = Point(240, 190)  # Close to apex
    t1_p2 = Point(200, 100)  # Far from apex
    t1_p3 = Point(150, 150)  # Far from apex
    triangle1 = Triangle(t1_p1, t1_p2, t1_p3, 1, apex)

    # Triangle 2: NADIRWARD - triangle with two vertices close to apex
    t2_p1 = Point(260, 190)  # Close to apex
    t2_p2 = Point(240, 190)  # Close to apex
    t2_p3 = Point(400, 100)  # Far from apex
    triangle2 = Triangle(t2_p1, t2_p2, t2_p3, 2, apex)

    # Triangle 3: Equilateral for incenter validation
    t3_p1 = Point(350, 300)
    t3_p2 = Point(450, 300)
    t3_p3 = Point(400, 213.4)  # Approximately equilateral
    triangle3 = Triangle(t3_p1, t3_p2, t3_p3, 3, apex)

    svg_elements = [
        create_svg_header("0 0 500 400", "1000px", "800px"),
        create_polygon_svg(bg_points, "#F8F9FA", 1.0),
        # Draw apex reference point
        create_circle_svg(apex, 6, "#E74C3C", "darkred", 2),
        create_text_svg("APEX", Point(apex.x, apex.y - 15), 14, "darkred", 1.0),
        # Triangle 1: APEXWARD (should be light blue)
        create_polygon_svg(triangle1.vertices, "#AED6F1", 0.7, "#2874A6"),
        create_circle_svg(triangle1.incenter, 4, "#2874A6"),
        create_text_svg(
            f"T1 {triangle1.orientation.value}",
            Point(t1_p1.x - 30, t1_p1.y - 20),
            12,
            "#2874A6",
            1.0,
        ),
        # Triangle 2: NADIRWARD (should be light green)
        create_polygon_svg(triangle2.vertices, "#ABEBC6", 0.7, "#27AE60"),
        create_circle_svg(triangle2.incenter, 4, "#27AE60"),
        create_text_svg(
            f"T2 {triangle2.orientation.value}",
            Point(t2_p1.x + 10, t2_p1.y - 15),
            12,
            "#27AE60",
            1.0,
        ),
        # Triangle 3: Equilateral (should be light orange)
        create_polygon_svg(triangle3.vertices, "#F8C471", 0.7, "#E67E22"),
        create_circle_svg(triangle3.incenter, 4, "#E67E22"),
        create_text_svg(
            f"T3 {triangle3.orientation.value}",
            Point(t3_p1.x, t3_p1.y + 25),
            12,
            "#E67E22",
            1.0,
        ),
        # Draw lines from incenters to apex to show distance relationships
        create_line_svg(triangle1.incenter, apex, "#2874A6", 1),
        create_line_svg(triangle2.incenter, apex, "#27AE60", 1),
        create_line_svg(triangle3.incenter, apex, "#E67E22", 1),
        # Draw edge midpoints for Triangle 1
        create_circle_svg(triangle1.edge_midpoints[0], 2, "#85929E"),
        create_circle_svg(triangle1.edge_midpoints[1], 2, "#85929E"),
        create_circle_svg(triangle1.edge_midpoints[2], 2, "#85929E"),
        # Title and legend
        create_text_svg(
            "Triangle Geometry Validation", Point(250, 30), 18, "#2C3E50", 1.0
        ),
        create_text_svg(
            "• Incenters (black dots) • Orientations • Edge midpoints (gray dots)",
            Point(250, 380),
            12,
            "#5D6D7E",
            0.8,
        ),
        "</svg>",
    ]

    with open(output_dir / "04_triangle_geometry.svg", "w") as f:
        f.write("\n".join(svg_elements))


def create_facet_subdivision_svg(output_dir: Path) -> None:
    """Create SVG demonstrating Facet subdivision of triangles."""
    # Background
    bg_points = [Point(0, 0), Point(600, 0), Point(600, 400), Point(0, 400)]

    # Test triangles with different orientations and colors
    apex = Point(300, 200)  # Central reference point

    # Both triangles point downward, positioned directly above/below the apex
    side_length = 60
    height = side_length * (3**0.5) / 2  # Height of equilateral triangle

    # Triangle 1: APEXWARD - above apex, pointing down toward it (counterclockwise vertices)
    t1_center_x = 300  # Same x as apex
    t1_center_y = 100  # Above apex
    t1_p1 = Point(
        t1_center_x, t1_center_y + 2 * height / 3, "#FF6B6B"
    )  # Bottom vertex pointing toward apex
    t1_p2 = Point(
        t1_center_x + side_length / 2, t1_center_y - height / 3, "#4ECDC4"
    )  # Top right
    t1_p3 = Point(
        t1_center_x - side_length / 2, t1_center_y - height / 3, "#45B7D1"
    )  # Top left
    triangle1 = Triangle(t1_p1, t1_p2, t1_p3, 1, apex)

    # Triangle 2: NADIRWARD - below apex, pointing down away from it (counterclockwise vertices)
    t2_center_x = 300  # Same x as apex
    t2_center_y = 300  # Below apex
    t2_p1 = Point(
        t2_center_x, t2_center_y + 2 * height / 3, "#FF6B6B"
    )  # Bottom vertex pointing away from apex
    t2_p2 = Point(
        t2_center_x + side_length / 2, t2_center_y - height / 3, "#4ECDC4"
    )  # Top right (close to apex)
    t2_p3 = Point(
        t2_center_x - side_length / 2, t2_center_y - height / 3, "#45B7D1"
    )  # Top left (close to apex)
    triangle2 = Triangle(t2_p1, t2_p2, t2_p3, 2, apex)

    svg_elements = [
        create_svg_header("0 0 600 400", "1200px", "800px"),
        create_polygon_svg(bg_points, "#F8F9FA", 1.0),
        # Draw apex reference point
        create_circle_svg(apex, 6, "#E74C3C", "darkred", 2),
        create_text_svg("APEX", Point(apex.x, apex.y - 15), 14, "darkred", 1.0),
        # Triangle 1: Draw triangle fill first (behind facets)
        create_polygon_svg(triangle1.vertices, "black", 0.4),
        create_circle_svg(triangle1.incenter, 3, "black"),
        # Triangle 1: Draw all facets
        *[svg for facet in triangle1.facets for svg in facet.get_svg()],
        # Triangle 1: Labels and info
        create_text_svg(
            f"T1 {triangle1.orientation.value}", Point(300, 140), 16, "#2874A6", 1.0
        ),
        # Triangle 2: Draw triangle fill first (behind facets)
        create_polygon_svg(triangle2.vertices, "black", 0.4),
        create_circle_svg(triangle2.incenter, 3, "black"),
        # Triangle 2: Draw all facets
        *[svg for facet in triangle2.facets for svg in facet.get_svg()],
        # Triangle 2: Labels and info
        create_text_svg(
            f"T2 {triangle2.orientation.value}", Point(300, 340), 16, "#27AE60", 1.0
        ),
        # Draw construction lines (incenter to edge midpoints) for Triangle 1
        create_line_svg(triangle1.incenter, triangle1.edge_midpoints[0], "#666666", 1),
        create_line_svg(triangle1.incenter, triangle1.edge_midpoints[1], "#666666", 1),
        create_line_svg(triangle1.incenter, triangle1.edge_midpoints[2], "#666666", 1),
        # Draw construction lines for Triangle 2
        create_line_svg(triangle2.incenter, triangle2.edge_midpoints[0], "#666666", 1),
        create_line_svg(triangle2.incenter, triangle2.edge_midpoints[1], "#666666", 1),
        create_line_svg(triangle2.incenter, triangle2.edge_midpoints[2], "#666666", 1),
        # Title and legend
        create_text_svg(
            "Kite Subdivision Validation", Point(300, 30), 20, "#2C3E50", 1.0
        ),
        create_text_svg(
            "• Triangles subdivided into 3 colored kites • Labels show orientation-based naming",
            Point(300, 380),
            14,
            "#5D6D7E",
            0.8,
        ),
        "</svg>",
    ]

    with open(output_dir / "05_kite_subdivision.svg", "w") as f:
        f.write("\n".join(svg_elements))


def create_net_reference_svg(output_dir: Path) -> None:
    """Create SVG from Net reference configuration for validation."""
    # Load the reference configuration and generate SVG
    config_path = Path("plan/svg-diagram/reference-v4.json")

    if not config_path.exists():
        # Create a simple placeholder if reference doesn't exist
        svg_elements = [
            create_svg_header("-450 -100 1100 370", "100%", "400"),
            create_text_svg(
                "Reference configuration not found", Point(100, 100), 24, "red", 1.0
            ),
            create_text_svg(
                f"Expected: {config_path}", Point(100, 140), 16, "red", 0.8
            ),
            "</svg>",
        ]
        svg_content = "\n".join(svg_elements)
    else:
        # Generate actual Net reference SVG
        net = Net.from_json_file(config_path)
        svg_elements = net.get_svg()
        svg_content = "".join(svg_elements)

    # Save the generated SVG
    with open(output_dir / "06_net_reference.svg", "w") as f:
        f.write(svg_content)

    # Copy the original reference SVG for comparison
    original_reference = Path("plan/svg-diagram/REFERENCE.svg")
    if original_reference.exists():
        import shutil

        shutil.copy(original_reference, output_dir / "06_original_reference.svg")


def create_description_files(output_dir: Path) -> None:
    """Create individual HTML description files for each SVG."""

    descriptions = {
        "01_point_operations.html": """<div class="description">
<h3>Point Operations Test</h3>
<p><strong>Expected:</strong> Three colored circles (red P1, teal P2, blue P3) connected by gray lines, with small black circles at midpoints labeled M12, M23, M13.</p>
<p><strong>Validates:</strong> Point coordinates, distance calculations, midpoint calculations.</p>
</div>""",
        "02_svg_utilities.html": """<div class="description">
<h3>SVG Utilities Demo</h3>
<p><strong>Expected:</strong> Light gray background with red triangle, teal pentagon with black border, blue circle with navy border, red circle outline, purple/orange lines, and various text labels.</p>
<p><strong>Validates:</strong> All SVG utility functions (polygons, circles, lines, text).</p>
</div>""",
        "03_complex_shapes.html": """<div class="description">
<h3>Complex Layered Shapes</h3>
<p><strong>Expected:</strong> Dark blue background, golden semi-transparent star, three overlapping transparent octagonal shapes (red/blue/green) creating visible overlap effects, white semi-transparent triangular shapes, white border rectangle with orange corners, and title text.</p>
<p><strong>Validates:</strong> Complex layering, transparency effects, coordinate precision, shape overlapping.</p>
</div>""",
        "04_triangle_geometry.html": """<div class="description">
<h3>Triangle Geometry Calculations</h3>
<p><strong>Expected:</strong> Light gray background with red APEX point, three colored triangles: blue APEXWARD triangle (T1), green NADIRWARD triangle (T2), orange equilateral triangle (T3). Each shows incenter (colored dot), orientation label, lines to apex, and gray edge midpoints on T1.</p>
<p><strong>Validates:</strong> Triangle incenter calculations, orientation detection logic, edge midpoint calculations, Triangle class initialization.</p>
</div>""",
        "05_kite_subdivision.html": """<div class="description">
<h3>Kite Subdivision of Triangles</h3>
<p><strong>Expected:</strong> Light gray background with red APEX point, two triangles subdivided into colored kites. T1 (APEXWARD) shows 3 kites labeled A-C in different colors (red, teal, blue). T2 (NADIRWARD) shows 3 kites labeled D-F in different colors (green, yellow, plum). Black construction lines show incenter to edge midpoints.</p>
<p><strong>Validates:</strong> Kite creation from triangle subdivision, kite coloring from vertex inheritance, orientation-based labeling (A-C vs D-F), kite centroid calculation for label positioning.</p>
</div>""",
        "06_net_reference.html": """<div class="description">
<h3>Net Reference Pattern from JSON</h3>
<p><strong>Expected:</strong> Two identical pentagon patterns - the top one generated from reference-v4.json using Net class, the bottom one is the original reference. Both should show complete pentagon pattern with 33 triangles subdivided into 99 kites, 31 colored vertex circles, 60 geometric lines, and 33 incenter dots.</p>
<p><strong>Validates:</strong> End-to-end JSON configuration parsing, Net class triangle/kite creation, Pydantic schema validation, complete SVG generation pipeline, color mapping from configuration. Visual comparison ensures generated output matches original reference exactly.</p>
</div>""",
    }

    for filename, content in descriptions.items():
        with open(output_dir / filename, "w") as f:
            f.write(content)


def get_file_hash(file_path: Path) -> str:
    """Get SHA-256 hash of file contents."""
    if not file_path.exists():
        return "missing"

    with open(file_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]  # Use first 16 chars


def create_html_index(output_dir: Path) -> None:
    """Create HTML index page displaying all SVGs and descriptions."""

    # Get hashes for each SVG file
    svg_files = [
        "01_point_operations.svg",
        "02_svg_utilities.svg",
        "03_complex_shapes.svg",
        "04_triangle_geometry.svg",
        "05_kite_subdivision.svg",
        "06_net_reference.svg",
        "07_oklch_color_validation.svg",
    ]

    file_hashes = {}
    for svg_file in svg_files:
        file_hashes[svg_file] = get_file_hash(output_dir / svg_file)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Foundation Infrastructure Validation</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .validation-section {{ background: white; margin: 20px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); overflow: hidden; }}
        .validation-header {{ background: #34495e; color: white; padding: 15px 20px; cursor: pointer; user-select: none; }}
        .validation-header:hover {{ background: #2c3e50; }}
        .validation-header h2 {{ margin: 0; font-size: 1.2em; }}
        .validation-content {{ padding: 20px; display: block; }}
        .validation-content.collapsed {{ display: none; }}
        .svg-container {{ text-align: center; margin: 20px 0; }}
        .svg-container svg {{ border: 1px solid #ddd; border-radius: 4px; }}
        .svg-comparison {{ display: flex; flex-direction: column; gap: 30px; }}
        .svg-comparison-item {{ flex: 1; }}
        .svg-comparison-item h4 {{ 
            color: #2c3e50; 
            text-align: center; 
            margin: 0 0 15px 0; 
            font-size: 16px; 
            font-weight: bold;
        }}
        .description {{ margin: 10px 0; }}
        .description h3 {{ color: #2c3e50; margin-top: 0; }}
        .description p {{ margin: 8px 0; line-height: 1.5; }}
        .description strong {{ color: #34495e; }}
        h1 {{ color: #2c3e50; text-align: center; }}
        .success-criteria {{ background: #e8f5e8; padding: 15px; border-radius: 4px; margin: 20px 0; }}
        .success-criteria h3 {{ color: #27ae60; margin-top: 0; }}
        .toggle-icon {{ float: right; transition: transform 0.3s; }}
        .collapsed .toggle-icon {{ transform: rotate(-90deg); }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Foundation Infrastructure Validation</h1>
        
        <div class="validation-section" data-hash="{file_hashes['01_point_operations.svg']}">
            <div class="validation-header" onclick="toggleSection(1)">
                <h2>Calculate and Draw Points <span class="toggle-icon">▼</span></h2>
            </div>
            <div class="validation-content" id="content1">
                <div class="svg-container">
                    <object data="01_point_operations.svg" type="image/svg+xml" width="400" height="300"></object>
                </div>
                <div id="desc1"></div>
            </div>
        </div>
        
        <div class="validation-section" data-hash="{file_hashes['02_svg_utilities.svg']}">
            <div class="validation-header" onclick="toggleSection(2)">
                <h2>Draw Simple Shapes <span class="toggle-icon">▼</span></h2>
            </div>
            <div class="validation-content" id="content2">
                <div class="svg-container">
                    <object data="02_svg_utilities.svg" type="image/svg+xml" width="600" height="400"></object>
                </div>
                <div id="desc2"></div>
            </div>
        </div>
        
        <div class="validation-section" data-hash="{file_hashes['03_complex_shapes.svg']}">
            <div class="validation-header" onclick="toggleSection(3)">
                <h2>Draw Complex and Layered Shapes <span class="toggle-icon">▼</span></h2>
            </div>
            <div class="validation-content" id="content3">
                <div class="svg-container">
                    <object data="03_complex_shapes.svg" type="image/svg+xml" width="800" height="600"></object>
                </div>
                <div id="desc3"></div>
            </div>
        </div>
        
        <div class="validation-section" data-hash="{file_hashes['04_triangle_geometry.svg']}">
            <div class="validation-header" onclick="toggleSection(4)">
                <h2>Calculate Triangle Geometry <span class="toggle-icon">▼</span></h2>
            </div>
            <div class="validation-content" id="content4">
                <div class="svg-container">
                    <object data="04_triangle_geometry.svg" type="image/svg+xml" width="1000" height="800"></object>
                </div>
                <div id="desc4"></div>
            </div>
        </div>
        
        <div class="validation-section" data-hash="{file_hashes['05_kite_subdivision.svg']}">
            <div class="validation-header" onclick="toggleSection(5)">
                <h2>Subdivide Triangles into Kites <span class="toggle-icon">▼</span></h2>
            </div>
            <div class="validation-content" id="content5">
                <div class="svg-container">
                    <object data="05_kite_subdivision.svg" type="image/svg+xml" width="1200" height="800"></object>
                </div>
                <div id="desc5"></div>
            </div>
        </div>
        
        <div class="validation-section" data-hash="{file_hashes['06_net_reference.svg']}">
            <div class="validation-header" onclick="toggleSection(6)">
                <h2>Net Reference Pattern from JSON <span class="toggle-icon">▼</span></h2>
            </div>
            <div class="validation-content" id="content6">
                <div class="svg-comparison">
                    <div class="svg-comparison-item">
                        <h4>Generated from JSON Configuration (Net class)</h4>
                        <div class="svg-container">
                            <object data="06_net_reference.svg" type="image/svg+xml" width="100%" height="400"></object>
                        </div>
                    </div>
                    <div class="svg-comparison-item">
                        <h4>Original Reference Pattern</h4>
                        <div class="svg-container">
                            <object data="06_original_reference.svg" type="image/svg+xml" width="100%" height="400"></object>
                        </div>
                    </div>
                </div>
                <div id="desc6"></div>
            </div>
        </div>
        
        <div class="validation-section" data-hash="{file_hashes['07_oklch_color_validation.svg']}">
            <div class="validation-header" onclick="toggleSection(7)">
                <h2>OKLCH Color Space Validation <span class="toggle-icon">▼</span></h2>
            </div>
            <div class="validation-content" id="content7">
                <div class="svg-container">
                    <object data="07_oklch_color_validation.svg" type="image/svg+xml" width="800" height="600"></object>
                </div>
                <div id="desc7"></div>
            </div>
        </div>
        
        <div class="success-criteria">
            <h3>Validation Success Criteria</h3>
            <p>✅ All shapes render correctly - no distorted or missing elements<br>
            ✅ Colors match descriptions - proper color rendering and transparency<br>
            ✅ Text is readable and positioned correctly<br>
            ✅ Layering is correct - elements appear in proper order<br>
            ✅ Coordinates are precise - shapes align properly</p>
        </div>
    </div>
    
    <script>
        // Load description files
        fetch('01_point_operations.html').then(r => r.text()).then(html => 
            document.getElementById('desc1').innerHTML = html);
        fetch('02_svg_utilities.html').then(r => r.text()).then(html => 
            document.getElementById('desc2').innerHTML = html);
        fetch('03_complex_shapes.html').then(r => r.text()).then(html => 
            document.getElementById('desc3').innerHTML = html);
        fetch('04_triangle_geometry.html').then(r => r.text()).then(html => 
            document.getElementById('desc4').innerHTML = html);
        fetch('05_kite_subdivision.html').then(r => r.text()).then(html => 
            document.getElementById('desc5').innerHTML = html);
        fetch('06_net_reference.html').then(r => r.text()).then(html => 
            document.getElementById('desc6').innerHTML = html);
        fetch('07_oklch_color_validation.html').then(r => r.text()).then(html => 
            document.getElementById('desc7').innerHTML = html);
        
        // LocalStorage key for collapsed sections
        const STORAGE_KEY = 'luminary_validation_collapsed';
        
        // Get collapsed hashes from localStorage
        function getCollapsedHashes() {{
            const stored = localStorage.getItem(STORAGE_KEY);
            return stored ? JSON.parse(stored) : {{}};
        }}
        
        // Save collapsed hashes to localStorage  
        function saveCollapsedHashes(collapsedHashes) {{
            localStorage.setItem(STORAGE_KEY, JSON.stringify(collapsedHashes));
        }}
        
        // Initialize sections based on localStorage
        function initializeSections() {{
            const collapsedHashes = getCollapsedHashes();
            const sections = document.querySelectorAll('.validation-section');
            
            sections.forEach((section, index) => {{
                const hash = section.getAttribute('data-hash');
                const sectionNum = index + 1;
                const content = document.getElementById('content' + sectionNum);
                const header = content.previousElementSibling;
                
                if (collapsedHashes[hash]) {{
                    content.classList.add('collapsed');
                    header.classList.add('collapsed');
                }}
            }});
        }}
        
        // Toggle section visibility
        function toggleSection(sectionNum) {{
            const content = document.getElementById('content' + sectionNum);
            const header = content.previousElementSibling;
            const section = header.parentElement;
            const hash = section.getAttribute('data-hash');
            
            const collapsedHashes = getCollapsedHashes();
            
            if (content.classList.contains('collapsed')) {{
                content.classList.remove('collapsed');
                header.classList.remove('collapsed');
                delete collapsedHashes[hash];
            }} else {{
                content.classList.add('collapsed');
                header.classList.add('collapsed');
                collapsedHashes[hash] = true;
            }}
            
            saveCollapsedHashes(collapsedHashes);
        }}
        
        // Initialize on page load
        window.addEventListener('load', initializeSections);
    </script>
</body>
</html>"""

    with open(output_dir / "index.html", "w") as f:
        f.write(html_content)


def create_oklch_color_validation_svg(output_dir: Path) -> None:
    """Create OKLCH color validation demonstrating color conversion and brightness adjustment."""

    svg_content = create_svg_header(viewbox="0 0 800 600", width="800", height="600")
    svg_content += (
        '<rect width="800" height="600" fill="#f8f8fa"/>\n'  # Light background
    )

    # Title
    svg_content += create_text_svg(
        "OKLCH Color Validation", Point(400, 30), 24, "#2c3e50", 1.0
    )
    svg_content += create_text_svg(
        "Testing color conversion and brightness adjustments",
        Point(400, 55),
        14,
        "#7f8c8d",
        1.0,
    )

    # Test color sets
    test_colors = [
        ("Red", "#FF0000", 100),
        ("Green", "#00FF00", 200),
        ("Blue", "#0000FF", 300),
        ("Purple", "#800080", 400),
        ("Orange", "#FFA500", 500),
        ("Darkcyan", "darkcyan", 600),
        ("Forestgreen", "forestgreen", 700),
    ]

    # Column headers
    svg_content += create_text_svg("Original", Point(150, 90), 16, "#2c3e50", 1.0)
    svg_content += create_text_svg("20% Darker", Point(300, 90), 16, "#2c3e50", 1.0)
    svg_content += create_text_svg("20% Brighter", Point(450, 90), 16, "#2c3e50", 1.0)
    svg_content += create_text_svg("OKLCH CSS", Point(600, 90), 16, "#2c3e50", 1.0)

    y_start = 120

    for i, (name, color_str, _) in enumerate(test_colors):
        y = y_start + i * 60

        # Original color
        original = Color.from_color_string(color_str)
        original_hex = original.to_hex()

        # Brightness variations
        darker = original.adjust_lightness(0.8)  # 20% darker
        brighter = original.adjust_lightness(1.2)  # 20% brighter

        darker_hex = darker.to_hex()
        brighter_hex = brighter.to_hex()
        oklch_css = original.to_oklch_string()

        # Draw color swatches
        swatch_width = 50
        swatch_height = 30

        # Original swatch
        svg_content += create_polygon_svg(
            [
                Point(125, y),
                Point(125 + swatch_width, y),
                Point(125 + swatch_width, y + swatch_height),
                Point(125, y + swatch_height),
            ],
            original_hex,
            1.0,
        )

        # Darker swatch
        svg_content += create_polygon_svg(
            [
                Point(275, y),
                Point(275 + swatch_width, y),
                Point(275 + swatch_width, y + swatch_height),
                Point(275, y + swatch_height),
            ],
            darker_hex,
            1.0,
        )

        # Brighter swatch
        svg_content += create_polygon_svg(
            [
                Point(425, y),
                Point(425 + swatch_width, y),
                Point(425 + swatch_width, y + swatch_height),
                Point(425, y + swatch_height),
            ],
            brighter_hex,
            1.0,
        )

        # Labels
        svg_content += create_text_svg(name, Point(50, y + 20), 12, "#2c3e50", 1.0)
        svg_content += create_text_svg(
            original_hex, Point(150, y + 45), 10, "#7f8c8d", 1.0
        )
        svg_content += create_text_svg(
            darker_hex, Point(300, y + 45), 10, "#7f8c8d", 1.0
        )
        svg_content += create_text_svg(
            brighter_hex, Point(450, y + 45), 10, "#7f8c8d", 1.0
        )
        svg_content += create_text_svg(oklch_css, Point(580, y + 20), 9, "#7f8c8d", 1.0)

    # Add validation notes
    svg_content += create_text_svg(
        "Expected: Each row shows original color, 20% darker, 20% brighter versions",
        Point(400, 550),
        12,
        "#34495e",
        1.0,
    )
    svg_content += create_text_svg(
        "Validates: OKLCH color conversion, lightness adjustment, hex output",
        Point(400, 570),
        12,
        "#34495e",
        1.0,
    )

    svg_content += "</svg>"

    # Save SVG
    output_path = output_dir / "07_oklch_color_validation.svg"
    output_path.write_text(svg_content)


def run_validation() -> List[str]:
    """Run validation and return list of created files."""
    create_validation_svgs()

    # Return list of SVGs created
    return [
        "01_point_operations.svg - Point coordinates, distances, midpoints with triangle and labels",
        "02_svg_utilities.svg - All SVG utilities: polygons, circles, lines, text on light background",
        "03_complex_shapes.svg - Complex layering with star, overlapping circles, borders on dark background",
        "04_triangle_geometry.svg - Triangle incenters, orientations, edge midpoints with colored triangles",
        "05_kite_subdivision.svg - Triangles subdivided into colored kites with orientation-based labeling",
        "06_net_reference.svg - Net reference validation with reference overlay and facet inspection",
        "07_oklch_color_validation.svg - OKLCH color conversion with brightness adjustments and CSS output",
    ]


if __name__ == "__main__":
    print("Running foundation infrastructure validation...")
    svg_list = run_validation()
    print("Validation files created in output/validation/")
    print("\nSVGs to check:")
    for svg_desc in svg_list:
        print(f"• {svg_desc}")
    print("\nOpen output/validation/index.html in browser to view all SVGs together.")

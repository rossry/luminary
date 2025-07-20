"""Validation module for generating test SVGs and visual inspection."""

import os
import hashlib
from pathlib import Path
from luminary.geometry.point import Point
from luminary.writers.svg.utilities import (
    create_svg_header,
    create_polygon_svg,
    create_circle_svg,
    create_line_svg,
    create_text_svg,
)


def create_validation_svgs():
    """Generate validation SVGs for visual inspection."""
    output_dir = Path("output/validation")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Validation 1: Point operations visualization
    create_point_operations_svg(output_dir)

    # Validation 2: SVG utilities demonstration
    create_svg_utilities_demo(output_dir)

    # Validation 3: Complex shapes test
    create_complex_shapes_svg(output_dir)

    # Create individual description files
    create_description_files(output_dir)

    # Create HTML index
    create_html_index(output_dir)


def create_point_operations_svg(output_dir: Path):
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
        create_circle_svg(p1, 8, p1.color),
        create_circle_svg(p2, 8, p2.color),
        create_circle_svg(p3, 8, p3.color),
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


def create_svg_utilities_demo(output_dir: Path):
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


def create_complex_shapes_svg(output_dir: Path):
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


def create_description_files(output_dir: Path):
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


def create_html_index(output_dir: Path):
    """Create HTML index page displaying all SVGs and descriptions."""

    # Get hashes for each SVG file
    svg_files = [
        "01_point_operations.svg",
        "02_svg_utilities.svg",
        "03_complex_shapes.svg",
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


def run_validation():
    """Run validation and return list of created files."""
    create_validation_svgs()

    # Return list of SVGs created
    return [
        "01_point_operations.svg - Point coordinates, distances, midpoints with triangle and labels",
        "02_svg_utilities.svg - All SVG utilities: polygons, circles, lines, text on light background",
        "03_complex_shapes.svg - Complex layering with star, overlapping circles, borders on dark background",
    ]


if __name__ == "__main__":
    print("Running foundation infrastructure validation...")
    svg_list = run_validation()
    print("Validation files created in output/validation/")
    print("\nSVGs to check:")
    for svg_desc in svg_list:
        print(f"• {svg_desc}")
    print("\nOpen output/validation/index.html in browser to view all SVGs together.")

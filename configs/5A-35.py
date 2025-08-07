#!/usr/bin/env python3
"""
Generate 5A-35.json configuration for a pentagon star pattern.

Creates a regular pentagon centered at (0,0) with equilateral triangles
extending from each edge to form a 5-pointed star pattern.
"""

import json
import math
from pathlib import Path


def main():
    """Generate 5A-35.json configuration."""

    # Pentagon parameters
    apex = [0.0, 0.0]
    side_length = 50.0

    # Calculate circumradius for regular pentagon with given side length
    # R = s / (2 * sin(π/5))
    circumradius = side_length / (2 * math.sin(math.pi / 5))

    # Programmatic generation of 5 layers of vertices
    all_points = []

    # Layer indices tracking
    layer1_start = 0  # Inner pentagon vertices (5 points)
    layer2vertex_start = 5  # Outer pentagon vertices (5 points)
    layer2center_start = 10  # Star/edge center points (5 points)
    layer3first_start = 15  # First extension points (5 points)
    layer3second_start = 20  # Second extension points (5 points)
    layer4_start = 25  # Outer triangle points (5 points)

    # Generate all layers by looping 5 times (once per direction)
    for i in range(5):
        angle = -math.pi / 2 + i * 2 * math.pi / 5  # -90° + i * 72°

        # Layer 1: Inner pentagon vertex
        x1 = circumradius * math.cos(angle)
        y1 = circumradius * math.sin(angle)
        all_points.append([x1, y1])

    # Calculate star distance and outer radius for layers 2-3
    # First get a layer2center point to calculate distances
    v1 = all_points[0]  # layer1[0]
    v2 = all_points[1]  # layer1[1]
    mid_x = (v1[0] + v2[0]) / 2
    mid_y = (v1[1] + v2[1]) / 2
    normal_x = mid_x - apex[0]
    normal_y = mid_y - apex[1]
    length = math.sqrt(normal_x**2 + normal_y**2)
    normal_x /= length
    normal_y /= length
    triangle_height = side_length * math.sqrt(3) / 2
    sample_star_x = mid_x + triangle_height * normal_x
    sample_star_y = mid_y + triangle_height * normal_y
    star_distance = math.sqrt(sample_star_x**2 + sample_star_y**2)
    outer_radius = star_distance / math.cos(math.pi / 5)

    for i in range(5):
        angle = -math.pi / 2 + i * 2 * math.pi / 5

        # Layer 2 vertex: Outer pentagon vertex
        x2v = outer_radius * math.cos(angle)
        y2v = outer_radius * math.sin(angle)
        all_points.append([x2v, y2v])

    for i in range(5):
        # Layer 2 center: Star/edge center point
        v1 = all_points[layer1_start + i]
        v2 = all_points[layer1_start + (i + 1) % 5]

        mid_x = (v1[0] + v2[0]) / 2
        mid_y = (v1[1] + v2[1]) / 2
        normal_x = mid_x - apex[0]
        normal_y = mid_y - apex[1]
        length = math.sqrt(normal_x**2 + normal_y**2)
        normal_x /= length
        normal_y /= length
        triangle_height = side_length * math.sqrt(3) / 2

        star_x = mid_x + triangle_height * normal_x
        star_y = mid_y + triangle_height * normal_y
        all_points.append([star_x, star_y])

    for i in range(5):
        # Layer 3 first: First extension point (from next vertex through star)
        star_point = all_points[layer2center_start + i]
        inner_vertex = all_points[layer1_start + (i + 1) % 5]

        vec_x = star_point[0] - inner_vertex[0]
        vec_y = star_point[1] - inner_vertex[1]
        ext_x = star_point[0] + vec_x
        ext_y = star_point[1] + vec_y
        all_points.append([ext_x, ext_y])

    for i in range(5):
        # Layer 3 second: Second extension point (from current vertex through star)
        star_point = all_points[layer2center_start + i]
        inner_vertex = all_points[layer1_start + i]

        vec_x = star_point[0] - inner_vertex[0]
        vec_y = star_point[1] - inner_vertex[1]
        ext_x = star_point[0] + vec_x
        ext_y = star_point[1] + vec_y
        all_points.append([ext_x, ext_y])

    for i in range(5):
        # Layer 4: Outer triangle point using shortcut method
        layer2center_point = all_points[layer2center_start + i]
        layer3first_point = all_points[layer3first_start + i]
        layer3second_point = all_points[layer3second_start + i]

        # Vector from layer2center to layer3first
        diff_x = layer3first_point[0] - layer2center_point[0]
        diff_y = layer3first_point[1] - layer2center_point[1]

        # Add that difference to layer3second to get layer4
        layer4_x = layer3second_point[0] + diff_x
        layer4_y = layer3second_point[1] + diff_y

        all_points.append([layer4_x, layer4_y])

    # Explicit color assignment for all 30 vertices
    vertex_colors = [
        # Layer 1: Inner pentagon (0-4)
        "indigo",  # 0: North
        "forest_green",  # 1: Northeast
        "gold",  # 2: Southeast
        "royal_blue",  # 3: Southwest
        "forest_green",  # 4: Northwest
        # Layer 2 vertex: Outer pentagon (5-9)
        "dark_cyan",  # 5: North outer (was turquoise, now teal)
        "light_pink",  # 6: Northeast outer (East)
        "light_steel_blue",  # 7: Southeast outer (South)
        "light_steel_blue",  # 8: Southwest outer (West)
        "light_pink",  # 9: Northwest outer
        # Layer 2 center: Star/edge centers (10-14)
        "maroon",  # 10: North star (edge 0->1)
        "crimson",  # 11: Northeast star (edge 1->2)
        "dark_orange",  # 12: Southeast star (edge 2->3)
        "crimson",  # 13: Southwest star (edge 3->4)
        "tan",  # 14: Northwest star (edge 4->0)
        # Layer 3 first: First extensions (15-19) - from next vertex through star
        "white",  # 15: Direction 1 (star 10) - white
        "turquoise",  # 16: Direction 2 (star 11) - turquoise (was teal)
        "lime_green",  # 17: Direction 3 (star 12) - limegreen
        "chartreuse",  # 18: Direction 4 (star 13) - electriclime
        "sky_blue",  # 19: Direction 5 (star 14) - skyblue
        # Layer 3 second: Second extensions (20-24) - from current vertex through star
        "sky_blue",  # 20: Direction 1 (star 10) - skyblue
        "chartreuse",  # 21: Direction 2 (star 11) - electriclime
        "magenta",  # 22: Direction 3 (star 12) - magenta
        "turquoise",  # 23: Direction 4 (star 13) - turquoise (was teal)
        "white",  # 24: Direction 5 (star 14) - white
        # Layer 4: Outer triangle points (25-29)
        "goldenrod",  # 25: Direction 1 - goldenrod
        "silver",  # 26: Direction 2 - silver
        "navy",  # 27: Direction 3 - deep blue
        "silver",  # 28: Direction 4 - silver
        "goldenrod",  # 29: Direction 5 - goldenrod
    ]

    # Create colored points
    colored_points = []
    for i, point in enumerate(all_points):
        colored_points.append([point[0], point[1], vertex_colors[i]])

    # Create triangles using 6-triangle loop pattern with 5 series
    triangles = []

    # Generate triangles for each of the 5 directions as separate series
    for i in range(5):
        # Get vertices for current direction i and next direction (i+1)
        layer1_curr = layer1_start + i
        layer1_next = layer1_start + (i + 1) % 5
        layer2vertex_curr = layer2vertex_start + i
        layer2vertex_next = layer2vertex_start + (i + 1) % 5
        layer2center_curr = layer2center_start + i
        layer3first_curr = layer3first_start + i
        layer3second_curr = layer3second_start + i

        # Create series of 6 triangles for this direction
        direction_triangles = []

        # Triangle 1: layer2center - layer3first - layer2vertex_curr
        direction_triangles.append(
            [layer2center_curr, layer3first_curr, layer2vertex_curr]
        )

        # Triangle 2: layer2center - layer2vertex_curr - layer1_curr
        direction_triangles.append([layer2center_curr, layer2vertex_curr, layer1_curr])

        # Triangle 3: layer2center - layer1_curr - layer1_next
        direction_triangles.append([layer2center_curr, layer1_curr, layer1_next])

        # Triangle 4: layer2center - layer1_next - layer2vertex_next
        direction_triangles.append([layer2center_curr, layer1_next, layer2vertex_next])

        # Triangle 5: layer2center - layer2vertex_next - layer3second_curr
        direction_triangles.append(
            [layer2center_curr, layer2vertex_next, layer3second_curr]
        )

        # Triangle 6: layer2center - layer3second_curr - layer3first_curr
        direction_triangles.append(
            [layer2center_curr, layer3second_curr, layer3first_curr]
        )

        # Triangle 7: layer4 - layer3first - layer3second (new outer triangle)
        layer4_curr = layer4_start + i
        direction_triangles.append([layer4_curr, layer3first_curr, layer3second_curr])

        # Add this series to the triangles array
        triangles.append(direction_triangles)

    # No explicit lines - triangles will automatically draw their edges
    lines = []

    # Create color definitions (using 3A-33 colors)
    colors = {
        # Colors used in 5A-35 (mapped from 3A-33)
        "indigo": "#5B0082",
        "forest_green": "#228B22",
        "gold": "#FFD700",
        "royal_blue": "#4169E1",
        "turquoise": "#00CED1",
        "maroon": "#800000",
        "light_pink": "#FFB6C1",
        "crimson": "#DC143C",
        "light_steel_blue": "#CCCCFF",
        "dark_orange": "#FF8C00",
        "tan": "#D2B48C",
        # Additional colors for extension points
        "chartreuse": "#CCFF00",
        "white": "#FFFFFF",
        "silver": "#C0C0C0",
        "sky_blue": "#87CEEB",
        "lime_green": "#32CD32",
        "goldenrod": "#DAA520",
        "magenta": "#FF00FF",
        "dark_cyan": "#008B8B",
        "dark_grey": "#2F2F2F",
        "pale_green": "#F0FFF0",
        "navy": "#000080",
    }

    # Create the complete configuration
    config = {
        "colors": colors,
        "geometry": {
            "points": colored_points,
            "triangles": triangles,  # Five series of triangles (6 triangles each)
            "apex": apex,
            "lines": lines,
        },
        "rendering": {
            "svg": {
                "width": "100%",
                "height": "400",
                "viewBox": "-170 -150 340 330",  # Fits all vertices with padding
            }
        },
    }

    # Write to JSON file in same directory as script
    script_dir = Path(__file__).parent
    output_file = script_dir / "5A-35.json"

    with open(output_file, "w") as f:
        json.dump(config, f, indent=2)

    print(f"Generated {output_file}")
    print(f"Inner pentagon circumradius: {circumradius:.3f}")
    print(f"Outer pentagon circumradius: {outer_radius:.3f}")
    print(f"Layer 1 (inner pentagon): 5 vertices")
    print(f"Layer 2 vertex (outer pentagon): 5 vertices")
    print(f"Layer 2 center (star/edge centers): 5 vertices")
    print(f"Layer 3 first (extensions): 5 vertices")
    print(f"Layer 3 second (extensions): 5 vertices")
    print(f"Layer 4 (outer triangles): 5 vertices")
    print(f"Total points: {len(colored_points)}")
    total_triangles = sum(len(series) for series in triangles)
    print(f"Triangle series: {len(triangles)} (7 triangles each)")
    print(f"Total triangles: {total_triangles}")
    print(f"Geometric lines: {len(lines)}")


if __name__ == "__main__":
    main()

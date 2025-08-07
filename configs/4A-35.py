#!/usr/bin/env python3
"""
Generate 4A-35.json configuration for a pentagon star pattern.

Creates a regular pentagon centered at (0,0) with equilateral triangles
extending from each edge to form a 5-pointed star pattern.
"""

import json
import math
from pathlib import Path


def main():
    """Generate 4A-35.json configuration."""

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
    layer3first_start = 15  # First extension points (4 points, skip direction 2)
    layer3second_start = 19  # Second extension points (4 points, skip direction 2)
    layer4second_start = 23  # Outer triangle second points (4 points, skip direction 2)
    layer4first_start = 27  # Outer triangle first points (1 point, only direction 1)
    layer5second_start = 28  # Layer 5 second points (1 point, only direction 1)
    layer4third_start = 29  # Layer 4 third points (1 point, only direction 3)
    layer5third_start = 30  # Layer 5 third points (1 point, only direction 3)

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
        if i == 2:  # Skip direction 2 for layer 3 first
            continue
        # Layer 3 first: First extension point (from next vertex through star)
        star_point = all_points[layer2center_start + i]
        inner_vertex = all_points[layer1_start + (i + 1) % 5]

        vec_x = star_point[0] - inner_vertex[0]
        vec_y = star_point[1] - inner_vertex[1]
        ext_x = star_point[0] + vec_x
        ext_y = star_point[1] + vec_y
        all_points.append([ext_x, ext_y])

    for i in range(5):
        if i == 2:  # Skip direction 2 for layer 3 second
            continue
        # Layer 3 second: Second extension point (from current vertex through star)
        star_point = all_points[layer2center_start + i]
        inner_vertex = all_points[layer1_start + i]

        vec_x = star_point[0] - inner_vertex[0]
        vec_y = star_point[1] - inner_vertex[1]
        ext_x = star_point[0] + vec_x
        ext_y = star_point[1] + vec_y
        all_points.append([ext_x, ext_y])

    for i in range(5):
        if i == 2:  # Skip direction 2 for layer 4
            continue
        # Layer 4 second: Outer triangle second point using shortcut method
        # Need to adjust indices since we skipped direction 2 in previous layers
        layer3first_idx = layer3first_start + (i if i < 2 else i - 1)
        layer3second_idx = layer3second_start + (i if i < 2 else i - 1)
        
        layer2center_point = all_points[layer2center_start + i]
        layer3first_point = all_points[layer3first_idx]
        layer3second_point = all_points[layer3second_idx]

        # Vector from layer2center to layer3first
        diff_x = layer3first_point[0] - layer2center_point[0]
        diff_y = layer3first_point[1] - layer2center_point[1]

        # Add that difference to layer3second to get layer4second
        layer4second_x = layer3second_point[0] + diff_x
        layer4second_y = layer3second_point[1] + diff_y

        all_points.append([layer4second_x, layer4second_y])

    for i in range(5):
        if i != 1:  # Only create layer4first for direction 1
            continue
        # Layer 4 first: Create equilateral triangle with layer3first and layer4second
        # Formula: layer3second - layer3first + layer4second
        # Need to adjust indices since we skipped direction 2 in previous layers
        layer3first_idx = layer3first_start + (i if i < 2 else i - 1)
        layer3second_idx = layer3second_start + (i if i < 2 else i - 1)
        layer4second_idx = layer4second_start + (i if i < 2 else i - 1)
        
        layer3first_point = all_points[layer3first_idx]
        layer3second_point = all_points[layer3second_idx]
        layer4second_point = all_points[layer4second_idx]

        # Calculate layer4first using the formula: layer3first - layer3second + layer4second
        layer4first_x = layer3first_point[0] - layer3second_point[0] + layer4second_point[0]
        layer4first_y = layer3first_point[1] - layer3second_point[1] + layer4second_point[1]

        all_points.append([layer4first_x, layer4first_y])

    for i in range(5):
        if i != 1:  # Only create layer5second for direction 1
            continue
        # Layer 5 second: Create layer5 using formula layer4second + (layer4first - layer3first)
        # Need to adjust indices since we skipped direction 2 in previous layers
        layer3first_idx = layer3first_start + (i if i < 2 else i - 1)
        layer4second_idx = layer4second_start + (i if i < 2 else i - 1)
        layer4first_idx = layer4first_start  # Index 27 for direction 1
        
        layer3first_point = all_points[layer3first_idx]
        layer4second_point = all_points[layer4second_idx]
        layer4first_point = all_points[layer4first_idx]

        # Calculate layer5second using the formula: layer4second + (layer4first - layer3first)
        layer5second_x = layer4second_point[0] + (layer4first_point[0] - layer3first_point[0])
        layer5second_y = layer4second_point[1] + (layer4first_point[1] - layer3first_point[1])

        all_points.append([layer5second_x, layer5second_y])

    for i in range(5):
        if i != 3:  # Only create layer4third for direction 3
            continue
        # Layer 4 third: Create using formula layer3second - layer3first + layer4second
        # Need to adjust indices since we skipped direction 2 in previous layers
        layer3first_idx = layer3first_start + (i if i < 2 else i - 1)
        layer3second_idx = layer3second_start + (i if i < 2 else i - 1)
        layer4second_idx = layer4second_start + (i if i < 2 else i - 1)
        
        layer3first_point = all_points[layer3first_idx]
        layer3second_point = all_points[layer3second_idx]
        layer4second_point = all_points[layer4second_idx]

        # Calculate layer4third using the formula: layer3second - layer3first + layer4second
        layer4third_x = layer3second_point[0] - layer3first_point[0] + layer4second_point[0]
        layer4third_y = layer3second_point[1] - layer3first_point[1] + layer4second_point[1]

        all_points.append([layer4third_x, layer4third_y])

    for i in range(5):
        if i != 3:  # Only create layer5third for direction 3
            continue
        # Layer 5 third: Create using formula (layer4second - layer3second) + layer4third
        # Need to adjust indices since we skipped direction 2 in previous layers
        layer3second_idx = layer3second_start + (i if i < 2 else i - 1)
        layer4second_idx = layer4second_start + (i if i < 2 else i - 1)
        layer4third_idx = layer4third_start  # Index 29 for direction 3
        
        layer3second_point = all_points[layer3second_idx]
        layer4second_point = all_points[layer4second_idx]
        layer4third_point = all_points[layer4third_idx]

        # Calculate layer5third using the formula: (layer4second - layer3second) + layer4third
        layer5third_x = (layer4second_point[0] - layer3second_point[0]) + layer4third_point[0]
        layer5third_y = (layer4second_point[1] - layer3second_point[1]) + layer4third_point[1]

        all_points.append([layer5third_x, layer5third_y])

    # Explicit color assignment for all 31 vertices
    vertex_colors = [
        # Layer 1: Inner pentagon (0-4)
        "indigo",  # 0: North
        "forest_green",  # 1: Northeast
        "gold",  # 2: Southeast
        "royal_blue",  # 3: Southwest
        "forest_green",  # 4: Northwest
        # Layer 2 vertex: Outer pentagon (5-9)
        "dark_cyan",  # 5: North outer
        "light_pink",  # 6: Northeast outer
        "light_steel_blue",  # 7: Southeast outer
        "light_steel_blue",  # 8: Southwest outer
        "light_pink",  # 9: Northwest outer
        # Layer 2 center: Star/edge centers (10-14)
        "maroon",  # 10: North star
        "crimson",  # 11: Northeast star
        "dark_orange",  # 12: Southeast star
        "crimson",  # 13: Southwest star
        "tan",  # 14: Northwest star
        # Layer 3 first: First extensions (15-18) - 4 vertices, skip direction 2
        "white",  # 15: Direction 0
        "turquoise",  # 16: Direction 1
        "chartreuse",  # 17: Direction 3 (direction 2 skipped)
        "sky_blue",  # 18: Direction 4
        # Layer 3 second: Second extensions (19-22) - 4 vertices, skip direction 2
        "sky_blue",  # 19: Direction 0
        "chartreuse",  # 20: Direction 1
        "turquoise",  # 21: Direction 3 (direction 2 skipped)
        "white",  # 22: Direction 4
        # Layer 4 second: Outer triangle second points (23-26) - 4 vertices, skip direction 2
        "goldenrod",  # 23: Direction 0
        "magenta",  # 24: Direction 1
        "magenta",  # 25: Direction 3 (direction 2 skipped)
        "goldenrod",  # 26: Direction 4
        # Layer 4 first: Outer triangle first points (27) - 1 vertex, only direction 1
        "navy",  # 27: Direction 1
        # Layer 5 second: Layer 5 second points (28) - 1 vertex, only direction 1
        "silver",  # 28: Direction 1
        # Layer 4 third: Layer 4 third points (29) - 1 vertex, only direction 3
        "navy",  # 29: Direction 3
        # Layer 5 third: Layer 5 third points (30) - 1 vertex, only direction 3
        "silver",  # 30: Direction 3
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
        
        # Skip direction 2 completely for triangles that use layer 3 or 4 vertices
        if i == 2:
            # For direction 2, only create triangles that don't use layer 3 or 4
            direction_triangles = []
            # Triangle 2: layer2center - layer2vertex_curr - layer1_curr
            direction_triangles.append([layer2center_curr, layer2vertex_curr, layer1_curr])
            # Triangle 3: layer2center - layer1_curr - layer1_next
            direction_triangles.append([layer2center_curr, layer1_curr, layer1_next])
            # Triangle 4: layer2center - layer1_next - layer2vertex_next
            direction_triangles.append([layer2center_curr, layer1_next, layer2vertex_next])
            # Add this reduced series to the triangles array
            triangles.append(direction_triangles)
            continue
        
        # For other directions, adjust indexing for layer 3 and 4 vertices
        # Since we skipped direction 2, directions 3+ need adjusted indices
        layer3first_idx = layer3first_start + (i if i < 2 else i - 1)
        layer3second_idx = layer3second_start + (i if i < 2 else i - 1)
        layer4second_idx = layer4second_start + (i if i < 2 else i - 1)
        layer4first_idx = layer4first_start  # Only direction 1 has layer4first, so always index 27

        # Create series of triangles for this direction (7 base + 1 extra for direction 1)
        direction_triangles = []

        # Triangle 1: layer2center - layer3first - layer2vertex_curr
        direction_triangles.append(
            [layer2center_curr, layer3first_idx, layer2vertex_curr]
        )

        # Triangle 2: layer2center - layer2vertex_curr - layer1_curr
        direction_triangles.append([layer2center_curr, layer2vertex_curr, layer1_curr])

        # Triangle 3: layer2center - layer1_curr - layer1_next
        direction_triangles.append([layer2center_curr, layer1_curr, layer1_next])

        # Triangle 4: layer2center - layer1_next - layer2vertex_next
        direction_triangles.append([layer2center_curr, layer1_next, layer2vertex_next])

        # Triangle 5: layer2center - layer2vertex_next - layer3second_curr
        direction_triangles.append(
            [layer2center_curr, layer2vertex_next, layer3second_idx]
        )

        # Triangle 6: layer2center - layer3second_curr - layer3first_curr
        direction_triangles.append(
            [layer2center_curr, layer3second_idx, layer3first_idx]
        )

        # Triangle 7: layer4second - layer3first - layer3second (original outer triangle)
        direction_triangles.append([layer4second_idx, layer3first_idx, layer3second_idx])
        
        # Triangle 8: layer3first - layer4first - layer4second (connection triangle, for direction 1 only)
        if i == 1:
            layer4first_idx = layer4first_start  # Index 27 for direction 1
            direction_triangles.append([layer3first_idx, layer4first_idx, layer4second_idx])
            # Triangle 9: layer4first - layer4second - layer5second (new outer triangle, direction 1)
            layer5second_idx = layer5second_start  # Index 28 for direction 1
            direction_triangles.append([layer4first_idx, layer4second_idx, layer5second_idx])
        elif i == 3:
            layer4third_idx = layer4third_start  # Index 29 for direction 3
            # Triangle 8: layer3second - layer4second - layer4third (connection triangle, direction 3)
            direction_triangles.append([layer3second_idx, layer4second_idx, layer4third_idx])
            # Triangle 9: layer4second - layer4third - layer5third (new outer triangle, direction 3)
            layer5third_idx = layer5third_start  # Index 30 for direction 3
            direction_triangles.append([layer4second_idx, layer4third_idx, layer5third_idx])

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
            "triangles": triangles,  # Five series of triangles (3 for dir 2, 9 for dirs 1&3, 7 for others)
            "apex": apex,
            "lines": lines,
        },
        "rendering": {
            "svg": {
                "width": "100%",
                "height": "400",
                "viewBox": "-220 -150 440 240",  # Fits all vertices with padding
            }
        },
    }

    # Write to JSON file in same directory as script
    script_dir = Path(__file__).parent
    output_file = script_dir / "4A-35.json"

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
    print(f"Triangle series: {len(triangles)} (3 for direction 2, 9 for directions 1&3, 7 for others)")
    print(f"Total triangles: {total_triangles}")
    print(f"Geometric lines: {len(lines)}")


if __name__ == "__main__":
    main()
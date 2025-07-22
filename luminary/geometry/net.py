"""Net class for creating pentagon patterns from JSON configuration."""

from typing import List, Dict, Optional, Tuple
from pathlib import Path
import json

from ..config.schema import NetConfiguration, JSONLoader
from ..writers.svg.svg_exportable import SVGExportable
from ..writers.svg.utilities import (
    create_svg_header,
    create_line_svg,
    create_circle_svg,
)
from .point import Point
from .triangle import Triangle


class Net(SVGExportable):
    """Pentagon pattern net that creates triangles and kites from JSON configuration."""

    def __init__(self, config: NetConfiguration):
        """Initialize Net from validated configuration."""
        self.config = config
        self.points = self._create_points()
        self.apex = Point(
            self.config.geometry.apex[0],
            self.config.geometry.apex[1],
            "white",  # Default apex color
        )
        self.triangles = self._create_triangles()

    @classmethod
    def from_json_file(cls, file_path: Path) -> "Net":
        """Load Net from JSON configuration file."""
        config = JSONLoader.load_config(file_path)
        return cls(config)

    @classmethod
    def from_json_string(cls, json_str: str) -> "Net":
        """Load Net from JSON string."""
        data = json.loads(json_str)
        config = NetConfiguration(**data)
        return cls(config)

    def _create_points(self) -> List[Point]:
        """Create Point objects from configuration tuples."""
        points = []
        for x, y, color_name in self.config.geometry.points:
            # Look up the actual color value from the color definitions
            color_hex = str(self.config.colors[color_name])
            points.append(Point(x, y, color_hex))
        return points

    def _create_triangles(self) -> List[Triangle]:
        """Create Triangle objects from configuration."""
        triangles = []

        for (
            triangle_id,
            triangle_tuple,
            series_num,
        ) in self.config.iter_triangles_with_ids():
            # Get the three vertex points
            v1_idx, v2_idx, v3_idx = triangle_tuple
            v1 = self.points[v1_idx]
            v2 = self.points[v2_idx]
            v3 = self.points[v3_idx]

            # Create triangle with calculated ID
            triangle = Triangle(v1, v2, v3, triangle_id, self.apex)
            triangles.append(triangle)

        return triangles

    def _render_geometric_lines(self) -> str:
        """Render structural geometric lines."""
        svg_content = ""
        line_width = self.config.rendering.styles.line_width

        for from_idx, to_idx in self.config.geometry.lines:
            from_point = self.points[from_idx]
            to_point = self.points[to_idx]

            svg_content += (
                create_line_svg(
                    from_point, to_point, stroke_color="black", stroke_width=line_width
                )
                + "\n"
            )

        return svg_content

    def _render_vertex_circles(self) -> str:
        """Render vertex circles."""
        svg_content = ""
        # Fix circle sizing: half radius and stroke-width 2
        radius = self.config.rendering.styles.vertex_circle_radius / 2
        stroke_width = 2  # Fixed stroke width

        for point in self.points:
            svg_content += (
                create_circle_svg(
                    center=point,
                    radius=radius,
                    fill=point.color or "black",
                    stroke="black",
                    stroke_width=stroke_width,
                )
                + "\n"
            )

        return svg_content

    def get_svg(self) -> List[str]:
        """Generate complete SVG representation of the Net."""
        svg_config = self.config.rendering.svg
        style_config = self.config.rendering.styles

        # Start SVG
        svg_content = (
            create_svg_header(
                viewbox=svg_config.viewBox,
                width=svg_config.width,
                height=svg_config.height,
            )
            + "\n"
        )

        # Render triangles (with fill opacity)
        for triangle in self.triangles:
            triangle_elements = triangle.get_svg()
            for element in triangle_elements:
                element_svg = element.replace(
                    'fill-opacity="0.4"',
                    f'fill-opacity="{style_config.triangle_fill_opacity}"',
                )
                svg_content += element_svg + "\n"

        # Render all kites (with fill opacity)
        for triangle in self.triangles:
            for kite in triangle.kites:
                kite_elements = kite.get_svg()
                for element in kite_elements:
                    element_svg = element.replace(
                        'fill-opacity="0.6"',
                        f'fill-opacity="{style_config.kite_fill_opacity}"',
                    )
                    svg_content += element_svg + "\n"

        # Render triangle edge lines - AFTER all kites, on top
        for triangle in self.triangles:
            edge_lines = triangle.get_edge_lines_svg()
            for line in edge_lines:
                svg_content += line + "\n"

        # Render geometric lines (standalone lines)
        svg_content += self._render_geometric_lines()

        # Render vertex circles (standalone vertices)
        svg_content += self._render_vertex_circles()

        # End SVG
        svg_content += "</svg>"

        return [svg_content]

    def save_svg(self, output_path: Path) -> None:
        """Save SVG to file."""
        svg_elements = self.get_svg()
        svg_content = "".join(svg_elements)
        output_path.write_text(svg_content)

    def get_stats(self) -> Dict[str, int]:
        """Get statistics about the Net."""
        total_kites = sum(len(triangle.kites) for triangle in self.triangles)
        return {
            "points": len(self.points),
            "triangles": len(self.triangles),
            "kites": total_kites,
            "geometric_lines": len(self.config.geometry.lines),
            "series": len(self.config.geometry.triangles),
        }

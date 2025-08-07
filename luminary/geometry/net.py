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
    create_polygon_svg,
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
            color_value = self.config.colors.get(color_name)
            if not color_value:
                raise ValueError(
                    f"Color '{color_name}' not found in configuration colors or is empty"
                )

            # color_value is now a string (hex or OKLCH), validate it with our Color class
            if not color_value or color_value.lower() in ("none", "null", ""):
                raise ValueError(
                    f"Invalid color value for '{color_name}': '{color_value}'"
                )

            # Validate the color string and get the hex representation
            from luminary.color import Color

            try:
                color_obj = Color.from_string(color_value)
                color_hex = color_obj.to_hex()
            except ValueError as e:
                raise ValueError(
                    f"Invalid color format for '{color_name}': '{color_value}' - {e}"
                )

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
            # Get beam counts from configuration
            beam_counts_list = self.config.geometry.default_beam_counts
            beam_counts_tuple = tuple(beam_counts_list)

            triangle = Triangle(v1, v2, v3, triangle_id, self.apex, beam_counts_tuple)
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

    def get_svg(self, extended: bool = False, show_vertices: bool = False, beam_colors: dict = None) -> List[str]:
        """Generate complete SVG representation of the Net.

        Args:
            extended: If True, render individual beam subdivisions instead of facets
            show_vertices: If True, draw circles for triangle vertices (incenters always shown)
            beam_colors: Optional dictionary mapping beam_id to Color objects for pattern rendering
        """
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

        if extended:
            # Render individual beams instead of facets
            for triangle in self.triangles:
                for facet in triangle.facets:
                    beam_groups = facet.get_beams()
                    for edge_beams in beam_groups:
                        for beam in edge_beams:
                            beam_elements = beam.get_svg(facet.color, beam_colors)
                            for element in beam_elements:
                                svg_content += element + "\n"
            
            # Render facet edge lines on top of beams for geometric structure
            from ..writers.svg.utilities import create_line_svg
            for triangle in self.triangles:
                for facet in triangle.facets:
                    vertices = facet.get_vertices()
                    for i in range(len(vertices)):
                        start_vertex = vertices[i]
                        end_vertex = vertices[(i + 1) % len(vertices)]
                        
                        line_svg = create_line_svg(
                            start_vertex, end_vertex,
                            stroke_color="black",
                            stroke_width=0.5
                        )
                        svg_content += line_svg + "\n"
        else:
            # Render all facets (with fill opacity)
            for triangle in self.triangles:
                for facet in triangle.facets:
                    facet_elements = facet.get_svg()
                    for element in facet_elements:
                        element_svg = element.replace(
                            'fill-opacity="0.6"',
                            f'fill-opacity="{style_config.facet_fill_opacity}"',
                        )
                        svg_content += element_svg + "\n"

        # Render triangle edge lines - AFTER all facets, on top
        for triangle in self.triangles:
            edge_lines = triangle.get_edge_lines_svg()
            for line in edge_lines:
                svg_content += line + "\n"

        # Render geometric lines (standalone lines)
        svg_content += self._render_geometric_lines()

        # Render vertex circles (standalone vertices) - only if requested
        if show_vertices:
            svg_content += self._render_vertex_circles()

        # End SVG
        svg_content += "</svg>"

        return [svg_content]

    def save_svg(
        self, output_path: Path, extended: bool = False, show_vertices: bool = False, beam_colors: dict = None
    ) -> None:
        """Save SVG to file.

        Args:
            output_path: Path to write SVG file
            extended: If True, render individual beam subdivisions
            show_vertices: If True, draw circles for triangle vertices
            beam_colors: Optional dictionary mapping beam_id to Color objects for pattern rendering
        """
        svg_elements = self.get_svg(extended=extended, show_vertices=show_vertices, beam_colors=beam_colors)
        svg_content = "".join(svg_elements)
        output_path.write_text(svg_content)

    def get_stats(self) -> Dict[str, int]:
        """Get statistics about the Net."""
        total_facets = sum(len(triangle.facets) for triangle in self.triangles)
        return {
            "points": len(self.points),
            "triangles": len(self.triangles),
            "facets": total_facets,
            "geometric_lines": len(self.config.geometry.lines),
            "series": len(self.config.geometry.triangles),
        }

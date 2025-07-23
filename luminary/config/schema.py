"""Pydantic models for JSON configuration schema."""

from pydantic import BaseModel, Field, field_validator, model_validator
# Using string-based colors instead of pydantic.color.Color
from typing import List, Dict, Optional, Tuple
from typing_extensions import TypeAlias
from pathlib import Path
from enum import Enum


# Point as tuple: (x, y, color)
PointTuple: TypeAlias = Tuple[float, float, str]


# Triangle as tuple: (vertex1, vertex2, vertex3)
TriangleTuple: TypeAlias = Tuple[int, int, int]


# Apex as tuple: (x, y)
ApexTuple: TypeAlias = Tuple[float, float]


# Use tuple for geometric lines - much more compact
GeometricLine: TypeAlias = Tuple[int, int]


class SVGConfig(BaseModel):
    """SVG rendering configuration."""

    width: str = Field(..., pattern=r"^(\d+%|\d+px|\d+)$", description="SVG width")
    height: str = Field(..., pattern=r"^(\d+%|\d+px|\d+)$", description="SVG height")
    viewBox: str = Field(..., description="SVG viewBox coordinates")

    @field_validator("viewBox")
    def validate_viewbox(cls, v):
        parts = v.split()
        if len(parts) != 4:
            raise ValueError("ViewBox must have 4 space-separated values")
        try:
            [float(p) for p in parts]
        except ValueError:
            raise ValueError("ViewBox values must be numeric")
        return v


class StyleConfig(BaseModel):
    """Rendering style configuration."""

    triangle_fill_opacity: float = Field(default=0.4, ge=0.0, le=1.0)
    facet_fill_opacity: float = Field(
        default=0.6, ge=0.0, le=1.0
    )  # Renamed from kite_fill_opacity
    text_opacity: float = Field(default=0.7, ge=0.0, le=1.0)
    line_width: float = Field(default=2.0, gt=0.0)
    vertex_circle_radius: float = Field(default=8.0, gt=0.0)
    vertex_circle_stroke_width: float = Field(default=4.0, gt=0.0)


class RenderingConfig(BaseModel):
    """Complete rendering configuration."""

    svg: SVGConfig = Field(
        ..., description="SVG-specific settings"
    )  # Only SVG config is required
    styles: StyleConfig = Field(
        default_factory=StyleConfig, description="Visual styling"
    )


class GeometryConfig(BaseModel):
    """Geometric data configuration."""

    points: List[PointTuple] = Field(
        ..., min_length=3, description="Points as (x, y, color) tuples"
    )
    triangles: List[List[TriangleTuple]] = Field(
        ..., min_length=1, description="Triangle series as nested arrays"
    )
    apex: ApexTuple = Field(..., description="Apex point as (x, y) tuple")
    lines: List[GeometricLine] = Field(
        default_factory=list, description="Structural lines as [from, to] tuples"
    )
    default_beam_counts: List[int] = Field(
        default=[7, 4, 4, 7],
        min_length=4,
        max_length=4,
        description="Default beam counts per facet edge [major_starboard, minor_starboard, minor_port, major_port]",
    )

    @model_validator(mode="after")
    def validate_triangle_indices(self):
        """Ensure all triangle vertex indices reference valid points."""
        max_index = len(self.points) - 1

        for series_idx, series in enumerate(self.triangles):
            for tri_idx, triangle in enumerate(series):
                for vertex_idx in triangle:
                    if vertex_idx > max_index:
                        raise ValueError(
                            f"Series {series_idx+1} triangle {tri_idx} references invalid point index: {vertex_idx}"
                        )
        return self


class NetConfiguration(BaseModel):
    """Complete configuration schema for Net class."""

    colors: Dict[str, str] = Field(..., description="Named color definitions (hex or OKLCH strings)")
    geometry: GeometryConfig = Field(..., description="Geometric definitions")
    rendering: RenderingConfig = Field(
        default_factory=lambda: RenderingConfig(
            svg=SVGConfig(width="100%", height="400", viewBox="-450 -100 1100 370")
        ),
        description="Rendering configuration",
    )

    @model_validator(mode="after")
    def validate_color_references(self):
        """Ensure all point colors reference defined colors."""
        for x, y, color in self.geometry.points:
            if color not in self.colors:
                raise ValueError(
                    f"Point ({x}, {y}) references undefined color: {color}"
                )
        return self

    @model_validator(mode="after")
    def validate_geometric_line_indices(self):
        """Ensure all geometric line indices reference valid points."""
        max_index = len(self.geometry.points) - 1

        # Validate geometric line indices
        for line in self.geometry.lines:
            for point_idx in line:  # line is now a tuple (from, to)
                if point_idx > max_index:
                    raise ValueError(
                        f"Geometric line references invalid point index: {point_idx}"
                    )

        return self

    def get_triangle_id(self, series_idx: int, triangle_idx: int) -> int:
        """Calculate triangle ID from series and triangle indices (1-based series)."""
        return ((series_idx + 1) * 10) + triangle_idx

    def iter_triangles_with_ids(self):
        """Iterate over all triangles with their calculated IDs."""
        for series_idx, series in enumerate(self.geometry.triangles):
            for triangle_idx, triangle in enumerate(series):
                triangle_id = self.get_triangle_id(series_idx, triangle_idx)
                yield triangle_id, triangle, series_idx + 1  # 1-based series

    @classmethod
    def from_file(cls, path: Path) -> "NetConfiguration":
        """Load and validate configuration from JSON file."""
        return cls.parse_file(path)

    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "colors": {"turquoise": "#00CED1", "indigo": "#5B0082"},
                "geometry": {
                    "points": [
                        {"x": 100.0, "y": -80.7, "color": "turquoise"},
                        {"x": 100.0, "y": 20.0, "color": "indigo"},
                    ],
                    "triangles": [{"id": 10, "vertices": [0, 1, 2], "series": 0}],
                    "apex": {"x": 100.0, "y": 100.0},
                    "geometric_lines": [{"from": 0, "to": 1, "style": "structure"}],
                },
                "rendering": {
                    "svg": {
                        "width": "100%",
                        "height": "400",
                        "viewBox": "-450 -100 1100 370",
                    },
                    "styles": {"triangle_fill_opacity": 0.4, "facet_fill_opacity": 0.6},
                },
            }
        }


class JSONLoader:
    """Utility for loading and validating JSON configurations."""

    @staticmethod
    def load_config(file_path: Path) -> NetConfiguration:
        """Load and validate JSON configuration with helpful error messages."""
        try:
            return NetConfiguration.from_file(file_path)
        except Exception as e:
            raise ValueError(
                f"Failed to load configuration from {file_path}: {e}"
            ) from e

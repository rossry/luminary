"""Color handling with internal OKLCH representation for perceptual uniformity."""

import numpy as np
import colour
from typing import Union, Tuple


class Color:
    """Color representation with perceptually uniform manipulation capabilities.

    Internally uses OKLCH color space for accurate color adjustments.
    Provides multiple construction methods and output formats.
    """

    def __init__(self, l: float, c: float, h: float):
        """Initialize Color from OKLCH components (internal constructor).

        Args:
            l: Lightness (0.0 to 1.0+)
            c: Chroma (0.0 to ~0.4+)
            h: Hue in degrees (0-360)
        """
        self._l = l
        self._c = c
        self._h = h

    @classmethod
    def from_hex(cls, hex_color: str) -> "Color":
        """Create Color from hex string.

        Args:
            hex_color: Hex color like "#FF0000" or "#ff0000"

        Returns:
            Color instance
        """
        if not hex_color:
            raise ValueError("Empty hex color string provided")

        # Remove # if present
        color = hex_color.lstrip("#")

        # Validate and normalize hex string length
        if len(color) == 3:
            # Expand 3-char hex to 6-char (e.g., "ccf" -> "ccccff")
            color = "".join([c * 2 for c in color])
        elif len(color) != 6:
            raise ValueError(
                f"Invalid hex color format: '{hex_color}' (must be 3 or 6 characters after removing #)"
            )

        # Validate hex characters
        try:
            # Convert hex to RGB (0-1 range)
            r = int(color[0:2], 16) / 255.0
            g = int(color[2:4], 16) / 255.0
            b = int(color[4:6], 16) / 255.0
        except ValueError as e:
            raise ValueError(f"Invalid hex color format: '{hex_color}' - {str(e)}")

        rgb = np.array([r, g, b])
        return cls._from_rgb_array(rgb)

    @classmethod
    def from_named_color(cls, color_name: str) -> "Color":
        """Create Color from named color.

        Args:
            color_name: Named color like "red", "blue", "darkcyan"

        Returns:
            Color instance
        """
        # Common named colors to hex mapping
        named_colors = {
            "white": "#FFFFFF",
            "black": "#000000",
            "red": "#FF0000",
            "green": "#008000",
            "blue": "#0000FF",
            "yellow": "#FFFF00",
            "cyan": "#00FFFF",
            "magenta": "#FF00FF",
            "silver": "#C0C0C0",
            "gray": "#808080",
            "maroon": "#800000",
            "olive": "#808000",
            "lime": "#00FF00",
            "aqua": "#00FFFF",
            "teal": "#008080",
            "navy": "#000080",
            "fuchsia": "#FF00FF",
            "purple": "#800080",
            "orange": "#FFA500",
            "indigo": "#4B0082",
            "darkcyan": "#008B8B",
            "forestgreen": "#228B22",
            "darkgreen": "#006400",
            "darkred": "#8B0000",
            "darkblue": "#00008B",
            "darkmagenta": "#8B008B",
            "turquoise": "#40E0D0",
            "tan": "#D2B48C",
            "lightpink": "#FFB6C1",
            "gold": "#FFD700",
            "darkorange": "#FF8C00",
            "crimson": "#DC143C",
            "chartreuse": "#7FFF00",
            "skyblue": "#87CEEB",
            "limegreen": "#32CD32",
            "goldenrod": "#DAA520",
        }

        # Normalize color name
        normalized = color_name.lower().replace("_", "").replace(" ", "")

        if normalized in named_colors:
            return cls.from_hex(named_colors[normalized])
        else:
            # Fallback to red if unknown
            return cls.from_hex("#FF0000")

    @classmethod
    def from_color_string(cls, color_str: str) -> "Color":
        """Create Color from hex or named color string.

        Args:
            color_str: Either hex like "#FF0000" or named like "red"

        Returns:
            Color instance
        """
        if not color_str:
            raise ValueError("Empty color string provided")

        if color_str.startswith("#"):
            return cls.from_hex(color_str)
        else:
            return cls.from_named_color(color_str)

    @classmethod
    def _from_rgb_array(cls, rgb: np.ndarray) -> "Color":
        """Create Color from RGB numpy array (internal helper).

        Args:
            rgb: RGB values as numpy array (0-1 range)

        Returns:
            Color instance
        """
        # RGB -> XYZ -> Oklab -> OKLCH conversion chain
        xyz = colour.sRGB_to_XYZ(rgb)
        oklab = colour.XYZ_to_Oklab(xyz)
        oklch = colour.Oklab_to_Oklch(oklab)

        return cls(oklch[0], oklch[1], oklch[2])

    def adjust_lightness(self, multiplier: float) -> "Color":
        """Adjust lightness by a multiplier.

        Args:
            multiplier: Lightness multiplier (1.2 = +20%, 0.8 = -20%)

        Returns:
            New Color with adjusted lightness
        """
        new_l = max(0.0, self._l * multiplier)  # Clamp to >= 0
        return Color(new_l, self._c, self._h)

    def to_hex(self) -> str:
        """Convert to hex color string for SVG output.

        Returns:
            Hex color string like "#FF0000"
        """
        # OKLCH -> Oklab -> XYZ -> RGB conversion chain
        oklch = np.array([self._l, self._c, self._h])
        oklab = colour.Oklch_to_Oklab(oklch)
        xyz = colour.Oklab_to_XYZ(oklab)
        rgb = colour.XYZ_to_sRGB(xyz)

        # Clamp RGB to valid range and convert to hex
        rgb_255 = np.clip(rgb * 255, 0, 255).astype(int)
        return f"#{rgb_255[0]:02x}{rgb_255[1]:02x}{rgb_255[2]:02x}"

    def to_oklch_string(self) -> str:
        """Convert to OKLCH CSS string for SVG output.

        Returns:
            OKLCH string like "oklch(0.63 0.26 29.22)"
        """
        return f"oklch({self._l:.3f} {self._c:.3f} {self._h:.2f})"

    def to_svg_str(self) -> str:
        """Convert to SVG-compatible color string.

        Returns:
            OKLCH string for SVG output
        """
        return self.to_oklch_string()

    def get_oklch(self) -> Tuple[float, float, float]:
        """Get OKLCH components.

        Returns:
            Tuple of (lightness, chroma, hue)
        """
        return (self._l, self._c, self._h)

    def get_rgb(self) -> Tuple[float, float, float]:
        """Get RGB components in 0-1 range.

        Returns:
            Tuple of (red, green, blue)
        """
        oklch = np.array([self._l, self._c, self._h])
        oklab = colour.Oklch_to_Oklab(oklch)
        xyz = colour.Oklab_to_XYZ(oklab)
        rgb = colour.XYZ_to_sRGB(xyz)
        return tuple(np.clip(rgb, 0, 1))

    def __str__(self) -> str:
        """String representation."""
        return f"OKLCH({self._l:.3f}, {self._c:.3f}, {self._h:.2f}°)"

    def __repr__(self) -> str:
        """Debug representation."""
        return f"Color(l={self._l:.3f}, c={self._c:.3f}, h={self._h:.2f})"

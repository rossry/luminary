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
    def from_hex_string(cls, hex_color: str) -> "Color":
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
    def from_oklch_string(cls, oklch_str: str) -> "Color":
        """Create Color from OKLCH string.

        Args:
            oklch_str: OKLCH string like "oklch(0.65 0.2 180)" or "oklch(65% 0.2 180deg)"

        Returns:
            Color instance
        """
        import re
        
        if not oklch_str.strip():
            raise ValueError("Empty OKLCH string provided")
        
        # Remove whitespace and validate basic format
        oklch_str = oklch_str.strip()
        if not (oklch_str.startswith("oklch(") and oklch_str.endswith(")")):
            raise ValueError(f"Invalid OKLCH format: '{oklch_str}' (must be 'oklch(L C H)')")
        
        # Extract content between parentheses
        content = oklch_str[6:-1].strip()
        
        # Parse components - handle common formats
        # Split by whitespace and/or commas, filter empty strings
        parts = [p.strip() for p in re.split(r'[\s,]+', content) if p.strip()]
        
        if len(parts) != 3:
            raise ValueError(f"Invalid OKLCH components: '{content}' (expected 3 values: L C H)")
        
        l_str, c_str, h_str = parts
        
        # Parse lightness (handle percentage)
        l_percent = l_str.endswith('%')
        l_val = l_str.rstrip('%')
        
        # Parse hue (handle degree suffix)
        h_val = h_str.rstrip('deg°')
        
        try:
            # Parse lightness (handle percentage)
            l = float(l_val)
            if l_percent:
                l = l / 100.0
            
            # Parse chroma (always decimal)
            c = float(c_str)
            
            # Parse hue
            h = float(h_val)
            
            # Validate ranges
            if l < 0:
                raise ValueError(f"Lightness must be >= 0, got {l}")
            if c < 0:
                raise ValueError(f"Chroma must be >= 0, got {c}")
            
            # Normalize hue to 0-360 range
            h = h % 360
            
            return cls(l, c, h)
            
        except ValueError as e:
            if "could not convert" in str(e):
                raise ValueError(f"Invalid numeric values in OKLCH string: '{oklch_str}'")
            else:
                raise

    @classmethod
    def from_string(cls, color_str: str) -> "Color":
        """Create Color from string - auto-detects format.
        
        Supports:
        - Hex: "#FF0000", "#f00" 
        - OKLCH: "oklch(0.65 0.2 180)", "oklch(65% 0.2 180deg)"
        
        Args:
            color_str: Color string in supported format
            
        Returns:
            Color instance
            
        Raises:
            ValueError: If format not recognized or invalid
        """
        if not color_str:
            raise ValueError("Empty color string provided")
        
        color_str = color_str.strip()
        
        if color_str.startswith("#"):
            return cls.from_hex_string(color_str)
        elif color_str.startswith("oklch(") and color_str.endswith(")"):
            return cls.from_oklch_string(color_str)
        else:
            raise ValueError(f"Unsupported color format: '{color_str}'. Use hex (#FF0000) or OKLCH (oklch(0.65 0.2 180))")

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

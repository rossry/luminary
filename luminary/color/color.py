"""Scalar Color for config parsing and authoring (spec §8.5).

A thin wrapper over the vectorized pipeline in :mod:`luminary.color.convert`,
operating on length-1 arrays. It exists so config files can name colors as
"#RRGGBB" or "oklch(...)" strings; it MUST NOT be used on the per-frame path
(spec §8.5.1) — that is what convert.py's array functions are for.
"""

from __future__ import annotations

import re
from typing import Tuple

import numpy as np

from luminary.color import convert

_OKLCH_RE = re.compile(
    r"oklch\(\s*([0-9.]+%?)\s+([0-9.]+)\s+([0-9.]+)(?:deg)?\s*\)", re.IGNORECASE
)


class Color:
    """A single color, stored as OKLCH (L in [0,1], C >= 0, H degrees [0,360))."""

    def __init__(self, l: float, c: float, h: float) -> None:
        if l < 0 or c < 0:
            raise ValueError(f"Invalid OKLCH values: L={l}, C={c} must be >= 0")
        self._l = float(l)
        self._c = float(c)
        self._h = float(h) % 360.0

    @classmethod
    def from_hex_string(cls, hex_color: str) -> "Color":
        """Parse "#RRGGBB" or "#RGB"."""
        if not hex_color:
            raise ValueError("Empty hex color string provided")
        s = hex_color.strip().lstrip("#")
        if len(s) == 3:
            s = "".join(ch * 2 for ch in s)
        if len(s) != 6:
            raise ValueError(
                f"Invalid hex color {hex_color!r}: must be 3 or 6 characters"
            )
        try:
            rgb8 = np.array(
                [[int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)]], dtype=np.uint8
            )
        except ValueError as exc:
            raise ValueError(f"Invalid hex color format: {hex_color!r}") from exc
        l, c, h = convert.srgb8_to_oklch(rgb8)[0]
        return cls(float(l), float(c), float(h))

    @classmethod
    def from_oklch_string(cls, oklch_str: str) -> "Color":
        """Parse "oklch(0.65 0.2 180)" (also accepts % lightness and deg suffix)."""
        match = _OKLCH_RE.fullmatch(oklch_str.strip())
        if not match:
            raise ValueError(f"Invalid OKLCH color string: {oklch_str!r}")
        l_str, c_str, h_str = match.groups()
        l = float(l_str[:-1]) / 100.0 if l_str.endswith("%") else float(l_str)
        return cls(l, float(c_str), float(h_str))

    @classmethod
    def from_string(cls, color_str: str) -> "Color":
        """Auto-detect hex or oklch() format."""
        if not color_str:
            raise ValueError("Empty color string provided")
        s = color_str.strip()
        if s.startswith("#"):
            return cls.from_hex_string(s)
        if s.lower().startswith("oklch"):
            return cls.from_oklch_string(s)
        raise ValueError(f"Unsupported color format: {color_str!r}")

    def get_oklch(self) -> Tuple[float, float, float]:
        return (self._l, self._c, self._h)

    def get_rgb(self) -> Tuple[float, float, float]:
        """Gamma-encoded sRGB in [0,1], gamut-clipped."""
        rgb8 = convert.oklch_to_srgb8(np.array([[self._l, self._c, self._h]]))
        r, g, b = rgb8[0]
        return (float(r) / 255.0, float(g) / 255.0, float(b) / 255.0)

    def to_hex(self) -> str:
        rgb8 = convert.oklch_to_srgb8(np.array([[self._l, self._c, self._h]]))
        r, g, b = (int(v) for v in rgb8[0])
        return f"#{r:02X}{g:02X}{b:02X}"

    def to_oklch_string(self) -> str:
        return f"oklch({self._l:.3f} {self._c:.3f} {self._h:.2f})"

    def to_svg_str(self) -> str:
        """Preferred SVG color string (browsers support oklch() natively)."""
        return self.to_oklch_string()

    def adjust_lightness(self, multiplier: float) -> "Color":
        """New Color with lightness scaled (clamped to >= 0)."""
        return Color(max(0.0, self._l * multiplier), self._c, self._h)

    def __repr__(self) -> str:
        return f"Color(l={self._l:.3f}, c={self._c:.3f}, h={self._h:.2f})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Color):
            return NotImplemented
        return self.get_oklch() == other.get_oklch()

    def __hash__(self) -> int:
        return hash(self.get_oklch())

"""Tests for Color class with OKLCH roundtripping."""

import pytest
import numpy as np
from luminary.color import Color


class TestColor:
    """Test Color class functionality and roundtripping."""

    def test_hex_roundtrip_primary_colors(self):
        """Test hex color roundtripping for primary colors with OKLCH precision tolerance."""
        test_colors = [
            "#FF0000",  # Red
            "#00FF00",  # Green
            "#0000FF",  # Blue
            "#FFFFFF",  # White
            "#000000",  # Black
            "#808080",  # Gray
            "#FF00FF",  # Magenta
            "#00FFFF",  # Cyan
            "#FFFF00",  # Yellow
        ]

        for hex_color in test_colors:
            color = Color.from_hex_string(hex_color)
            roundtrip = color.to_hex()

            # Parse original and roundtrip RGB values
            orig_r = int(hex_color[1:3], 16)
            orig_g = int(hex_color[3:5], 16)
            orig_b = int(hex_color[5:7], 16)

            rt_r = int(roundtrip[1:3], 16)
            rt_g = int(roundtrip[3:5], 16)
            rt_b = int(roundtrip[5:7], 16)

            # Check that roundtrip is within 2 units (small OKLCH precision loss)
            assert (
                abs(orig_r - rt_r) <= 2
            ), f"Red mismatch for {hex_color}: {orig_r} vs {rt_r}"
            assert (
                abs(orig_g - rt_g) <= 2
            ), f"Green mismatch for {hex_color}: {orig_g} vs {rt_g}"
            assert (
                abs(orig_b - rt_b) <= 2
            ), f"Blue mismatch for {hex_color}: {orig_b} vs {rt_b}"

    def test_hex_roundtrip_approximate(self):
        """Test hex roundtripping with tolerance for OKLCH conversion precision."""
        test_colors = [
            "#FF8080",  # Light red
            "#80FF80",  # Light green
            "#8080FF",  # Light blue
            "#FFA500",  # Orange
            "#800080",  # Purple
            "#008080",  # Teal
        ]

        for hex_color in test_colors:
            color = Color.from_hex_string(hex_color)
            roundtrip = color.to_hex()

            # Parse original and roundtrip RGB values
            orig_r = int(hex_color[1:3], 16)
            orig_g = int(hex_color[3:5], 16)
            orig_b = int(hex_color[5:7], 16)

            rt_r = int(roundtrip[1:3], 16)
            rt_g = int(roundtrip[3:5], 16)
            rt_b = int(roundtrip[5:7], 16)

            # Check that roundtrip is within 2 units (small OKLCH precision loss)
            assert (
                abs(orig_r - rt_r) <= 2
            ), f"Red mismatch for {hex_color}: {orig_r} vs {rt_r}"
            assert (
                abs(orig_g - rt_g) <= 2
            ), f"Green mismatch for {hex_color}: {orig_g} vs {rt_g}"
            assert (
                abs(orig_b - rt_b) <= 2
            ), f"Blue mismatch for {hex_color}: {orig_b} vs {rt_b}"

    def test_oklch_string_parsing(self):
        """Test OKLCH string parsing and roundtripping."""
        test_oklch_strings = [
            "oklch(0.628 0.258 29.22)",  # Red-ish
            "oklch(0.558 0.169 142.91)", # Green-ish  
            "oklch(0.571 0.222 20.07)",  # Crimson-ish
            "oklch(0.5 0.2 180)",        # Simple format
            "oklch(50% 0.2 180deg)",     # With percentage and degree
        ]

        for oklch_str in test_oklch_strings:
            color = Color.from_oklch_string(oklch_str)
            
            # Parse the original components for comparison
            content = oklch_str.replace('oklch(', '').replace(')', '')
            parts = content.replace('%', '').replace('deg', '').split()
            orig_l = float(parts[0]) / (100 if '%' in oklch_str else 1)
            orig_c = float(parts[1])
            orig_h = float(parts[2])
            
            # Check components are approximately equal
            l, c, h = color.get_oklch()
            assert abs(l - orig_l) < 0.01, f"Lightness mismatch: {l} vs {orig_l}"
            assert abs(c - orig_c) < 0.01, f"Chroma mismatch: {c} vs {orig_c}"
            assert abs(h - orig_h) < 1.0, f"Hue mismatch: {h} vs {orig_h}"

    def test_oklch_component_access(self):
        """Test OKLCH component getter methods."""
        color = Color.from_hex_string("#FF0000")  # Red

        # Get OKLCH components
        l, c, h = color.get_oklch()

        # Red should have moderate lightness, high chroma, hue around 29°
        assert 0.4 < l < 0.8, f"Unexpected lightness for red: {l}"
        assert c > 0.15, f"Unexpected chroma for red: {c}"
        assert 20 < h < 40, f"Unexpected hue for red: {h}"

    def test_rgb_component_access(self):
        """Test RGB component getter methods."""
        color = Color.from_hex_string("#FF0000")  # Red

        # Get RGB components
        r, g, b = color.get_rgb()

        # Should be close to (1.0, 0.0, 0.0)
        assert abs(r - 1.0) < 0.01, f"Unexpected red component: {r}"
        assert abs(g - 0.0) < 0.01, f"Unexpected green component: {g}"
        assert abs(b - 0.0) < 0.01, f"Unexpected blue component: {b}"

    def test_lightness_adjustment_preserves_hue_chroma(self):
        """Test that lightness adjustment preserves hue and chroma."""
        original = Color.from_hex_string("#FF0000")  # Red

        # Adjust lightness
        brighter = original.adjust_lightness(1.2)  # 20% brighter
        darker = original.adjust_lightness(0.8)  # 20% darker

        # Get OKLCH components
        orig_l, orig_c, orig_h = original.get_oklch()
        bright_l, bright_c, bright_h = brighter.get_oklch()
        dark_l, dark_c, dark_h = darker.get_oklch()

        # Lightness should change as expected
        assert bright_l > orig_l, "Brighter version should have higher lightness"
        assert dark_l < orig_l, "Darker version should have lower lightness"
        assert abs(bright_l - orig_l * 1.2) < 0.01, "Brightness adjustment incorrect"
        assert abs(dark_l - orig_l * 0.8) < 0.01, "Darkness adjustment incorrect"

        # Chroma should be preserved (within small tolerance)
        assert abs(bright_c - orig_c) < 0.01, "Brightness adjustment changed chroma"
        assert abs(dark_c - orig_c) < 0.01, "Darkness adjustment changed chroma"

        # Hue should be preserved (within small tolerance)
        assert abs(bright_h - orig_h) < 1.0, "Brightness adjustment changed hue"
        assert abs(dark_h - orig_h) < 1.0, "Darkness adjustment changed hue"

    def test_svg_output_format(self):
        """Test SVG OKLCH string output format."""
        color = Color.from_hex_string("#FF0000")  # Red

        svg_str = color.to_svg_str()
        oklch_str = color.to_oklch_string()

        # Should be identical
        assert svg_str == oklch_str, "SVG string should match OKLCH string"

        # Should have correct format
        assert svg_str.startswith(
            "oklch("
        ), f"SVG string should start with 'oklch(': {svg_str}"
        assert svg_str.endswith(")"), f"SVG string should end with ')': {svg_str}"

        # Should contain three numeric components
        content = svg_str[6:-1]  # Remove "oklch(" and ")"
        parts = content.split()
        assert len(parts) == 3, f"OKLCH string should have 3 components: {parts}"

        # Each part should be numeric
        for part in parts:
            float(part)  # Should not raise exception

    def test_string_dispatch(self):
        """Test from_string dispatches correctly."""
        # Test hex dispatch
        hex_color = Color.from_string("#FF0000")
        direct_hex = Color.from_hex_string("#FF0000")
        assert hex_color.to_hex() == direct_hex.to_hex()

        # Test OKLCH dispatch
        oklch_color = Color.from_string("oklch(0.628 0.258 29.22)")
        direct_oklch = Color.from_oklch_string("oklch(0.628 0.258 29.22)")
        assert oklch_color.to_oklch_string() == direct_oklch.to_oklch_string()
        
        # Test unsupported format
        with pytest.raises(ValueError, match="Unsupported color format"):
            Color.from_string("unsupported_format")

    def test_lightness_clamping(self):
        """Test that lightness adjustments are properly clamped."""
        # Start with a dark color
        dark_color = Color.from_hex_string("#404040")

        # Try to make it much darker (should clamp to 0)
        very_dark = dark_color.adjust_lightness(0.1)  # 90% darker
        l, c, h = very_dark.get_oklch()

        assert l >= 0.0, f"Lightness should be clamped to >= 0: {l}"

    def test_invalid_formats_raise_errors(self):
        """Test that invalid color formats raise appropriate errors."""
        # Test empty string
        with pytest.raises(ValueError, match="Empty color string"):
            Color.from_string("")
            
        # Test invalid hex
        with pytest.raises(ValueError, match="Invalid hex color format"):
            Color.from_hex_string("#gggggg")
            
        # Test invalid OKLCH
        with pytest.raises(ValueError, match="Invalid OKLCH"):
            Color.from_oklch_string("oklch(invalid)")
            
        # Test unsupported format
        with pytest.raises(ValueError, match="Unsupported color format"):
            Color.from_string("rgb(255, 0, 0)")

    def test_perceptual_uniformity(self):
        """Test that OKLCH adjustments are more perceptually uniform than RGB."""
        # Create colors across the spectrum
        test_colors = ["#FF0000", "#00FF00", "#0000FF", "#FFFF00", "#FF00FF", "#00FFFF"]

        rgb_differences = []
        oklch_differences = []

        for hex_color in test_colors:
            color = Color.from_hex_string(hex_color)
            brighter = color.adjust_lightness(1.2)

            # Calculate RGB difference (simple Euclidean)
            r1, g1, b1 = color.get_rgb()
            r2, g2, b2 = brighter.get_rgb()
            rgb_diff = ((r2 - r1) ** 2 + (g2 - g1) ** 2 + (b2 - b1) ** 2) ** 0.5
            rgb_differences.append(rgb_diff)

            # Calculate OKLCH lightness difference
            l1, c1, h1 = color.get_oklch()
            l2, c2, h2 = brighter.get_oklch()
            oklch_diff = abs(l2 - l1)
            oklch_differences.append(oklch_diff)

        # OKLCH lightness differences should be more consistent (lower standard deviation)
        oklch_std = np.std(oklch_differences)
        rgb_std = np.std(rgb_differences)

        # This is a qualitative test - OKLCH should be more uniform
        # (Exact values depend on the colors chosen, but OKLCH should be much more consistent)
        assert (
            oklch_std < rgb_std / 2
        ), f"OKLCH should be more perceptually uniform: OKLCH std={oklch_std}, RGB std={rgb_std}"

"""Test edge cases for Color class to prevent hex parsing errors."""

import pytest
from luminary.color import Color


def test_color_from_empty_hex():
    """Test that empty hex strings raise appropriate error."""
    with pytest.raises(ValueError, match="Empty hex color string provided"):
        Color.from_hex_string("")


def test_color_from_none_hex():
    """Test that None values are handled appropriately."""
    with pytest.raises(ValueError, match="Empty hex color string provided"):
        Color.from_hex_string(None)


def test_color_from_empty_color_string():
    """Test that empty color strings raise appropriate error."""
    with pytest.raises(ValueError, match="Empty color string provided"):
        Color.from_string("")


def test_color_from_invalid_hex_length():
    """Test that invalid hex lengths raise appropriate error."""
    # Too short (2 chars)
    with pytest.raises(ValueError, match="must be 3 or 6 characters"):
        Color.from_hex_string("#ff")

    # Too long (7 chars)
    with pytest.raises(ValueError, match="must be 3 or 6 characters"):
        Color.from_hex_string("#ff00000")

    # Invalid length (4 chars)
    with pytest.raises(ValueError, match="must be 3 or 6 characters"):
        Color.from_hex_string("#ffff")


def test_color_from_short_hex():
    """Test that 3-character hex codes are properly expanded."""
    color = Color.from_hex_string("#f0c")
    # Should be equivalent to #ff00cc

    # Test that it doesn't crash and produces valid output
    hex_out = color.to_hex()
    assert hex_out.startswith("#")
    assert len(hex_out) == 7


def test_color_from_invalid_hex_chars():
    """Test that invalid hex characters raise appropriate error."""
    with pytest.raises(ValueError, match="Invalid hex color format"):
        Color.from_hex_string("#gghhii")

    with pytest.raises(ValueError, match="Invalid hex color format"):
        Color.from_hex_string("#12345z")


def test_color_from_valid_3_char_hex():
    """Test various 3-character hex codes."""
    test_cases = ["#fff", "#000", "#f0c", "#a1b"]

    for hex_code in test_cases:
        color = Color.from_hex_string(hex_code)
        # Should not raise any errors
        result = color.to_hex()
        assert isinstance(result, str)
        assert result.startswith("#")
        assert len(result) == 7


def test_color_from_valid_6_char_hex():
    """Test various 6-character hex codes."""
    test_cases = ["#ffffff", "#000000", "#ff00cc", "#a1b2c3"]

    for hex_code in test_cases:
        color = Color.from_hex_string(hex_code)
        # Should not raise any errors
        result = color.to_hex()
        assert isinstance(result, str)
        assert result.startswith("#")
        assert len(result) == 7

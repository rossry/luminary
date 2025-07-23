"""Tests for Beam class geometry and color functionality."""

import pytest
from luminary.geometry.beam import Beam
from luminary.geometry.point import Point
from luminary.color import Color


class TestBeam:
    """Test Beam class functionality."""

    def test_beam_initialization(self):
        """Test basic beam initialization."""
        extent_pairs = [(Point(0, 10), Point(5, 10))]
        beam = Beam(
            extent_pairs=extent_pairs,
            beam_index=0,
            edge_index=0,
            anchor_point=Point(2.5, 0),
            starboard_vector=Point(5, 0),
            parity=0,
        )

        assert beam.beam_index == 0
        assert beam.edge_index == 0
        assert beam.anchor_point.x == 2.5
        assert beam.anchor_point.y == 0
        assert beam.starboard_vector.x == 5
        assert beam.starboard_vector.y == 0
        assert len(beam.vertices) == 4

    def test_beam_vertices_calculation(self):
        """Test beam vertices are calculated correctly."""
        # Simple horizontal beam
        extent_pairs = [(Point(0, 10), Point(5, 10))]
        beam = Beam(
            extent_pairs=extent_pairs,
            beam_index=0,
            edge_index=0,
            anchor_point=Point(2.5, 0),
            starboard_vector=Point(5, 0),
            parity=0,
        )

        vertices = beam.vertices
        
        # Should be 4 vertices forming a quadrilateral
        assert len(vertices) == 4
        
        # Vertices should include baseline and forward edge
        baseline_port = vertices[0]  # anchor - half_width
        baseline_starboard = vertices[1]  # anchor + half_width
        forward_starboard = vertices[2]  # from extent_pairs[0][1]
        forward_port = vertices[3]  # from extent_pairs[0][0]
        
        # Check baseline points
        assert baseline_port.x == 0.0  # 2.5 - 2.5
        assert baseline_port.y == 0.0
        assert baseline_starboard.x == 5.0  # 2.5 + 2.5
        assert baseline_starboard.y == 0.0
        
        # Check forward points match extent
        assert forward_starboard.x == 5.0
        assert forward_starboard.y == 10.0
        assert forward_port.x == 0.0
        assert forward_port.y == 10.0

    def test_beam_forward_vector_calculation(self):
        """Test forward vector is perpendicular to starboard vector."""
        extent_pairs = [(Point(0, 10), Point(5, 10))]
        
        # Horizontal starboard vector
        beam = Beam(
            extent_pairs=extent_pairs,
            beam_index=0,
            edge_index=0,
            anchor_point=Point(0, 0),
            starboard_vector=Point(5, 0),
            parity=0,
        )
        
        # Forward vector should be perpendicular: (-0, 5) = (0, 5)
        assert beam.forward_vector.x == 0
        assert beam.forward_vector.y == 5
        
        # Test with vertical starboard vector
        beam2 = Beam(
            extent_pairs=extent_pairs,
            beam_index=0,
            edge_index=0,
            anchor_point=Point(0, 0),
            starboard_vector=Point(0, 5),
            parity=0,
        )
        
        # Forward vector should be perpendicular: (-5, 0)
        assert beam2.forward_vector.x == -5
        assert beam2.forward_vector.y == 0

    def test_beam_parity_calculation(self):
        """Test beam color parity based on provided parity value."""
        extent_pairs = [(Point(0, 10), Point(5, 10))]
        
        # Test different parity values
        test_cases = [
            (0, 1.2),  # Parity 0 = bright
            (1, 0.8),  # Parity 1 = dim  
        ]
        
        for parity, expected_multiplier in test_cases:
            beam = Beam(
                extent_pairs=extent_pairs,
                beam_index=0,
                edge_index=0,
                anchor_point=Point(0, 0),
                starboard_vector=Point(5, 0),
                parity=parity,
            )
            
            multiplier = beam.get_fill_color_multiplier()
            assert multiplier == expected_multiplier, f"Failed for parity={parity}"

    def test_beam_color_adjustment_hex(self):
        """Test beam color adjustment with hex colors."""
        extent_pairs = [(Point(0, 10), Point(5, 10))]
        
        # Bright beam (multiplier = 1.2)
        bright_beam = Beam(
            extent_pairs=extent_pairs,
            beam_index=0, edge_index=0,
            anchor_point=Point(0, 0),
            starboard_vector=Point(5, 0),
            parity=0,  # Bright beam
        )
        
        adjusted_color = bright_beam._adjust_color_brightness("#FF0000", 1.2)
        
        # Should be OKLCH format
        assert adjusted_color.startswith("oklch(")
        assert adjusted_color.endswith(")")
        
        # Should be brighter than original
        original_color = Color.from_hex_string("#FF0000")
        adjusted_color_obj = Color.from_string("#FF0000").adjust_lightness(1.2)
        
        orig_l, _, _ = original_color.get_oklch()
        adj_l, _, _ = adjusted_color_obj.get_oklch()
        assert adj_l > orig_l

    def test_beam_color_adjustment_hex_dim(self):
        """Test beam color adjustment with hex colors for dim beams."""
        extent_pairs = [(Point(0, 10), Point(5, 10))]
        
        # Dim beam (multiplier = 0.8)
        dim_beam = Beam(
            extent_pairs=extent_pairs,
            beam_index=1, edge_index=0,
            anchor_point=Point(0, 0),
            starboard_vector=Point(5, 0),
            parity=1,  # Dim beam
        )
        
        adjusted_color = dim_beam._adjust_color_brightness("#0000FF", 0.8)
        
        # Should be OKLCH format
        assert adjusted_color.startswith("oklch(")
        assert adjusted_color.endswith(")")
        
        # Should be darker than original
        original_color = Color.from_string("#0000FF")
        adjusted_color_obj = Color.from_string("#0000FF").adjust_lightness(0.8)
        
        orig_l, _, _ = original_color.get_oklch()
        adj_l, _, _ = adjusted_color_obj.get_oklch()
        assert adj_l < orig_l

    def test_beam_svg_generation(self):
        """Test SVG generation includes color adjustment."""
        extent_pairs = [(Point(0, 10), Point(5, 10))]
        beam = Beam(
            extent_pairs=extent_pairs,
            beam_index=0, edge_index=0,
            anchor_point=Point(0, 0),
            starboard_vector=Point(5, 0),
            parity=0,  # Bright beam
        )
        
        svg_elements = beam.get_svg("#FF0000")
        
        assert len(svg_elements) == 1
        svg = svg_elements[0]
        
        # Should contain polygon with OKLCH color and beam opacity
        assert "polygon" in svg
        assert "oklch(" in svg
        assert 'fill-opacity="0.6"' in svg

    def test_beam_sample_generation(self):
        """Test beam sample point generation."""
        extent_pairs = [(Point(0, 20), Point(5, 20))]
        beam = Beam(
            extent_pairs=extent_pairs,
            beam_index=0,
            edge_index=0,
            anchor_point=Point(2.5, 0),
            starboard_vector=Point(5, 0),
            parity=0,
        )
        
        samples = beam.generate_samples()
        
        # Should have at least one sample
        assert len(samples) >= 1
        
        # First sample should be at 0.5w forward
        first_sample = samples[0]
        expected_x = 2.5  # anchor x
        expected_y = 2.5  # anchor y + 0.5 * forward_vector.y (5)
        
        assert abs(first_sample.x - expected_x) < 0.001
        assert abs(first_sample.y - expected_y) < 0.001

    def test_beam_dual_extents_supported(self):
        """Test that dual extents (1 or 2) are supported."""
        # Dual extent pairs should work
        extent_pairs = [
            (Point(0, 10), Point(5, 10)),
            (Point(0, 20), Point(5, 20))
        ]
        
        beam = Beam(
            extent_pairs=extent_pairs,
            beam_index=0,
            edge_index=0,
            anchor_point=Point(2.5, 0),
            starboard_vector=Point(5, 0),
            parity=0,
        )
        
        # Should successfully create beam with appropriate extent selection
        assert len(beam.extent_pairs) == 2
        assert len(beam.vertices) == 4  # 4-sided polygon for now
        
    def test_beam_too_many_extents_not_supported(self):
        """Test that more than 2 extents raise NotImplementedError."""
        # Three extent pairs should raise error
        extent_pairs = [
            (Point(0, 10), Point(5, 10)),
            (Point(0, 20), Point(5, 20)),
            (Point(0, 30), Point(5, 30))
        ]
        
        with pytest.raises(NotImplementedError, match="Currently only 1 or 2 extents supported"):
            Beam(
                extent_pairs=extent_pairs,
                beam_index=0,
                edge_index=0,
                anchor_point=Point(0, 0),
                starboard_vector=Point(5, 0),
                parity=0,
            )

    def test_beam_point_in_geometry(self):
        """Test point-in-polygon detection for beams."""
        # Simple rectangular beam
        extent_pairs = [(Point(0, 10), Point(10, 10))]
        beam = Beam(
            extent_pairs=extent_pairs,
            beam_index=0,
            edge_index=0,
            anchor_point=Point(5, 0),
            starboard_vector=Point(10, 0),
            parity=0,
        )
        
        # Point inside beam should return True
        inside_point = Point(5, 5)
        assert beam._point_in_geometry(inside_point)
        
        # Point outside beam should return False
        outside_point = Point(15, 5)
        assert not beam._point_in_geometry(outside_point)
        
        # Point on edge might return True or False (depends on ray casting precision)
        edge_point = Point(0, 5)
        # Don't assert specific value as edge cases can vary with floating point precision

    def test_beam_alternation_pattern(self):
        """Test that beams alternate correctly with sequential parity."""
        extent_pairs = [(Point(0, 10), Point(2, 10))]
        
        # Create several beams with alternating parity (as would be assigned during generation)
        beams = []
        for i in range(6):
            beam = Beam(
                extent_pairs=extent_pairs,
                beam_index=i,
                edge_index=0,
                anchor_point=Point(1, 0),
                starboard_vector=Point(2, 0),
                parity=i % 2,  # Sequential alternation: 0, 1, 0, 1, 0, 1
            )
            beams.append(beam)
        
        # Check alternation pattern
        multipliers = [beam.get_fill_color_multiplier() for beam in beams]
        expected = [1.2, 0.8, 1.2, 0.8, 1.2, 0.8]  # Alternating bright/dim
        
        assert multipliers == expected

    def test_beam_color_consistency(self):
        """Test that same parity beams produce consistent colors."""
        extent_pairs = [(Point(0, 10), Point(5, 10))]
        
        # Two beams with same parity
        beam1 = Beam(
            extent_pairs=extent_pairs,
            beam_index=0, edge_index=0,
            anchor_point=Point(0, 0),
            starboard_vector=Point(5, 0),
            parity=0,  # Same parity
        )
        
        beam2 = Beam(
            extent_pairs=extent_pairs,
            beam_index=2, edge_index=2,
            anchor_point=Point(0, 0),
            starboard_vector=Point(5, 0),
            parity=0,  # Same parity
        )
        
        # Should have same color multiplier
        assert beam1.get_fill_color_multiplier() == beam2.get_fill_color_multiplier()
        
        # Should produce same adjusted color
        color1 = beam1._adjust_color_brightness("#FF0000", beam1.get_fill_color_multiplier())
        color2 = beam2._adjust_color_brightness("#FF0000", beam2.get_fill_color_multiplier())
        
        assert color1 == color2
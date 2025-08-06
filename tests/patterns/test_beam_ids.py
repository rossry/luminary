"""Tests for beam ID system and SVG pattern rendering."""

import unittest
import tempfile
from pathlib import Path

from luminary.geometry.point import Point
from luminary.geometry.beam import Beam
from luminary.geometry.primitives import OrientedSegment, Vector
from luminary.color import Color


class TestBeamIDs(unittest.TestCase):
    """Test beam ID system."""

    def test_beam_id_creation(self):
        """Test that beams are created with proper IDs."""
        # Create test beam with minimal extent
        port_point = Point(0, 0)
        starboard_point = Point(1, 0) 
        
        extent_segment = OrientedSegment({
            "port": port_point,
            "starboard": starboard_point
        })
        
        beam = Beam(
            extent_segments=[extent_segment],
            beam_index=5,
            edge_index=2,
            anchor_point=Point(0.5, -0.5),
            starboard_vector=Vector(1, 0),
            parity=1,
            face_index=10,
            facet_index=1
        )
        
        # Check beam ID tuple
        expected_id = (10, 1, 2, 5)
        self.assertEqual(beam.beam_id, expected_id)
        
        # Check individual components
        self.assertEqual(beam.face_index, 10)
        self.assertEqual(beam.facet_index, 1)
        self.assertEqual(beam.edge_index, 2)
        self.assertEqual(beam.beam_index, 5)

    def test_beam_svg_with_pattern_colors(self):
        """Test beam SVG generation with pattern colors."""
        # Create test beam
        port_point = Point(0, 0)
        starboard_point = Point(2, 0)
        forward_port = Point(0, 1)
        forward_starboard = Point(2, 1)
        
        extent_segment = OrientedSegment({
            "port": forward_port,
            "starboard": forward_starboard
        })
        
        beam = Beam(
            extent_segments=[extent_segment],
            beam_index=0,
            edge_index=1,
            anchor_point=Point(1, 0),
            starboard_vector=Vector(2, 0),
            parity=0,
            face_index=5,
            facet_index=2
        )
        
        # Test without beam colors (should use base color)
        svg_elements = beam.get_svg("red")
        svg_content = "".join(svg_elements)
        
        self.assertIn('id="beam_5:2:1:0"', svg_content)
        self.assertIn('class="beam"', svg_content)
        self.assertIn('fill="', svg_content)
        
        # Test with beam colors (should override base color)
        pattern_color = Color(0.7, 0.4, 120.0)  # Bright green
        beam_colors = {beam.beam_id: pattern_color}
        
        svg_elements_with_pattern = beam.get_svg("red", beam_colors)
        svg_content_with_pattern = "".join(svg_elements_with_pattern)
        
        self.assertIn('id="beam_5:2:1:0"', svg_content_with_pattern)
        self.assertIn('class="beam"', svg_content_with_pattern)
        self.assertIn('oklch(0.700 0.400 120.0)', svg_content_with_pattern)

    def test_beam_svg_fallback_to_base_color(self):
        """Test beam SVG falls back to base color when not in beam_colors dict."""
        # Create test beam
        port_point = Point(0, 0)
        starboard_point = Point(1, 0)
        extent_segment = OrientedSegment({
            "port": port_point,
            "starboard": starboard_point
        })
        
        beam = Beam(
            extent_segments=[extent_segment],
            beam_index=3,
            edge_index=0,
            anchor_point=Point(0.5, -0.5),
            starboard_vector=Vector(1, 0),
            parity=1,
            face_index=8,
            facet_index=0
        )
        
        # Create beam_colors dict without this beam
        other_beam_id = (9, 1, 2, 4)  # Different beam
        beam_colors = {other_beam_id: Color(0.5, 0.3, 180.0)}
        
        svg_elements = beam.get_svg("blue", beam_colors)
        svg_content = "".join(svg_elements)
        
        # Should use adjusted base color, not pattern color
        self.assertIn('id="beam_8:0:0:3"', svg_content)
        self.assertNotIn('oklch(0.500 0.300 180.0)', svg_content)

    def test_beam_id_string_format(self):
        """Test beam ID string formatting for SVG."""
        # Create test beam
        port_point = Point(0, 0)
        starboard_point = Point(1, 0)
        extent_segment = OrientedSegment({
            "port": port_point,
            "starboard": starboard_point
        })
        
        beam = Beam(
            extent_segments=[extent_segment],
            beam_index=12,
            edge_index=3,
            anchor_point=Point(0.5, -0.5),
            starboard_vector=Vector(1, 0),
            parity=0,
            face_index=25,
            facet_index=1
        )
        
        svg_elements = beam.get_svg("green")
        svg_content = "".join(svg_elements)
        
        # Check exact ID format
        self.assertIn('id="beam_25:1:3:12"', svg_content)

    def test_beam_basis_point(self):
        """Test beam basis point calculation for pattern evaluation."""
        # Create test beam
        anchor = Point(10, 20)
        starboard_vec = Vector(2, 0)  # 2 units wide beam
        forward_vec = Vector(0, 1)    # Forward is up
        
        port_point = Point(0, 0)
        starboard_point = Point(1, 0)
        extent_segment = OrientedSegment({
            "port": port_point,
            "starboard": starboard_point
        })
        
        beam = Beam(
            extent_segments=[extent_segment],
            beam_index=0,
            edge_index=0,
            anchor_point=anchor,
            starboard_vector=starboard_vec,
            parity=0,
            face_index=0,
            facet_index=0
        )
        
        # Basis point should be half a width forward from anchor
        expected_basis = Point(10, 20.5)  # anchor + 0.5 * forward_vector
        basis_point = beam.get_basis_point()
        
        self.assertAlmostEqual(basis_point.x, expected_basis.x, places=3)
        self.assertAlmostEqual(basis_point.y, expected_basis.y, places=3)


class TestSVGPatternIntegration(unittest.TestCase):
    """Test SVG pattern rendering integration."""

    def test_svg_beam_count_validation(self):
        """Test that SVG contains expected number of beam elements."""
        # This is more of an integration test that would need a full Net
        # For now, just test the structure
        pass  # Would need full Net setup

    def test_svg_pattern_color_application(self):
        """Test that pattern colors are correctly applied in SVG."""
        # This would test the full Net.get_svg() -> Beam.get_svg() chain
        pass  # Would need full Net setup with pattern colors


if __name__ == "__main__":
    unittest.main()
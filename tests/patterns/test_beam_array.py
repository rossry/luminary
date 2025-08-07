"""Tests for beam array construction and pattern color mapping."""

import unittest
import numpy as np
from pathlib import Path

from luminary.config import JSONLoader
from luminary.geometry.net import Net
from luminary.patterns.beam_array import BeamArrayBuilder
from luminary.patterns.schema import BeamArrayColumns
from luminary.color import Color


class TestBeamArrayBuilder(unittest.TestCase):
    """Test BeamArrayBuilder functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Load a small config for testing
        config_path = Path("configs/4A-35.json")
        if not config_path.exists():
            self.skipTest("Test config not found - skipping beam array tests")
        
        self.config = JSONLoader.load_config(str(config_path))
        self.net = Net(self.config)
        self.builder = BeamArrayBuilder(self.net)

    def test_build_array_structure(self):
        """Test that beam array has correct structure."""
        beam_array = self.builder.build_array()
        
        # Check shape
        self.assertEqual(beam_array.ndim, 2)
        self.assertEqual(beam_array.shape[1], 11)  # All columns
        self.assertGreater(beam_array.shape[0], 0)  # Some beams
        
        # Check data types
        self.assertEqual(beam_array.dtype, np.float32)

    def test_beam_array_columns(self):
        """Test that beam array columns contain valid data."""
        beam_array = self.builder.build_array()
        
        if beam_array.shape[0] == 0:
            self.skipTest("No beams generated - cannot test columns")
        
        # Check spatial coordinates (should not be all zeros)
        x_col = beam_array[:, BeamArrayColumns.X]
        y_col = beam_array[:, BeamArrayColumns.Y]
        self.assertFalse(np.all(x_col == 0))
        self.assertFalse(np.all(y_col == 0))
        
        # Check r and theta are computed correctly
        r_col = beam_array[:, BeamArrayColumns.R]
        theta_col = beam_array[:, BeamArrayColumns.THETA]
        
        # R should be >= 0
        self.assertTrue(np.all(r_col >= 0))
        
        # Theta should be in [-pi, pi]
        self.assertTrue(np.all(theta_col >= -np.pi))
        self.assertTrue(np.all(theta_col <= np.pi))
        
        # Check geometric hierarchy (should be non-negative integers)
        face_col = beam_array[:, BeamArrayColumns.FACE]
        facet_col = beam_array[:, BeamArrayColumns.FACET]
        edge_col = beam_array[:, BeamArrayColumns.EDGE]
        pos_col = beam_array[:, BeamArrayColumns.POSITION_INDEX]
        
        self.assertTrue(np.all(face_col >= 0))
        self.assertTrue(np.all(facet_col >= 0))
        self.assertTrue(np.all(edge_col >= 0))
        self.assertTrue(np.all(pos_col >= 0))
        
        # Edge should be in [0, 3] (4 edges per facet)
        self.assertTrue(np.all(edge_col <= 3))
        
        # Facet should be in [0, 2] (3 facets per triangle)  
        self.assertTrue(np.all(facet_col <= 2))

    def test_hardware_mapping(self):
        """Test hardware mapping calculation."""
        beam_array = self.builder.build_array()
        
        if beam_array.shape[0] == 0:
            self.skipTest("No beams generated - cannot test hardware mapping")
        
        # Check hardware columns
        node_col = beam_array[:, BeamArrayColumns.NODE]
        strip_col = beam_array[:, BeamArrayColumns.STRIP]
        strip_idx_col = beam_array[:, BeamArrayColumns.STRIP_IDX]
        
        # Node should be in [0, 63]
        self.assertTrue(np.all(node_col >= 0))
        self.assertTrue(np.all(node_col < 64))
        
        # Strip should be in [0, 3] (matches edge index)
        self.assertTrue(np.all(strip_col >= 0))
        self.assertTrue(np.all(strip_col <= 3))
        
        # Strip index should be in [0, 511]
        self.assertTrue(np.all(strip_idx_col >= 0))
        self.assertTrue(np.all(strip_idx_col < 512))

    def test_create_beam_colors_dict(self):
        """Test beam colors dictionary creation."""
        beam_array = self.builder.build_array()
        
        if beam_array.shape[0] == 0:
            self.skipTest("No beams generated - cannot test beam colors")
        
        # Create test OKLCH values
        n_beams = beam_array.shape[0]
        test_oklch = np.zeros((n_beams, 3))
        test_oklch[:, 0] = 0.5  # L = 0.5
        test_oklch[:, 1] = 0.3  # C = 0.3
        test_oklch[:, 2] = np.linspace(0, 360, n_beams)  # H varies
        
        # Create beam colors dictionary
        beam_colors = self.builder.create_beam_colors_dict(test_oklch)
        
        # Check dictionary structure
        self.assertIsInstance(beam_colors, dict)
        self.assertEqual(len(beam_colors), n_beams)
        
        # Check keys are tuples
        for beam_id in beam_colors.keys():
            self.assertIsInstance(beam_id, tuple)
            self.assertEqual(len(beam_id), 4)  # (face, facet, edge, position)
        
        # Check values are Color objects
        for color in beam_colors.values():
            self.assertIsInstance(color, Color)
            
        # Check first few colors have expected values
        if n_beams > 0:
            first_color = list(beam_colors.values())[0]
            self.assertAlmostEqual(first_color.l, 0.5, places=3)
            self.assertAlmostEqual(first_color.c, 0.3, places=3)

    def test_empty_beam_handling(self):
        """Test handling of configurations with no beams."""
        # Create a minimal net that might have no beams
        from luminary.config import NetConfiguration, GeometryConfig
        
        # Create minimal config with no triangles
        minimal_config = NetConfiguration(
            geometry=GeometryConfig(
                triangles=[],
                apex=[0.0, 0.0],
                lines=[]
            ),
            rendering={
                "svg": {"width": "100", "height": "100", "viewBox": "0 0 100 100"}
            }
        )
        
        minimal_net = Net(minimal_config)
        minimal_builder = BeamArrayBuilder(minimal_net)
        
        beam_array = minimal_builder.build_array()
        self.assertEqual(beam_array.shape[0], 0)
        self.assertEqual(beam_array.shape[1], 11)
        
        # Empty OKLCH array should return empty colors dict
        empty_oklch = np.zeros((0, 3))
        beam_colors = minimal_builder.create_beam_colors_dict(empty_oklch)
        self.assertEqual(len(beam_colors), 0)


if __name__ == "__main__":
    unittest.main()
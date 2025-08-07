"""Integration tests for the complete patterns system."""

import unittest
import tempfile
import shutil
from pathlib import Path
import numpy as np

from luminary.config import NetConfiguration, GeometryConfig
from luminary.geometry.net import Net
from luminary.patterns.beam_array import BeamArrayBuilder
from luminary.patterns.base import LuminaryPattern
from luminary.patterns.schema import BeamArrayColumns
from luminary.color import Color


class SimpleTestPattern(LuminaryPattern):
    """Simple test pattern for integration testing."""
    
    @property
    def name(self) -> str:
        return "Simple Test Pattern"
    
    @property
    def description(self) -> str:
        return "A simple gradient pattern for testing"
    
    def evaluate(self, beam_array: np.ndarray, t: float) -> np.ndarray:
        """Create a simple gradient pattern based on position."""
        n_beams = beam_array.shape[0]
        oklch = np.zeros((n_beams, 3))
        
        # Fixed lightness and chroma
        oklch[:, 0] = 0.6  # L = 0.6
        oklch[:, 1] = 0.4  # C = 0.4
        
        # Hue varies with theta
        theta = beam_array[:, BeamArrayColumns.THETA]
        hue = (theta * 180.0 / np.pi) % 360.0
        oklch[:, 2] = hue
        
        return oklch


class TestPatternsIntegration(unittest.TestCase):
    """Test complete patterns system integration."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()
        self.config_path = Path("configs/4A-35.json")
        
        # Skip if config not available
        if not self.config_path.exists():
            self.skipTest("Test configuration not found")

    def tearDown(self):
        """Clean up temporary directories."""
        shutil.rmtree(self.test_dir)

    def test_full_pattern_pipeline(self):
        """Test the complete pattern evaluation and SVG generation pipeline."""
        # 1. Load configuration and create Net
        from luminary.config import JSONLoader
        config = JSONLoader.load_config(str(self.config_path))
        net = Net(config)
        
        # 2. Build beam array
        builder = BeamArrayBuilder(net)
        beam_array = builder.build_array()
        
        # Verify beam array structure
        self.assertGreater(beam_array.shape[0], 0)
        self.assertEqual(beam_array.shape[1], 11)
        
        # 3. Create and evaluate pattern
        pattern = SimpleTestPattern()
        oklch_values = pattern.evaluate(beam_array, 0.0)
        
        # Verify pattern output
        self.assertEqual(oklch_values.shape, (beam_array.shape[0], 3))
        self.assertTrue(np.all(oklch_values[:, 0] == 0.6))  # L
        self.assertTrue(np.all(oklch_values[:, 1] == 0.4))  # C
        self.assertTrue(np.all(oklch_values[:, 2] >= 0))    # H >= 0
        self.assertTrue(np.all(oklch_values[:, 2] < 360))   # H < 360
        
        # 4. Create beam colors dictionary
        beam_colors = builder.create_beam_colors_dict(oklch_values)
        
        # Verify beam colors dictionary
        self.assertEqual(len(beam_colors), beam_array.shape[0])
        
        # Check that all beam colors are Color objects
        for color in beam_colors.values():
            self.assertIsInstance(color, Color)
            self.assertAlmostEqual(color.l, 0.6, places=2)
            self.assertAlmostEqual(color.c, 0.4, places=2)
        
        # 5. Generate SVG with pattern colors
        svg_elements = net.get_svg(extended=True, beam_colors=beam_colors)
        svg_content = "".join(svg_elements)
        
        # Verify SVG structure
        self.assertIn('<svg', svg_content)
        self.assertIn('</svg>', svg_content)
        self.assertIn('class="beam"', svg_content)
        self.assertIn('oklch(', svg_content)
        
        # Count beam elements in SVG
        beam_count = svg_content.count('class="beam"')
        self.assertEqual(beam_count, beam_array.shape[0])

    def test_pattern_time_variation(self):
        """Test that patterns can vary with time parameter."""
        
        class TimeVaryingPattern(LuminaryPattern):
            @property
            def name(self) -> str:
                return "Time Varying Pattern"
            
            @property
            def description(self) -> str:
                return "Pattern that varies with time"
            
            def evaluate(self, beam_array: np.ndarray, t: float) -> np.ndarray:
                n_beams = beam_array.shape[0]
                oklch = np.zeros((n_beams, 3))
                oklch[:, 0] = 0.5
                oklch[:, 1] = 0.3
                oklch[:, 2] = (t * 90.0) % 360.0  # Hue rotates with time
                return oklch
        
        from luminary.config import JSONLoader
        config = JSONLoader.load_config(str(self.config_path))
        net = Net(config)
        
        builder = BeamArrayBuilder(net)
        beam_array = builder.build_array()
        
        if beam_array.shape[0] == 0:
            self.skipTest("No beams generated")
        
        pattern = TimeVaryingPattern()
        
        # Test different times
        oklch_t0 = pattern.evaluate(beam_array, 0.0)
        oklch_t1 = pattern.evaluate(beam_array, 1.0)
        oklch_t4 = pattern.evaluate(beam_array, 4.0)
        
        # Hues should be different at different times
        self.assertAlmostEqual(oklch_t0[0, 2], 0.0)
        self.assertAlmostEqual(oklch_t1[0, 2], 90.0)
        self.assertAlmostEqual(oklch_t4[0, 2], 0.0)  # 360 % 360 = 0

    def test_beam_id_consistency(self):
        """Test that beam IDs are consistent between array and SVG."""
        from luminary.config import JSONLoader
        config = JSONLoader.load_config(str(self.config_path))
        net = Net(config)
        
        builder = BeamArrayBuilder(net)
        beam_array = builder.build_array()
        
        if beam_array.shape[0] == 0:
            self.skipTest("No beams generated")
        
        # Create simple pattern
        pattern = SimpleTestPattern()
        oklch_values = pattern.evaluate(beam_array, 0.0)
        beam_colors = builder.create_beam_colors_dict(oklch_values)
        
        # Generate SVG
        svg_elements = net.get_svg(extended=True, beam_colors=beam_colors)
        svg_content = "".join(svg_elements)
        
        # Extract beam IDs from beam_colors dict
        beam_ids_from_dict = set(beam_colors.keys())
        
        # Extract beam IDs from SVG content
        import re
        svg_beam_ids = set()
        beam_id_pattern = r'id="beam_(\d+):(\d+):(\d+):(\d+)"'
        matches = re.findall(beam_id_pattern, svg_content)
        
        for match in matches:
            beam_id = (int(match[0]), int(match[1]), int(match[2]), int(match[3]))
            svg_beam_ids.add(beam_id)
        
        # Beam IDs should match between dictionary and SVG
        self.assertEqual(len(beam_ids_from_dict), len(svg_beam_ids))
        self.assertEqual(beam_ids_from_dict, svg_beam_ids)

    def test_pattern_error_handling(self):
        """Test error handling in pattern evaluation."""
        
        class ErrorPattern(LuminaryPattern):
            @property
            def name(self) -> str:
                return "Error Pattern"
            
            @property
            def description(self) -> str:
                return "Pattern that produces errors for testing"
            
            def evaluate(self, beam_array: np.ndarray, t: float) -> np.ndarray:
                # Intentionally return wrong shape
                return np.zeros((beam_array.shape[0], 2))  # Should be 3 columns
        
        from luminary.config import JSONLoader
        config = JSONLoader.load_config(str(self.config_path))
        net = Net(config)
        
        builder = BeamArrayBuilder(net)
        beam_array = builder.build_array()
        
        if beam_array.shape[0] == 0:
            self.skipTest("No beams generated")
        
        pattern = ErrorPattern()
        oklch_values = pattern.evaluate(beam_array, 0.0)
        
        # This should fail when creating beam colors due to wrong shape
        with self.assertRaises(Exception):
            builder.create_beam_colors_dict(oklch_values)

    def test_empty_beam_array_handling(self):
        """Test handling of empty beam arrays."""
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
        
        net = Net(minimal_config)
        builder = BeamArrayBuilder(net)
        beam_array = builder.build_array()
        
        # Should handle empty array gracefully
        self.assertEqual(beam_array.shape[0], 0)
        
        pattern = SimpleTestPattern()
        oklch_values = pattern.evaluate(beam_array, 0.0)
        
        self.assertEqual(oklch_values.shape[0], 0)
        self.assertEqual(oklch_values.shape[1], 3)
        
        beam_colors = builder.create_beam_colors_dict(oklch_values)
        self.assertEqual(len(beam_colors), 0)
        
        # SVG should still be valid
        svg_elements = net.get_svg(extended=True, beam_colors=beam_colors)
        svg_content = "".join(svg_elements)
        
        self.assertIn('<svg', svg_content)
        self.assertIn('</svg>', svg_content)


if __name__ == "__main__":
    unittest.main()
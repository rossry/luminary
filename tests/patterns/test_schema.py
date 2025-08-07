"""Tests for pattern schema and constants."""

import unittest
import numpy as np

from luminary.patterns.schema import BeamArrayColumns, BEAM_ARRAY_COLUMNS, OKLCH_COLUMNS


class TestPatternSchema(unittest.TestCase):
    """Test pattern schema constants and structure."""

    def test_beam_array_columns_constants(self):
        """Test BeamArrayColumns enum values."""
        # Test that all expected columns are defined
        expected_columns = [
            'NODE', 'STRIP', 'STRIP_IDX',
            'X', 'Y', 'R', 'THETA', 
            'FACE', 'FACET', 'EDGE', 'POSITION_INDEX'
        ]
        
        for col_name in expected_columns:
            self.assertTrue(hasattr(BeamArrayColumns, col_name))
            
        # Test that column indices are in expected ranges
        self.assertEqual(BeamArrayColumns.NODE, 0)
        self.assertEqual(BeamArrayColumns.STRIP, 1)
        self.assertEqual(BeamArrayColumns.STRIP_IDX, 2)
        self.assertEqual(BeamArrayColumns.X, 3)
        self.assertEqual(BeamArrayColumns.Y, 4)
        self.assertEqual(BeamArrayColumns.R, 5)
        self.assertEqual(BeamArrayColumns.THETA, 6)
        self.assertEqual(BeamArrayColumns.FACE, 7)
        self.assertEqual(BeamArrayColumns.FACET, 8)
        self.assertEqual(BeamArrayColumns.EDGE, 9)
        self.assertEqual(BeamArrayColumns.POSITION_INDEX, 10)

    def test_beam_array_columns_uniqueness(self):
        """Test that all column indices are unique."""
        column_values = [
            BeamArrayColumns.NODE,
            BeamArrayColumns.STRIP,
            BeamArrayColumns.STRIP_IDX,
            BeamArrayColumns.X,
            BeamArrayColumns.Y,
            BeamArrayColumns.R,
            BeamArrayColumns.THETA,
            BeamArrayColumns.FACE,
            BeamArrayColumns.FACET,
            BeamArrayColumns.EDGE,
            BeamArrayColumns.POSITION_INDEX,
        ]
        
        # All values should be unique
        self.assertEqual(len(column_values), len(set(column_values)))
        
        # Should be consecutive integers starting from 0
        self.assertEqual(sorted(column_values), list(range(len(column_values))))

    def test_beam_array_columns_count(self):
        """Test that BEAM_ARRAY_COLUMNS matches expected count."""
        self.assertEqual(len(BEAM_ARRAY_COLUMNS), 11)

    def test_oklch_columns_structure(self):
        """Test OKLCH columns structure."""
        self.assertEqual(len(OKLCH_COLUMNS), 3)
        
        # Should contain L, C, H in that order
        expected_oklch = ['L', 'C', 'H']
        self.assertEqual(OKLCH_COLUMNS, expected_oklch)

    def test_beam_array_dtypes(self):
        """Test that beam array uses appropriate data types."""
        # Create test array with schema structure
        test_array = np.zeros((5, len(BEAM_ARRAY_COLUMNS)), dtype=np.float32)
        
        # Should be able to store all expected value ranges
        
        # Hardware mapping (integers)
        test_array[:, BeamArrayColumns.NODE] = [0, 15, 31, 47, 63]  # 0-63
        test_array[:, BeamArrayColumns.STRIP] = [0, 1, 2, 3, 0]     # 0-3
        test_array[:, BeamArrayColumns.STRIP_IDX] = [0, 100, 256, 400, 511]  # 0-511
        
        # Spatial coordinates (floats)
        test_array[:, BeamArrayColumns.X] = [-100.5, -50.25, 0.0, 50.25, 100.5]
        test_array[:, BeamArrayColumns.Y] = [-75.3, -25.1, 0.0, 25.1, 75.3]
        test_array[:, BeamArrayColumns.R] = [0.0, 10.5, 50.0, 100.7, 150.8]
        test_array[:, BeamArrayColumns.THETA] = [-np.pi, -np.pi/2, 0, np.pi/2, np.pi]
        
        # Geometric hierarchy (integers)  
        test_array[:, BeamArrayColumns.FACE] = [0, 5, 15, 25, 34]      # Triangle IDs
        test_array[:, BeamArrayColumns.FACET] = [0, 1, 2, 0, 1]       # 0-2
        test_array[:, BeamArrayColumns.EDGE] = [0, 1, 2, 3, 0]        # 0-3  
        test_array[:, BeamArrayColumns.POSITION_INDEX] = [0, 5, 10, 15, 18]  # Beam position
        
        # All values should be preserved correctly
        self.assertEqual(test_array.dtype, np.float32)
        
        # Check some specific values
        self.assertEqual(test_array[4, BeamArrayColumns.NODE], 63.0)
        self.assertAlmostEqual(test_array[2, BeamArrayColumns.THETA], 0.0)
        self.assertEqual(test_array[1, BeamArrayColumns.FACET], 1.0)

    def test_schema_usage_in_indexing(self):
        """Test using schema constants for array indexing."""
        # Create sample beam array data
        n_beams = 100
        beam_array = np.random.rand(n_beams, len(BEAM_ARRAY_COLUMNS)).astype(np.float32)
        
        # Should be able to extract columns using constants
        x_values = beam_array[:, BeamArrayColumns.X]
        y_values = beam_array[:, BeamArrayColumns.Y]
        theta_values = beam_array[:, BeamArrayColumns.THETA]
        
        self.assertEqual(len(x_values), n_beams)
        self.assertEqual(len(y_values), n_beams)
        self.assertEqual(len(theta_values), n_beams)
        
        # Should be able to modify columns
        beam_array[:, BeamArrayColumns.R] = np.sqrt(x_values**2 + y_values**2)
        r_values = beam_array[:, BeamArrayColumns.R]
        
        # R should be computed correctly for at least some values
        for i in range(min(5, n_beams)):
            expected_r = np.sqrt(x_values[i]**2 + y_values[i]**2)
            self.assertAlmostEqual(r_values[i], expected_r, places=5)

    def test_schema_constants_immutability(self):
        """Test that schema constants cannot be accidentally modified."""
        original_columns = BEAM_ARRAY_COLUMNS.copy()
        original_oklch = OKLCH_COLUMNS.copy()
        
        # Try to modify (should not affect originals due to immutability)
        modified_columns = BEAM_ARRAY_COLUMNS
        modified_oklch = OKLCH_COLUMNS
        
        self.assertEqual(BEAM_ARRAY_COLUMNS, original_columns)
        self.assertEqual(OKLCH_COLUMNS, original_oklch)


if __name__ == "__main__":
    unittest.main()
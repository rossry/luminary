"""Tests for pattern base classes and interfaces."""

import unittest
import numpy as np
from abc import ABC

from luminary.patterns.base import LuminaryPattern
from luminary.patterns.schema import BeamArrayColumns


class TestLuminaryPattern(unittest.TestCase):
    """Test LuminaryPattern abstract base class."""

    def test_abstract_base_class(self):
        """Test that LuminaryPattern is properly abstract."""
        # Cannot instantiate abstract base class
        with self.assertRaises(TypeError):
            LuminaryPattern()

    def test_concrete_implementation(self):
        """Test that concrete implementations work correctly."""
        
        class TestPattern(LuminaryPattern):
            @property
            def name(self) -> str:
                return "Test Pattern"
            
            @property
            def description(self) -> str:
                return "A test pattern for unit testing"
            
            def evaluate(self, beam_array: np.ndarray, t: float) -> np.ndarray:
                n_beams = beam_array.shape[0]
                oklch = np.zeros((n_beams, 3))
                oklch[:, 0] = 0.5  # L
                oklch[:, 1] = 0.3  # C  
                oklch[:, 2] = (beam_array[:, BeamArrayColumns.THETA] * 180.0 / np.pi) % 360.0  # H
                return oklch
        
        pattern = TestPattern()
        self.assertEqual(pattern.name, "Test Pattern")
        
        # Test evaluation
        beam_array = np.zeros((10, 11))
        beam_array[:, BeamArrayColumns.THETA] = np.linspace(0, 2*np.pi, 10)
        
        result = pattern.evaluate(beam_array, 0.0)
        
        self.assertEqual(result.shape, (10, 3))
        self.assertTrue(np.all(result[:, 0] == 0.5))  # L
        self.assertTrue(np.all(result[:, 1] == 0.3))  # C
        self.assertTrue(np.all(result[:, 2] >= 0))    # H >= 0
        self.assertTrue(np.all(result[:, 2] < 360))   # H < 360

    def test_info_method_default(self):
        """Test default info method implementation."""
        
        class SimplePattern(LuminaryPattern):
            @property  
            def name(self) -> str:
                return "Simple Pattern"
            
            @property
            def description(self) -> str:
                return "A simple pattern for testing"
            
            def evaluate(self, beam_array: np.ndarray, t: float) -> np.ndarray:
                return np.zeros((beam_array.shape[0], 3))
        
        pattern = SimplePattern()
        info = pattern.info()
        
        self.assertIsInstance(info, dict)
        self.assertIn("name", info)
        self.assertEqual(info["name"], "Simple Pattern")
        self.assertIn("description", info)

    def test_custom_info_method(self):
        """Test custom info method implementation."""
        
        class CustomInfoPattern(LuminaryPattern):
            @property
            def name(self) -> str:
                return "Custom Pattern"
            
            @property
            def description(self) -> str:
                return "A custom test pattern"
            
            def evaluate(self, beam_array: np.ndarray, t: float) -> np.ndarray:
                return np.zeros((beam_array.shape[0], 3))
            
            def info(self) -> dict:
                return {
                    "name": self.name,
                    "description": "A custom test pattern",
                    "author": "Test Suite",
                    "version": "1.0"
                }
        
        pattern = CustomInfoPattern()
        info = pattern.info()
        
        self.assertEqual(info["name"], "Custom Pattern")
        self.assertEqual(info["description"], "A custom test pattern")
        self.assertEqual(info["author"], "Test Suite")
        self.assertEqual(info["version"], "1.0")

    def test_evaluate_input_validation(self):
        """Test that evaluate handles various input shapes correctly."""
        
        class ValidatingPattern(LuminaryPattern):
            @property
            def name(self) -> str:
                return "Validating Pattern"
            
            @property
            def description(self) -> str:
                return "A pattern that validates input"
            
            def evaluate(self, beam_array: np.ndarray, t: float) -> np.ndarray:
                # Validate inputs
                if beam_array.ndim != 2:
                    raise ValueError("beam_array must be 2D")
                if beam_array.shape[1] != 11:
                    raise ValueError("beam_array must have 11 columns")
                    
                n_beams = beam_array.shape[0]
                return np.ones((n_beams, 3)) * 0.5
        
        pattern = ValidatingPattern()
        
        # Valid input
        valid_array = np.zeros((5, 11))
        result = pattern.evaluate(valid_array, 0.0)
        self.assertEqual(result.shape, (5, 3))
        
        # Invalid inputs
        with self.assertRaises(ValueError):
            pattern.evaluate(np.zeros((5,)), 0.0)  # 1D array
            
        with self.assertRaises(ValueError):
            pattern.evaluate(np.zeros((5, 10)), 0.0)  # Wrong number of columns

    def test_time_parameter_usage(self):
        """Test that time parameter affects output correctly."""
        
        class TimeVaryingPattern(LuminaryPattern):
            @property
            def name(self) -> str:
                return "Time Varying Pattern"
            
            @property
            def description(self) -> str:
                return "A pattern that changes over time"
            
            def evaluate(self, beam_array: np.ndarray, t: float) -> np.ndarray:
                n_beams = beam_array.shape[0]
                oklch = np.zeros((n_beams, 3))
                oklch[:, 0] = 0.5
                oklch[:, 1] = 0.3
                oklch[:, 2] = (t * 60.0) % 360.0  # Hue varies with time
                return oklch
        
        pattern = TimeVaryingPattern()
        beam_array = np.zeros((3, 11))
        
        # Different times should produce different hues
        result_t0 = pattern.evaluate(beam_array, 0.0)
        result_t1 = pattern.evaluate(beam_array, 1.0)
        result_t2 = pattern.evaluate(beam_array, 6.0)
        
        self.assertAlmostEqual(result_t0[0, 2], 0.0)
        self.assertAlmostEqual(result_t1[0, 2], 60.0)
        self.assertAlmostEqual(result_t2[0, 2], 0.0)  # 360 % 360 = 0


if __name__ == "__main__":
    unittest.main()
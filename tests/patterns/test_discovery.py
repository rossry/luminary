"""Tests for pattern discovery system."""

import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, mock_open

from luminary.patterns.discovery import discover_patterns, get_pattern_choices, get_pattern_or_select


class TestPatternDiscovery(unittest.TestCase):
    """Test pattern discovery functionality."""

    def setUp(self):
        """Set up test fixtures with temporary pattern directory."""
        self.test_dir = tempfile.mkdtemp()
        self.patterns_dir = Path(self.test_dir) / "patterns"
        self.patterns_dir.mkdir()

    def tearDown(self):
        """Clean up temporary directories."""
        shutil.rmtree(self.test_dir)

    def create_test_pattern_file(self, filename: str, content: str):
        """Create a test pattern file."""
        pattern_file = self.patterns_dir / filename
        pattern_file.write_text(content)
        return pattern_file

    def test_discover_patterns_empty_directory(self):
        """Test discovering patterns in empty directory."""
        with patch('luminary.patterns.discovery.Path') as mock_path:
            mock_path.return_value.glob.return_value = []
            
            patterns = discover_patterns()
            self.assertEqual(len(patterns), 0)

    def test_discover_patterns_with_valid_pattern(self):
        """Test discovering valid pattern files."""
        # Create a valid test pattern
        pattern_content = '''
"""Test pattern for unit tests."""

import numpy as np
from luminary.patterns.base import LuminaryPattern
from luminary.patterns.schema import BeamArrayColumns


class TestPattern(LuminaryPattern):
    """A simple test pattern."""
    
    @property
    def name(self) -> str:
        return "Test Pattern"
    
    def evaluate(self, beam_array: np.ndarray, t: float) -> np.ndarray:
        n_beams = beam_array.shape[0]
        oklch = np.zeros((n_beams, 3))
        oklch[:, 0] = 0.5
        oklch[:, 1] = 0.3
        oklch[:, 2] = 180.0
        return oklch
'''
        
        self.create_test_pattern_file("test_pattern.py", pattern_content)
        
        # Mock the patterns directory path
        with patch('luminary.patterns.discovery.PATTERNS_DIR', self.patterns_dir):
            patterns = discover_patterns()
            
        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0].name, "Test Pattern")

    def test_discover_patterns_skip_invalid_files(self):
        """Test that invalid pattern files are skipped."""
        # Create invalid pattern file (syntax error)
        invalid_content = '''
import numpy as np
from luminary.patterns.base import LuminaryPattern

class BadPattern(LuminaryPattern
    # Missing colon and implementation
'''
        
        # Create valid pattern file
        valid_content = '''
import numpy as np  
from luminary.patterns.base import LuminaryPattern

class GoodPattern(LuminaryPattern):
    @property
    def name(self):
        return "Good Pattern"
    
    def evaluate(self, beam_array, t):
        return np.zeros((beam_array.shape[0], 3))
'''
        
        self.create_test_pattern_file("bad_pattern.py", invalid_content)
        self.create_test_pattern_file("good_pattern.py", valid_content)
        
        with patch('luminary.patterns.discovery.PATTERNS_DIR', self.patterns_dir):
            patterns = discover_patterns()
            
        # Should only find the valid pattern
        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0].name, "Good Pattern")

    def test_discover_patterns_skip_non_python_files(self):
        """Test that non-Python files are ignored."""
        self.create_test_pattern_file("README.md", "# Not a pattern")
        self.create_test_pattern_file("data.json", '{"not": "a pattern"}')
        self.create_test_pattern_file("__pycache__", "")  # Directory-like name
        
        with patch('luminary.patterns.discovery.PATTERNS_DIR', self.patterns_dir):
            patterns = discover_patterns()
            
        self.assertEqual(len(patterns), 0)

    def test_get_pattern_choices(self):
        """Test getting pattern choices."""
        # Create multiple test patterns
        pattern1_content = '''
import numpy as np
from luminary.patterns.base import LuminaryPattern

class FirstPattern(LuminaryPattern):
    @property
    def name(self):
        return "First Pattern"
    
    def evaluate(self, beam_array, t):
        return np.zeros((beam_array.shape[0], 3))
'''
        
        pattern2_content = '''
import numpy as np
from luminary.patterns.base import LuminaryPattern

class SecondPattern(LuminaryPattern):
    @property
    def name(self):
        return "Second Pattern"
    
    def evaluate(self, beam_array, t):
        return np.zeros((beam_array.shape[0], 3))
'''
        
        self.create_test_pattern_file("first.py", pattern1_content)
        self.create_test_pattern_file("second.py", pattern2_content)
        
        with patch('luminary.patterns.discovery.PATTERNS_DIR', self.patterns_dir):
            choices = get_pattern_choices()
            
        expected_choices = ["First Pattern", "Second Pattern"]
        self.assertEqual(sorted(choices), sorted(expected_choices))

    def test_get_pattern_or_select_with_valid_name(self):
        """Test getting pattern by name."""
        pattern_content = '''
import numpy as np
from luminary.patterns.base import LuminaryPattern

class NamedPattern(LuminaryPattern):
    @property
    def name(self):
        return "Named Pattern"
    
    def evaluate(self, beam_array, t):
        return np.zeros((beam_array.shape[0], 3))
'''
        
        self.create_test_pattern_file("named.py", pattern_content)
        
        with patch('luminary.patterns.discovery.PATTERNS_DIR', self.patterns_dir):
            pattern = get_pattern_or_select("Named Pattern")
            
        self.assertEqual(pattern.name, "Named Pattern")

    def test_get_pattern_or_select_invalid_name(self):
        """Test getting pattern with invalid name raises error."""
        with patch('luminary.patterns.discovery.PATTERNS_DIR', self.patterns_dir):
            with self.assertRaises(ValueError) as context:
                get_pattern_or_select("Nonexistent Pattern")
                
        self.assertIn("Pattern 'Nonexistent Pattern' not found", str(context.exception))

    @patch('builtins.input', return_value='1')
    def test_get_pattern_or_select_interactive(self, mock_input):
        """Test interactive pattern selection."""
        pattern_content = '''
import numpy as np
from luminary.patterns.base import LuminaryPattern

class InteractivePattern(LuminaryPattern):
    @property
    def name(self):
        return "Interactive Pattern"
    
    def evaluate(self, beam_array, t):
        return np.zeros((beam_array.shape[0], 3))
'''
        
        self.create_test_pattern_file("interactive.py", pattern_content)
        
        with patch('luminary.patterns.discovery.PATTERNS_DIR', self.patterns_dir):
            with patch('builtins.print'):  # Suppress print output during test
                pattern = get_pattern_or_select(None)
                
        self.assertEqual(pattern.name, "Interactive Pattern")

    @patch('builtins.input', side_effect=['999', '0'])  # Invalid then exit
    def test_interactive_selection_invalid_then_exit(self, mock_input):
        """Test interactive selection with invalid choice then exit."""
        pattern_content = '''
import numpy as np
from luminary.patterns.base import LuminaryPattern

class TestPattern(LuminaryPattern):
    @property
    def name(self):
        return "Test Pattern"
    
    def evaluate(self, beam_array, t):
        return np.zeros((beam_array.shape[0], 3))
'''
        
        self.create_test_pattern_file("test.py", pattern_content)
        
        with patch('luminary.patterns.discovery.PATTERNS_DIR', self.patterns_dir):
            with patch('builtins.print'):  # Suppress print output
                with self.assertRaises(SystemExit):
                    get_pattern_or_select(None)


if __name__ == "__main__":
    unittest.main()
"""Tests for pattern animation server infrastructure."""

import unittest
import tempfile
import shutil
from pathlib import Path
import sys
import subprocess
from unittest.mock import patch, MagicMock

from luminary.config import JSONLoader
from luminary.geometry.net import Net
from luminary.patterns.discovery import get_pattern_or_select


class TestAnimationServer(unittest.TestCase):
    """Test pattern animation server infrastructure."""

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

    def test_server_module_exists(self):
        """Test that the animation server module exists and can be imported."""
        webserver_path = Path(__file__).parent.parent.parent / "patterns" / "webserver" / "server.py"
        
        self.assertTrue(webserver_path.exists(), "WebSocket server file should exist")
        
        # Test that the server script has the expected main function
        server_content = webserver_path.read_text()
        self.assertIn("class PatternAnimationServer", server_content)
        self.assertIn("def main():", server_content)
        self.assertIn("FastAPI", server_content)

    def test_client_html_exists(self):
        """Test that the client HTML file exists."""
        client_path = Path(__file__).parent.parent.parent / "patterns" / "webserver" / "client.html"
        
        self.assertTrue(client_path.exists(), "Client HTML file should exist")
        
        # Test that HTML has expected structure
        client_content = client_path.read_text()
        self.assertIn("<!DOCTYPE html>", client_content)
        self.assertIn("PatternViewer", client_content)
        self.assertIn("WebSocket", client_content)
        self.assertIn("updateBeamColors", client_content)

    def test_server_argument_parsing(self):
        """Test that server can parse command line arguments."""
        webserver_path = Path(__file__).parent.parent.parent / "patterns" / "webserver" / "server.py"
        
        # Test help output
        try:
            result = subprocess.run([
                sys.executable, str(webserver_path), "--help"
            ], capture_output=True, text=True, timeout=10)
            
            self.assertEqual(result.returncode, 0)
            self.assertIn("Luminary Pattern Animation Server", result.stdout)
            self.assertIn("--port", result.stdout)
            self.assertIn("--fps", result.stdout)
            
        except subprocess.TimeoutExpired:
            self.skipTest("Server help command timed out")
        except FileNotFoundError:
            self.skipTest("Python interpreter not found")

    def test_main_cli_preview_integration(self):
        """Test that main.py pattern preview command exists and has correct structure."""
        main_path = Path(__file__).parent.parent.parent / "main.py"
        main_content = main_path.read_text()
        
        # Check that preview command exists
        self.assertIn("cmd_pattern_preview", main_content)
        self.assertIn("pattern preview", main_content)
        self.assertIn("WebSocket server", main_content)
        
        # Check that it has expected arguments
        self.assertIn("--host", main_content)
        self.assertIn("--port", main_content) 
        self.assertIn("--fps", main_content)

    def test_pattern_framebuffer_format(self):
        """Test that patterns can generate framebuffer format for streaming."""
        from luminary.patterns.beam_array import BeamArrayBuilder
        
        config = JSONLoader.load_config(str(self.config_path))
        net = Net(config)
        
        builder = BeamArrayBuilder(net)
        beam_array = builder.build_array()
        
        if beam_array.shape[0] == 0:
            self.skipTest("No beams generated")
        
        # Get test pattern
        pattern = get_pattern_or_select("test")
        
        # Generate pattern data
        oklch_values = pattern.evaluate(beam_array, 0.0)
        beam_colors = builder.create_beam_colors_dict(oklch_values)
        
        # Convert to framebuffer format (what the server would send)
        framebuffer = {}
        for beam_id, color in beam_colors.items():
            # Convert tuple beam ID to colon-separated string
            beam_id_str = f"{beam_id[0]}:{beam_id[1]}:{beam_id[2]}:{beam_id[3]}"
            framebuffer[beam_id_str] = color.to_svg_str()
        
        # Verify framebuffer structure
        self.assertEqual(len(framebuffer), len(beam_colors))
        
        # Check a few framebuffer entries
        sample_keys = list(framebuffer.keys())[:5]
        for key in sample_keys:
            # Should be colon-separated numbers
            parts = key.split(":")
            self.assertEqual(len(parts), 4)
            for part in parts:
                self.assertTrue(part.isdigit(), f"Invalid beam ID part: {part}")
            
            # Should be valid OKLCH color string
            color_str = framebuffer[key]
            self.assertTrue(color_str.startswith("oklch("))
            self.assertTrue(color_str.endswith(")"))

    @patch('subprocess.run')
    def test_preview_command_execution(self, mock_subprocess):
        """Test that preview command would execute with correct arguments."""
        # Mock successful subprocess execution
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_subprocess.return_value = mock_result
        
        # Import and test the preview command function
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from main import cmd_pattern_preview
        
        # Create mock arguments
        class MockArgs:
            def __init__(self):
                self.config = Path("configs/4A-35.json")
                self.pattern_name = "test"
                self.host = "localhost"
                self.port = 8080
                self.fps = 30.0
        
        args = MockArgs()
        
        # Call the preview command
        result = cmd_pattern_preview(args)
        
        # Should succeed
        self.assertEqual(result, 0)
        
        # Check that subprocess was called with correct arguments
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args[0][0]
        
        self.assertIn("server.py", call_args[-7])  # Server script path
        self.assertIn("configs/4A-35.json", call_args)  # Config file
        self.assertIn("test", call_args)  # Pattern name
        self.assertIn("--host", call_args)
        self.assertIn("localhost", call_args)
        self.assertIn("--port", call_args)
        self.assertIn("8080", call_args)
        self.assertIn("--fps", call_args)
        self.assertIn("30.0", call_args)


class TestAnimationInfrastructure(unittest.TestCase):
    """Test animation infrastructure without external dependencies."""
    
    def test_pattern_time_variation(self):
        """Test that patterns produce different outputs at different times."""
        from luminary.patterns.base import LuminaryPattern
        from luminary.patterns.schema import BeamArrayColumns
        import numpy as np
        
        class TimeTestPattern(LuminaryPattern):
            @property
            def name(self) -> str:
                return "Time Test Pattern"
            
            @property
            def description(self) -> str:
                return "Pattern that changes over time for testing"
            
            def evaluate(self, beam_array: np.ndarray, t: float) -> np.ndarray:
                n_beams = beam_array.shape[0]
                oklch = np.zeros((n_beams, 3))
                oklch[:, 0] = 0.5
                oklch[:, 1] = 0.3
                # Hue rotates with time
                oklch[:, 2] = (t * 60.0) % 360.0
                return oklch
        
        # Test with mock beam array
        beam_array = np.zeros((10, 11))
        pattern = TimeTestPattern()
        
        # Get outputs at different times
        t0_output = pattern.evaluate(beam_array, 0.0)
        t1_output = pattern.evaluate(beam_array, 1.0)
        t6_output = pattern.evaluate(beam_array, 6.0)
        
        # Should have same L and C, different H
        np.testing.assert_array_equal(t0_output[:, 0], t1_output[:, 0])  # L same
        np.testing.assert_array_equal(t0_output[:, 1], t1_output[:, 1])  # C same
        
        self.assertAlmostEqual(t0_output[0, 2], 0.0)   # H at t=0
        self.assertAlmostEqual(t1_output[0, 2], 60.0)  # H at t=1
        self.assertAlmostEqual(t6_output[0, 2], 0.0)   # H at t=6 (360 % 360 = 0)

    def test_framebuffer_json_serialization(self):
        """Test that framebuffer data can be JSON serialized."""
        import json
        
        # Create mock framebuffer data
        framebuffer = {
            "0:1:2:3": "oklch(0.5 0.3 120)",
            "1:0:1:4": "oklch(0.6 0.2 240)", 
            "2:2:0:5": "oklch(0.7 0.4 360)"
        }
        
        # Should be able to serialize and deserialize
        json_str = json.dumps(framebuffer)
        restored = json.loads(json_str)
        
        self.assertEqual(framebuffer, restored)
        
        # Should be able to create WebSocket message format
        message = {
            "type": "framebuffer",
            "data": framebuffer,
            "timestamp": 1234567890.123
        }
        
        message_json = json.dumps(message)
        restored_message = json.loads(message_json)
        
        self.assertEqual(message, restored_message)


if __name__ == "__main__":
    unittest.main()
"""Tests for main.py CLI functionality."""

import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import json

from main import main


class TestMainCLI:
    """Test suite for main.py CLI functionality."""

    def test_version_command(self, capsys):
        """Test version subcommand output."""
        with patch("sys.argv", ["main.py", "version"]):
            main()

        captured = capsys.readouterr()
        assert "Luminary v2.0.1 (in development)" in captured.out
        assert "A Next Year on Luna project" in captured.out

    def test_svg_default_output_path(self):
        """Test that SVG command uses correct default output path."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create a mock config file
            config_file = temp_path / "test_config.json"
            config_data = {
                "points": [{"id": "p1", "x": 0, "y": 0}],
                "triangles": [],
                "kites": [],
                "series": [],
            }
            with open(config_file, "w") as f:
                json.dump(config_data, f)

            # Mock Net.from_json_file and save_svg
            mock_net = MagicMock()
            mock_net.get_stats.return_value = {
                "points": 1,
                "triangles": 0,
                "kites": 0,
                "geometric_lines": 0,
                "series": 0,
            }

            with patch("main.Net.from_json_file", return_value=mock_net), patch(
                "sys.argv", ["main.py", "svg", "-c", str(config_file)]
            ), patch("main.__file__", str(temp_path / "main.py")):

                main()

                # Check that save_svg was called with the expected path
                expected_output = temp_path / "output" / "test_config.svg"
                mock_net.save_svg.assert_called_once_with(expected_output)

    def test_svg_custom_output_path(self):
        """Test SVG command with custom output path."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create a mock config file
            config_file = temp_path / "my_diagram.json"
            config_data = {
                "points": [{"id": "p1", "x": 0, "y": 0}],
                "triangles": [],
                "kites": [],
                "series": [],
            }
            with open(config_file, "w") as f:
                json.dump(config_data, f)

            custom_output = temp_path / "custom_output.svg"

            # Mock Net.from_json_file and save_svg
            mock_net = MagicMock()
            mock_net.get_stats.return_value = {
                "points": 1,
                "triangles": 0,
                "kites": 0,
                "geometric_lines": 0,
                "series": 0,
            }

            with patch("main.Net.from_json_file", return_value=mock_net), patch(
                "sys.argv",
                ["main.py", "svg", "-c", str(config_file), "-o", str(custom_output)],
            ):

                main()

                # Check that save_svg was called with custom output path
                mock_net.save_svg.assert_called_once_with(custom_output)

    def test_svg_config_file_not_found(self, capsys):
        """Test SVG command with non-existent config file."""
        with patch("sys.argv", ["main.py", "svg", "-c", "nonexistent.json"]):
            result = main()

        captured = capsys.readouterr()
        assert "Error: Configuration file 'nonexistent.json' not found" in captured.out
        assert result == 1

    def test_svg_output_directory_creation(self):
        """Test that output directory is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create a mock config file
            config_file = temp_path / "diagram.json"
            config_data = {
                "points": [{"id": "p1", "x": 0, "y": 0}],
                "triangles": [],
                "kites": [],
                "series": [],
            }
            with open(config_file, "w") as f:
                json.dump(config_data, f)

            # Mock Net.from_json_file
            mock_net = MagicMock()
            mock_net.get_stats.return_value = {
                "points": 1,
                "triangles": 0,
                "kites": 0,
                "geometric_lines": 0,
                "series": 0,
            }

            # Use a nested output path that doesn't exist
            output_path = temp_path / "deep" / "nested" / "output.svg"

            with patch("main.Net.from_json_file", return_value=mock_net), patch(
                "sys.argv",
                ["main.py", "svg", "-c", str(config_file), "-o", str(output_path)],
            ):

                main()

                # Verify the directory creation was handled
                mock_net.save_svg.assert_called_once_with(output_path)

    def test_no_command_shows_help(self, capsys):
        """Test that running without a command shows help."""
        with patch("sys.argv", ["main.py"]):
            main()

        captured = capsys.readouterr()
        assert "usage:" in captured.out
        assert (
            "positional arguments:" in captured.out
            or "Available commands:" in captured.out
        )

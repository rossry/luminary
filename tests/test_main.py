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
                "facets": [],
                "series": [],
            }
            with open(config_file, "w") as f:
                json.dump(config_data, f)

            # Mock Net.from_json_file and save_svg
            mock_net = MagicMock()
            mock_net.get_stats.return_value = {
                "points": 1,
                "triangles": 0,
                "facets": 0,
                "geometric_lines": 0,
                "series": 0,
            }

            with (
                patch("main.Net.from_json_file", return_value=mock_net),
                patch("sys.argv", ["main.py", "svg", "-c", str(config_file)]),
                patch("main.__file__", str(temp_path / "main.py")),
            ):

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
                "facets": [],
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
                "facets": 0,
                "geometric_lines": 0,
                "series": 0,
            }

            with (
                patch("main.Net.from_json_file", return_value=mock_net),
                patch(
                    "sys.argv",
                    [
                        "main.py",
                        "svg",
                        "-c",
                        str(config_file),
                        "-o",
                        str(custom_output),
                    ],
                ),
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
                "facets": [],
                "series": [],
            }
            with open(config_file, "w") as f:
                json.dump(config_data, f)

            # Mock Net.from_json_file
            mock_net = MagicMock()
            mock_net.get_stats.return_value = {
                "points": 1,
                "triangles": 0,
                "facets": 0,
                "geometric_lines": 0,
                "series": 0,
            }

            # Use a nested output path that doesn't exist
            output_path = temp_path / "deep" / "nested" / "output.svg"

            with (
                patch("main.Net.from_json_file", return_value=mock_net),
                patch(
                    "sys.argv",
                    ["main.py", "svg", "-c", str(config_file), "-o", str(output_path)],
                ),
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

    def test_index_command_creates_html(self):
        """Test index command creates HTML file for SVG directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create some test SVG files
            svg1 = temp_path / "test1.svg"
            svg2 = temp_path / "test2.svg"
            svg1.write_text('<svg><rect width="100" height="100"/></svg>')
            svg2.write_text('<svg><circle cx="50" cy="50" r="25"/></svg>')

            # Create a subdirectory
            subdir = temp_path / "subdir"
            subdir.mkdir()

            with patch("sys.argv", ["main.py", "index", str(temp_path)]):
                result = main()

            assert result == 0
            index_file = temp_path / "index.html"
            assert index_file.exists()

            content = index_file.read_text()
            assert "test1" in content  # Filename stem
            assert "test2" in content  # Filename stem
            assert "subdir: not expanded" in content  # Subdirectory
            assert "SVG Index" in content  # Page title

    def test_index_command_nonexistent_directory(self, capsys):
        """Test index command with non-existent directory."""
        with patch("sys.argv", ["main.py", "index", "nonexistent"]):
            result = main()

        captured = capsys.readouterr()
        assert "Error: Directory 'nonexistent' does not exist" in captured.out
        assert result == 1

    def test_index_command_file_not_directory(self, capsys):
        """Test index command with file instead of directory."""
        with tempfile.NamedTemporaryFile() as temp_file:
            with patch("sys.argv", ["main.py", "index", temp_file.name]):
                result = main()

            captured = capsys.readouterr()
            assert f"Error: '{temp_file.name}' is not a directory" in captured.out
            assert result == 1

    def test_index_command_empty_directory(self):
        """Test index command on empty directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            with patch("sys.argv", ["main.py", "index", str(temp_path)]):
                result = main()

            assert result == 0
            index_file = temp_path / "index.html"
            assert index_file.exists()

            content = index_file.read_text()
            assert "No SVG files or subdirectories found" in content

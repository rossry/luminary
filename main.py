#!/usr/bin/env python3
"""
Main entry point for Luminary.
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime
from luminary.validation.validate import run_validation
from luminary.geometry.net import Net


def generate_svg_index(directory: Path):
    """Generate HTML index for SVG files in a directory."""
    if not directory.exists():
        print(f"Error: Directory '{directory}' does not exist")
        return 1

    if not directory.is_dir():
        print(f"Error: '{directory}' is not a directory")
        return 1

    # Get all SVG files and subdirectories
    svg_files = list(directory.glob("*.svg"))
    subdirs = [p for p in directory.iterdir() if p.is_dir()]

    # Sort by modification time (newest first)
    all_items = svg_files + subdirs
    all_items.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    # Generate HTML content
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SVG Index - {directory.name}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background-color: #f8f9fa;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            padding: 30px;
        }}
        h1 {{
            color: #2c3e50;
            text-align: center;
            margin-bottom: 30px;
        }}
        .item {{
            margin: 30px 0;
            padding: 20px;
            border: 1px solid #e9ecef;
            border-radius: 8px;
            background: #ffffff;
        }}
        .item h2 {{
            color: #34495e;
            margin: 0 0 15px 0;
            font-size: 1.5em;
        }}
        .svg-container {{
            text-align: center;
            margin: 20px 0;
        }}
        .svg-container object {{
            border: 1px solid #ddd;
            border-radius: 4px;
            max-width: 100%;
        }}
        .directory {{
            color: #7f8c8d;
            font-style: italic;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 4px;
        }}
        .timestamp {{
            color: #6c757d;
            font-size: 0.9em;
            margin-top: 10px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>SVG Index - {directory.name}</h1>
"""

    if not all_items:
        html_content += """
        <div class="item">
            <p>No SVG files or subdirectories found.</p>
        </div>
"""
    else:
        for item in all_items:
            if item.is_file() and item.suffix == ".svg":
                # SVG file
                stem = item.stem
                mtime = datetime.fromtimestamp(item.stat().st_mtime).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                html_content += f"""
        <div class="item">
            <h2>{stem}</h2>
            <div class="svg-container">
                <object data="{item.name}" type="image/svg+xml" width="100%" height="400"></object>
            </div>
            <div class="timestamp">Modified: {mtime}</div>
        </div>
"""
            elif item.is_dir():
                # Subdirectory
                mtime = datetime.fromtimestamp(item.stat().st_mtime).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                html_content += f"""
        <div class="item">
            <h2>{item.name}: not expanded</h2>
            <div class="directory">Subdirectory (not expanded)</div>
            <div class="timestamp">Modified: {mtime}</div>
        </div>
"""

    html_content += """
    </div>
</body>
</html>"""

    # Write HTML file
    index_path = directory / "index.html"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Generated index at {index_path}")
    if svg_files:
        print(f"Indexed {len(svg_files)} SVG files")
    if subdirs:
        print(f"Listed {len(subdirs)} subdirectories")

    return 0


def main():
    """Main entry point with subcommands."""
    parser = argparse.ArgumentParser(
        description="Luminary - A Next Year on Luna project"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Version subcommand
    version_parser = subparsers.add_parser("version", help="Show version information")

    # Validation subcommand
    validate_parser = subparsers.add_parser(
        "validate", help="Generate validation SVGs for visual inspection"
    )

    # SVG generation subcommand
    svg_parser = subparsers.add_parser(
        "svg", help="Generate SVG from JSON configuration"
    )
    svg_parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=Path("./config.json"),
        help="JSON configuration file (default: ./config.json)",
    )
    svg_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output SVG file (default: output/{config_stem}.svg)",
    )

    # SVG index subcommand
    index_parser = subparsers.add_parser(
        "index", help="Generate HTML index for SVG files in a directory"
    )
    index_parser.add_argument(
        "directory",
        type=Path,
        help="Directory to scan for SVG files",
    )

    args = parser.parse_args()

    if args.command == "version":
        print("Luminary v2.0.1 (in development)")
        print("A Next Year on Luna project")
    elif args.command == "validate":
        print("Running foundation infrastructure validation...")
        svg_list = run_validation()
        print("Validation files created in output/validation/")
        print("\nSVGs to check:")
        for svg_desc in svg_list:
            print(f"• {svg_desc}")
        print(
            "\nOpen output/validation/index.html in browser to view all SVGs together."
        )
    elif args.command == "svg":
        try:
            # Check if config file exists
            if not args.config.exists():
                print(f"Error: Configuration file '{args.config}' not found")
                return 1

            # Set default output path if not provided
            if args.output is None:
                config_stem = args.config.stem  # filename without .json extension
                script_dir = Path(__file__).parent  # Directory containing main.py
                args.output = script_dir / "output" / f"{config_stem}.svg"

            # Load Net from JSON configuration
            print(f"Loading configuration from {args.config}")
            net = Net.from_json_file(args.config)

            # Generate SVG
            print("Generating SVG...")

            # Create output directory if needed
            args.output.parent.mkdir(parents=True, exist_ok=True)

            # Save SVG
            net.save_svg(args.output)
            print(f"SVG saved to {args.output}")

            # Print statistics
            stats = net.get_stats()
            print(f"\nGenerated SVG contains:")
            print(f"  • {stats['points']} points")
            print(f"  • {stats['triangles']} triangles")
            print(f"  • {stats['kites']} kites")
            print(f"  • {stats['geometric_lines']} geometric lines")
            print(f"  • {stats['series']} triangle series")

        except Exception as e:
            print(f"Error generating SVG: {e}")
            return 1
    elif args.command == "index":
        return generate_svg_index(args.directory)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

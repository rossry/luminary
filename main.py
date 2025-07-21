#!/usr/bin/env python3
"""
Main entry point for Luminary.
"""

import sys
import argparse
from pathlib import Path
from luminary.validation.validate import run_validation
from luminary.geometry.net import Net


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
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

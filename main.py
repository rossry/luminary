#!/usr/bin/env python3
"""
Main entry point for Luminary.
"""

import sys
import argparse
from luminary.validation.validate import run_validation


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
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

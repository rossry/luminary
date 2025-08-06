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


def cmd_pattern(args):
    """Handle pattern subcommand operations."""
    
    if args.pattern_subcommand == "sample":
        return cmd_pattern_sample(args)
    elif args.pattern_subcommand == "preview":
        return cmd_pattern_preview(args)
    elif args.pattern_subcommand == "run":
        return cmd_pattern_run(args)
    else:
        print("Error: No pattern subcommand specified")
        print("Available subcommands: sample, preview, run")
        return 1


def cmd_pattern_sample(args):
    """Generate static SVG with pattern applied."""
    try:
        from luminary.patterns import get_pattern_or_select, BeamArrayBuilder
        from luminary.geometry.net import Net
        
        # Load pattern (with interactive selection if needed)
        pattern = get_pattern_or_select(args.pattern_name)
        print(f"Using pattern: {pattern.name}")
        
        # Check if config file exists
        if not args.config.exists():
            print(f"Error: Configuration file '{args.config}' not found")
            return 1
        
        # Load Net from configuration
        print(f"Loading configuration from {args.config}")
        net = Net.from_json_file(args.config)
        
        # Build beam array
        print("Building beam array...")
        builder = BeamArrayBuilder(net)
        beam_array = builder.build_array()
        
        print(f"Built beam array with {beam_array.shape[0]} beams and {beam_array.shape[1]} columns")
        
        # Evaluate pattern
        print(f"Evaluating pattern at time t={args.time}")
        oklch_values = pattern.evaluate(beam_array, args.time)
        
        print(f"Pattern evaluation complete - generated OKLCH values with shape {oklch_values.shape}")
        print(f"Sample OKLCH values (first 5 beams):")
        for i in range(min(5, oklch_values.shape[0])):
            l, c, h = oklch_values[i]
            print(f"  Beam {i}: L={l:.3f}, C={c:.3f}, H={h:.1f}°")
        
        # Apply OKLCH values to beams and generate SVG
        print("Creating beam colors dictionary...")
        beam_colors = builder.create_beam_colors_dict(oklch_values)
        print(f"Created colors for {len(beam_colors)} beams")
        
        # Generate SVG with pattern colors
        print("Rendering SVG with pattern colors...")
        svg_elements = net.get_svg(extended=True, beam_colors=beam_colors)
        svg_content = "".join(svg_elements)
        
        # Determine output path
        if args.output:
            output_path = args.output
        else:
            output_dir = Path("output")
            output_dir.mkdir(exist_ok=True)
            config_stem = args.config.stem if args.config.name.endswith('.json') else args.config.name
            output_path = output_dir / f"{config_stem}.{pattern.name}.t{args.time}.svg"
        
        # Save SVG file
        output_path.write_text(svg_content)
        print(f"Saved pattern SVG to: {output_path}")
        
        return 0
        
    except Exception as e:
        print(f"Error in pattern sample: {e}")
        return 1


def cmd_pattern_preview(args):
    """Run WebSocket server for real-time pattern animation."""
    try:
        from luminary.patterns import get_pattern_or_select
        from luminary.config import JSONLoader
        import sys
        import subprocess
        
        # Load configuration
        config = JSONLoader.load_config(str(args.config))
        net = Net(config)
        
        # Load pattern (with interactive selection if needed)
        pattern = get_pattern_or_select(args.pattern_name)
        
        print(f"Starting Luminary Pattern Animation Server")
        print(f"Configuration: {args.config}")
        print(f"Pattern: {pattern.name}")
        print(f"Description: {pattern.description}")
        print(f"Server: http://{args.host}:{args.port}")
        print(f"Press Ctrl+C to stop")
        print("")
        
        # Import and run the webserver
        webserver_path = Path(__file__).parent / "patterns" / "webserver" / "server.py"
        
        if not webserver_path.exists():
            print(f"Error: WebSocket server not found at {webserver_path}")
            return 1
        
        # Run the webserver with current arguments
        cmd = [
            sys.executable, str(webserver_path),
            str(args.config),
            args.pattern_name or "",
            "--host", args.host,
            "--port", str(args.port),
            "--fps", str(args.fps)
        ]
        
        # Filter out empty pattern name
        if not args.pattern_name:
            cmd = cmd[:2] + cmd[3:]
        
        try:
            return subprocess.run(cmd).returncode
        except KeyboardInterrupt:
            print("\nServer stopped by user")
            return 0
        
    except Exception as e:
        print(f"Error in pattern preview: {e}")
        return 1


def cmd_pattern_run(args):
    """Stream pattern to hardware (not implemented yet)."""
    print("Pattern run command is not yet implemented.")
    print("This will be added in future releases for hardware output.")
    return 1


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
    svg_parser.add_argument(
        "--extended",
        action="store_true",
        help="Generate extended view showing individual beam subdivisions",
    )
    svg_parser.add_argument(
        "--show-vertices",
        action="store_true",
        default=False,
        help="Draw circles for triangle vertices (incenters always shown)",
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

    # Pattern subcommand
    pattern_parser = subparsers.add_parser(
        "pattern", help="Pattern operations for animated geometric patterns"
    )
    pattern_subparsers = pattern_parser.add_subparsers(dest="pattern_subcommand", help="Pattern operations")

    # Pattern sample subcommand
    sample_parser = pattern_subparsers.add_parser(
        "sample", help="Generate static SVG with pattern applied"
    )
    sample_parser.add_argument(
        "pattern_name", 
        nargs="?", 
        help="Pattern name (optional - will show selection menu if omitted)"
    )
    sample_parser.add_argument(
        "-c", "--config",
        type=Path,
        default=Path("./config.json"),
        help="JSON configuration file (default: ./config.json)"
    )
    sample_parser.add_argument(
        "-t", "--time",
        type=float,
        default=0.0,
        help="Time parameter for pattern evaluation (default: 0.0)"
    )
    sample_parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output SVG file (default: output/{config_stem}.{pattern}.svg)"
    )

    # Pattern preview subcommand
    preview_parser = pattern_subparsers.add_parser(
        "preview", help="Run WebSocket server for real-time pattern animation"
    )
    preview_parser.add_argument(
        "pattern_name",
        nargs="?",
        help="Pattern name (optional - will show selection menu if omitted)"
    )
    preview_parser.add_argument(
        "-c", "--config",
        type=Path,
        default=Path("./config.json"),
        help="JSON configuration file (default: ./config.json)"
    )
    preview_parser.add_argument(
        "--host",
        type=str,
        default="localhost",
        help="WebSocket server host (default: localhost)"
    )
    preview_parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="WebSocket server port (default: 8080)"
    )
    preview_parser.add_argument(
        "--fps",
        type=float,
        default=30.0,
        help="Animation frame rate (default: 30.0)"
    )

    # Pattern run subcommand (future implementation)
    run_parser = pattern_subparsers.add_parser(
        "run", help="Stream pattern to hardware (not implemented yet)"
    )
    run_parser.add_argument(
        "pattern_name",
        nargs="?",
        help="Pattern name (optional - will show selection menu if omitted)"
    )
    run_parser.add_argument(
        "-c", "--config",
        type=Path,
        default=Path("./config.json"),
        help="JSON configuration file (default: ./config.json)"
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
                if args.extended:
                    args.output = script_dir / "output" / f"{config_stem}.extended.svg"
                else:
                    args.output = script_dir / "output" / f"{config_stem}.svg"

            # Load Net from JSON configuration
            print(f"Loading configuration from {args.config}")
            net = Net.from_json_file(args.config)

            # Generate SVG
            print("Generating SVG...")

            # Create output directory if needed
            args.output.parent.mkdir(parents=True, exist_ok=True)

            # Save SVG
            net.save_svg(args.output, extended=args.extended, show_vertices=args.show_vertices)
            print(f"SVG saved to {args.output}")
            if args.extended:
                print("Extended mode: Generated individual beam subdivisions")

            # Print statistics
            stats = net.get_stats()
            print(f"\nGenerated SVG contains:")
            print(f"  • {stats['points']} points")
            print(f"  • {stats['triangles']} triangles")
            print(f"  • {stats['facets']} facets")
            print(f"  • {stats['geometric_lines']} geometric lines")
            print(f"  • {stats['series']} triangle series")

        except Exception as e:
            print(f"Error generating SVG: {e}")
            return 1
    elif args.command == "index":
        return generate_svg_index(args.directory)
    elif args.command == "pattern":
        return cmd_pattern(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

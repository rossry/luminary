"""Unified CLI: every verb is an adapter over the one engine (spec §16).

python -m luminary.cli serve   [--host --port --store]
python -m luminary.cli play    --lights F --pattern N [--serial P | --dry-run]
python -m luminary.cli capture --scaffold F [--params F] -o OUT
python -m luminary.cli render  --lights F --pattern N [-t S] -o OUT.svg
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

from typing import TYPE_CHECKING, Dict, Union

from luminary.comms.codec import CodecConfig

if TYPE_CHECKING:
    from luminary.engine.engine import Engine
    from luminary.geometry.lights import LightsGeometry


def _load_lights(ref: str, store_dir: Path) -> "LightsGeometry":
    from luminary.geometry.lights import LightsGeometry
    from luminary.server.store import Store

    path = Path(ref)
    if path.exists():
        return LightsGeometry.load(path)
    return LightsGeometry.load(Store(store_dir).get("lights", ref))


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from luminary.server.app import create_app

    if args.seed_demo:
        _seed(Path(args.store))
    app = create_app(store_dir=Path(args.store))
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


def _seed(store_dir: Path) -> None:
    from luminary.server.demo import seed_store

    for entry in seed_store(store_dir):
        print(f"seeded {entry['kind']:9s} {entry['id']}  {entry['name']}")


def cmd_seed(args: argparse.Namespace) -> int:
    _seed(Path(args.store))
    return 0


def cmd_play(args: argparse.Namespace) -> int:
    from luminary.engine.engine import Engine
    from luminary.patterns.registry import default_registry

    lights = _load_lights(args.lights, Path(args.store))
    pattern = default_registry().get(args.pattern)
    config = CodecConfig(budget_bytes=args.budget)
    engine = Engine(lights, pattern, fps=args.fps, codec_config=config)

    if args.serial:
        from luminary.drivers.serial_driver import SerialDriver

        ports = _parse_ports(args.serial)
        driver = SerialDriver(engine, ports, baud=args.baud)
        print(f"Streaming {pattern.name!r} to {ports} at {args.fps} fps")
        driver.run(duration=args.duration)
        _print_stats(engine)
        return 0

    # Dry run: exercise the full render+encode pipeline, report codec stats.
    duration = args.duration or 5.0
    n_frames = int(duration * args.fps)
    started = time.perf_counter()
    for i in range(n_frames):
        engine.frame(i / args.fps)
    elapsed = time.perf_counter() - started
    print(
        f"Dry run: {n_frames} frames in {elapsed:.2f}s "
        f"({n_frames / elapsed:.1f} fps capability)"
    )
    _print_stats(engine)
    return 0


def _print_stats(engine: "Engine") -> None:
    stats = engine.stats
    print(
        f"codec: {stats.frames} frames, {stats.keyframes} keyframes, "
        f"{stats.bytes_sent} bytes, {stats.ops_sent} delta ops, "
        f"{stats.bytes_per_light_frame():.2f} bytes/light-frame"
    )


def _parse_ports(spec: str) -> Union[str, Dict[int, str]]:
    """ "/dev/ttyACM0" or "0=/dev/ttyACM0,1=/dev/ttyACM1" (spec §12.2.4)."""
    if "=" not in spec:
        return spec
    ports: Dict[int, str] = {}
    for part in spec.split(","):
        controller, port = part.split("=", 1)
        ports[int(controller)] = port
    return ports


def cmd_capture(args: argparse.Namespace) -> int:
    from luminary.geometry.capture.from_scaffold import CaptureParams, capture
    from luminary.geometry.scaffold import Scaffold

    scaffold = Scaffold.load(Path(args.scaffold))
    params = CaptureParams()
    if args.params:
        params = CaptureParams.model_validate(json.loads(Path(args.params).read_text()))
    lights = capture(scaffold, params)
    lights.save(args.output)
    active = int(lights.control_mask.sum())
    print(f"Captured {lights.n} lights ({active} active) -> {args.output}")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    from luminary.engine.engine import Engine
    from luminary.patterns.registry import default_registry
    from luminary.render.svg import lights_svg

    lights = _load_lights(args.lights, Path(args.store))
    pattern = default_registry().get(args.pattern)
    engine = Engine(lights, pattern)
    markup = lights_svg(lights, colors_srgb8=engine.colors_srgb8(args.time))
    Path(args.output).write_text(markup)
    print(f"Rendered {pattern.name!r} at t={args.time} -> {args.output}")
    return 0


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(prog="luminary", description=__doc__)
    parser.add_argument("--store", default="store", help="Geometry store directory")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Run the web server (spec §15)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
    serve.add_argument(
        "--seed-demo",
        action="store_true",
        help="Load the demo geometries into the store first (idempotent)",
    )
    serve.set_defaults(func=cmd_serve)

    seed = sub.add_parser(
        "seed", help="Load demo geometries into the store (idempotent)"
    )
    seed.set_defaults(func=cmd_seed)

    play = sub.add_parser("play", help="Stream a pattern (serial or dry run)")
    play.add_argument("--lights", required=True, help="Lights file or store id")
    play.add_argument("--pattern", required=True)
    play.add_argument("--serial", help="Port, or controller=port[,...] pairs")
    play.add_argument("--baud", type=int, default=2_000_000)
    play.add_argument("--fps", type=float, default=30.0)
    play.add_argument("--budget", type=int, default=None)
    play.add_argument("--duration", type=float, default=None, help="Seconds")
    play.set_defaults(func=cmd_play)

    cap = sub.add_parser("capture", help="Scaffold -> lights geometry (spec §7.2)")
    cap.add_argument("--scaffold", required=True)
    cap.add_argument("--params", help="JSON file of CaptureParams")
    cap.add_argument("-o", "--output", required=True)
    cap.set_defaults(func=cmd_capture)

    render = sub.add_parser("render", help="Static SVG of a pattern at time t")
    render.add_argument("--lights", required=True, help="Lights file or store id")
    render.add_argument("--pattern", required=True)
    render.add_argument("-t", "--time", type=float, default=0.0)
    render.add_argument("-o", "--output", required=True)
    render.set_defaults(func=cmd_render)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())

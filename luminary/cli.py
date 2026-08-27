"""Unified CLI: every verb is an adapter over the one engine (spec §16).

python -m luminary.cli serve   [--host --port --store]
python -m luminary.cli play    --lights F --pattern N [--serial P | --dry-run]
python -m luminary.cli capture --scaffold F [--params F] -o OUT
python -m luminary.cli render  --lights F --pattern N [-t S] -o OUT.svg
python -m luminary.cli map     [--continue --trust-boards --controllers IDS --web]
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from pathlib import Path
from typing import Optional

from typing import TYPE_CHECKING, Dict, Tuple, Union

from luminary.comms.codec import CodecConfig

if TYPE_CHECKING:
    from luminary.engine.engine import Engine
    from luminary.geometry.lights import LightsGeometry
    from luminary.mapping.session import SessionCore
    from luminary.mapping.store import MappingStore


def _store_dir(explicit: Optional[str], sub: str = "") -> Path:
    """Resolve a runtime-state directory: an explicit --store is honored
    verbatim; the default is ``var/`` (joined with ``sub`` for verbs
    whose state lives in a subdirectory). A legacy ``store/`` tree is
    still used, with a nudge, until it is renamed (mv store var)."""
    if explicit is not None:
        return Path(explicit)
    root = Path("var")
    if not root.exists() and Path("store").exists():
        print("note: using legacy ./store; rename it: mv store var")
        root = Path("store")
    return root / sub if sub else root


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

    store_dir = _store_dir(args.store)
    if args.seed_demo:
        _seed(store_dir)
    app = create_app(
        store_dir=store_dir,
        allow_pattern_upload=not args.disable_pattern_upload,
        mapping_demo=not args.no_mapping_demo,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


def _seed(store_dir: Path) -> None:
    from luminary.server.demo import seed_store

    for entry in seed_store(store_dir):
        print(f"seeded {entry['kind']:9s} {entry['id']}  {entry['name']}")


def cmd_seed(args: argparse.Namespace) -> int:
    _seed(_store_dir(args.store))
    return 0


def cmd_play(args: argparse.Namespace) -> int:
    from luminary.engine.engine import Engine
    from luminary.patterns.registry import default_registry

    lights = _load_lights(args.lights, _store_dir(args.store))
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

    lights = _load_lights(args.lights, _store_dir(args.store))
    pattern = default_registry().get(args.pattern)
    engine = Engine(lights, pattern)
    markup = lights_svg(lights, colors_srgb8=engine.colors_srgb8(args.time))
    Path(args.output).write_text(markup)
    print(f"Rendered {pattern.name!r} at t={args.time} -> {args.output}")
    return 0


def build_mapping_session(
    args: argparse.Namespace,
) -> Tuple["SessionCore", "MappingStore"]:
    """Everything of ``map`` short of the surfaces, so tests can build a
    session with neither a terminal nor hardware attached."""
    from luminary.geometry.net import Net
    from luminary.geometry.pentagon import capture
    from luminary.mapping.plan import Plan
    from luminary.mapping.serial_sink import SerialSink, probe_controllers
    from luminary.mapping.session import SessionCore
    from luminary.mapping.state import initial_state, resume_state
    from luminary.mapping.store import MappingStore, SerialBoards, trust_boards

    plan = Plan.load(args.config)
    configs = Path(__file__).resolve().parents[1] / "configs"
    net_lights = capture(Net.from_json_file(configs / f"{args.config}.json"))

    ports: Dict[int, str] = {}
    if args.controllers:
        controllers = [int(part) for part in args.controllers.split(",")]
    else:
        ports = probe_controllers()
        controllers = sorted(ports)
        if not controllers:
            raise SystemExit(
                "no boards answered the identity probe; pass --controllers "
                "(e.g. --controllers 0,1,2) for a window-only run"
            )

    store = MappingStore(_store_dir(args.store, "mapping"))
    store.port_hints = dict(ports)
    if args.trust_boards:
        trust_boards(store, SerialBoards(ports), plan)
    if args.continue_ or args.trust_boards:
        state = resume_state(plan, controllers, store.load_records(plan))
    else:
        state = initial_state(plan, controllers)

    core = SessionCore(plan, net_lights, state, fps=args.fps)
    if ports:
        core.wire_sinks.append(SerialSink(ports))
    return core, store


def cmd_map(args: argparse.Namespace) -> int:
    serve_web = None
    if args.web:
        # The web surface ships separately; the TUI must not require it.
        try:
            serve_web = importlib.import_module("luminary.mapping.web").serve_mapping
        except (ImportError, AttributeError):
            print(
                "web surface not present: luminary.mapping.web is not in this "
                "checkout; run without --web for the terminal surface",
                file=sys.stderr,
            )
            return 2
    try:
        core, store = build_mapping_session(args)
    except NotImplementedError as exc:
        print(exc, file=sys.stderr)  # --trust-boards before the firmware transport
        return 2
    try:
        if serve_web is not None:
            serve_web(core, store, args.host, args.port)
        else:
            try:
                from luminary.mapping.tui import run_tui
            except ImportError:  # termios: the TUI needs a POSIX terminal
                print(
                    "the mapping TUI needs a POSIX terminal; use --web",
                    file=sys.stderr,
                )
                return 2
            run_tui(core, store, args.fps)
        return 0
    finally:
        for sink in core.wire_sinks:
            close = getattr(sink, "close", None)
            if callable(close):
                close()


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(prog="luminary", description=__doc__)
    parser.add_argument(
        "--store", default=None, help="Runtime state directory (default: var)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Run the web server (spec §15)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
    serve.add_argument(
        "--seed-demo",
        action="store_true",
        help="Load the demo geometries into the store first (idempotent)",
    )
    serve.add_argument(
        "--disable-pattern-upload",
        action="store_true",
        help="403 POST /api/patterns; patterns come from the repo only "
        "(shared deployments, docs/deploy.md)",
    )
    serve.add_argument(
        "--no-mapping-demo",
        action="store_true",
        help="Don't mount the hardware-free mapping tutorial at /demo/mapping",
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

    mapping = sub.add_parser(
        "map", help="Interactive deployment mapping (plan/mapping/DESCRIPTION.md)"
    )
    mapping.add_argument(
        "--store", default=None, help="Mapping YAML directory (default: var/mapping)"
    )
    mapping.add_argument(
        "--config",
        default="4A-33",
        help="Net config name (default: 4A-33, the production net)",
    )
    mapping.add_argument(
        "--continue",
        dest="continue_",
        action="store_true",
        help="Resume from saved records (the progress markers)",
    )
    mapping.add_argument(
        "--trust-boards",
        action="store_true",
        help="Replace local files with the boards' stored mappings first "
        "(prior local copies kept as dated backups)",
    )
    mapping.add_argument(
        "--controllers",
        help="Comma-separated controller ids; overrides probing (window-only runs)",
    )
    mapping.add_argument("--fps", type=float, default=30.0)
    mapping.add_argument(
        "--web", action="store_true", help="Serve the web surface instead of the TUI"
    )
    mapping.add_argument("--host", default="127.0.0.1", help="--web bind host")
    mapping.add_argument("--port", type=int, default=8080, help="--web bind port")
    mapping.set_defaults(func=cmd_map)

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

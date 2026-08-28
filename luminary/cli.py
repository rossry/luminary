"""Unified CLI: every verb is an adapter over the one engine (spec §16).

python -m luminary.cli serve   [--host --port --store]
python -m luminary.cli play    --lights F --pattern N [--serial P | --dry-run]
python -m luminary.cli capture --scaffold F [--params F] -o OUT
python -m luminary.cli render  --lights F --pattern N [-t S] -o OUT.svg
python -m luminary.cli map     [--continue --trust-boards --controllers IDS --web]
python -m luminary.cli boards  [--json --all-ports --no-register]
python -m luminary.cli flash   [--controller N --max-per-strip N --build-only]
python -m luminary.cli geometry [--config NAME --partial -o OUT]
python -m luminary.cli show    --lights F --pattern N [--serial P --host --port]
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


# One resolver for every entrypoint (luminary/statedir.py): --store is
# honored verbatim; the default is var/, which ships in the repo
# (var/.gitkeep), so no existence or fallback logic exists anywhere.
from luminary.statedir import runtime_state_dir as _store_dir


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


def cmd_boards(args: argparse.Namespace) -> int:
    """Inventory the boards on USB, and record the ones that are real."""
    from datetime import datetime, timezone

    from luminary.boards import discovery
    from luminary.boards.registry import BoardRegistry

    candidates = discovery.discover(all_ports=args.all_ports, timeout=args.timeout)
    boards = [c for c in candidates if c.is_board]
    duplicates = discovery.duplicate_controllers(candidates)

    if args.json:
        print(
            json.dumps(
                {
                    "boards": [
                        {
                            "controller": c.controller,
                            "port": c.device,
                            "usb": c.vidpid(),
                            "usb_serial": c.usb_serial,
                            "description": c.description,
                        }
                        for c in boards
                    ],
                    "other": [
                        {
                            "port": c.device,
                            "status": c.status,
                            "usb": c.vidpid(),
                            "detail": c.detail,
                        }
                        for c in candidates
                        if not c.is_board
                    ],
                    "duplicate_controllers": duplicates,
                },
                indent=2,
            )
        )
    else:
        if boards:
            print(f"{len(boards)} board(s):")
            for c in sorted(boards, key=lambda c: (c.controller or 0)):
                serial_note = f"  usb-serial {c.usb_serial}" if c.usb_serial else ""
                print(
                    f"  controller {c.controller}  {c.device}  "
                    f"[{c.vidpid()}] {c.description}{serial_note}"
                )
        else:
            print("no boards found")
        others = [c for c in candidates if not c.is_board]
        if others and args.verbose:
            print("\nother USB devices considered:")
            for c in others:
                print(f"  {c.status:12s} {c.device}  [{c.vidpid()}]  {c.detail}")
        elif others:
            skipped = sum(1 for c in others if c.status == discovery.FOREIGN)
            notable = [c for c in others if c.status != discovery.FOREIGN]
            for c in notable:
                print(f"\n  {c.status}: {c.device}  [{c.vidpid()}]\n    {c.detail}")
            if skipped:
                print(f"\n({skipped} other USB device(s) skipped; -v to list)")

    if duplicates:
        print("\nWARNING: controller id claimed by more than one board:")
        for controller, ports in sorted(duplicates.items()):
            print(f"  controller {controller}: {', '.join(ports)}")
        print("  Both address the same lights. Re-flash one with a distinct id.")

    if args.no_register or not boards:
        return 1 if duplicates else 0

    registry = BoardRegistry(_store_dir(args.store)).load()
    when = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for c in boards:
        if c.controller is not None:
            registry.register(c.controller, c.device, c.usb_serial, when)
    path = registry.save()
    print(f"\nregistered {len(boards)} board(s) -> {path}")
    return 1 if duplicates else 0


def cmd_flash(args: argparse.Namespace) -> int:
    """Build and flash firmware, then prove each board came back."""
    from luminary.boards import discovery
    from luminary.boards.flash import flash_board, targets_from
    from luminary.boards.registry import BoardRegistry

    registry = BoardRegistry(_store_dir(args.store)).load()
    candidates = discovery.discover(timeout=args.timeout)

    if args.controller is not None:
        targets = [args.controller]
    else:
        targets = targets_from(registry.ports(), candidates)
    if not targets:
        print(
            "no boards to flash: run `luminary boards` first, pass "
            "--controller N, or hold BOOTSEL while plugging a board in",
            file=sys.stderr,
        )
        return 2

    live = discovery.boards_by_controller(candidates)
    failures = 0
    for controller in targets:
        result = flash_board(
            controller,
            port=live.get(controller) or registry.ports().get(controller),
            max_per_strip=args.max_per_strip,
            color_order=args.color_order,
            verify=not args.no_verify,
            log=sys.stdout,
        )
        mark = "ok" if result.ok else "FAILED"
        print(f"controller {result.controller}: {mark} — {result.detail}")
        if not result.ok:
            failures += 1
    return 1 if failures else 0


def cmd_geometry(args: argparse.Namespace) -> int:
    """Mapping records -> the geometry the installation actually has."""
    from luminary.geometry.net import Net
    from luminary.geometry.pentagon.mapped import (
        MappingIncompleteError,
        capture_mapped,
    )
    from luminary.mapping.plan import Plan
    from luminary.mapping.store import MappingStore

    plan = Plan.load(args.config)
    store = MappingStore(_store_dir(args.store, "mapping"))
    records = store.load_records(plan)
    configs = Path(__file__).resolve().parents[1] / "configs"
    net = Net.from_json_file(configs / f"{args.config}.json")

    try:
        lights = capture_mapped(net, plan, records, strict=not args.partial)
    except MappingIncompleteError as exc:
        print(f"{exc}\n(--partial builds what is mapped so far)", file=sys.stderr)
        return 2

    per = {c: len(lights.active_rows_for_controller(c)) for c in lights.controllers}
    print(f"{lights.n} lights across controllers {lights.controllers}")
    for controller, count in sorted(per.items()):
        print(f"  controller {controller}: {count} active")

    if args.output:
        lights.save(args.output)
        print(f"-> {args.output}")
        return 0

    from luminary.server.store import Store

    doc_id = Store(_store_dir(args.store)).save("lights", lights.to_file_dict())
    print(f"-> store id {doc_id}   (luminary show --lights {doc_id} --pattern ...)")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    """Stream to the boards and mirror the same bytes to a preview page."""
    import asyncio

    import uvicorn

    from luminary.boards import discovery
    from luminary.boards.registry import BoardRegistry
    from luminary.drivers.broadcast import BroadcastSession
    from luminary.engine.engine import Engine
    from luminary.patterns.registry import default_registry
    from luminary.server.app import create_app

    store_dir = _store_dir(args.store)
    lights = _load_lights(args.lights, store_dir)
    pattern = default_registry().get(args.pattern)
    engine = Engine(
        lights,
        pattern,
        fps=args.fps,
        codec_config=CodecConfig(budget_bytes=args.budget),
    )

    if args.serial:
        ports = _parse_ports(args.serial)
        if isinstance(ports, str):
            controllers = lights.controllers
            if len(controllers) != 1:
                print(
                    f"geometry spans controllers {controllers}; pass "
                    "--serial 0=/dev/ttyACM0,1=/dev/ttyACM1",
                    file=sys.stderr,
                )
                return 2
            ports = {controllers[0]: ports}
    else:
        # Registered boards first, re-probed so a moved port is corrected;
        # the registry stores hints, never identities.
        ports = discovery.boards_by_controller(discovery.discover())
        if not ports:
            ports = BoardRegistry(store_dir).load().ports()
        if not ports:
            print(
                "no boards found: run `luminary boards`, or pass --serial",
                file=sys.stderr,
            )
            return 2

    missing = [c for c in lights.controllers if c not in ports]
    if missing:
        print(
            f"warning: geometry needs controller(s) {missing} with no port; "
            "those lights will stay dark",
            file=sys.stderr,
        )

    def factory(loop: "asyncio.AbstractEventLoop") -> BroadcastSession:
        session = BroadcastSession(
            engine, ports, loop=loop, baud=args.baud, lights_id=args.lights
        )
        return session

    app = create_app(
        store_dir=store_dir,
        allow_pattern_upload=False,
        broadcast_factory=factory,
    )
    print(
        f"streaming {pattern.name!r} to {ports} at {args.fps} fps\n"
        f"preview: http://{args.host}:{args.port}/preview"
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


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
        if not ports:
            # Fall back to what `luminary boards` registered. The ports there
            # are hints, not identities, so this only helps when the boards
            # are present but momentarily unprobeable -- it never invents a
            # board that is not on the bus.
            from luminary.boards.registry import BoardRegistry

            ports = BoardRegistry(_store_dir(args.store)).load().ports()
        controllers = sorted(ports)
        if not controllers:
            raise SystemExit(
                "no boards answered the identity probe; run `luminary boards` "
                "to see what is on USB, or pass --controllers (e.g. "
                "--controllers 0,1,2) for a window-only run"
            )

    store = MappingStore(_store_dir(args.store, "mapping"))
    store.port_hints = dict(ports)
    if args.trust_boards:
        trust_boards(store, SerialBoards(ports), plan)
    records = store.load_records(plan)
    if args.continue_ or args.trust_boards:
        # --continue skips ahead to the first slot never recorded.
        state = resume_state(plan, controllers, records)
    else:
        # Default: walk from the beginning, but pre-filled from the saved
        # records, so every step that is already right is a single enter.
        state = initial_state(plan, controllers, records)

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

    boards = sub.add_parser(
        "boards", help="Find, verify, and register the Scorpio boards on USB"
    )
    boards.add_argument(
        "--json", action="store_true", help="Machine-readable inventory"
    )
    boards.add_argument(
        "-v", "--verbose", action="store_true", help="List every device considered"
    )
    boards.add_argument(
        "--all-ports",
        action="store_true",
        help="Probe ports that do not carry the Scorpio USB identity too",
    )
    boards.add_argument(
        "--no-register",
        action="store_true",
        help="Report only; don't write boards.yaml",
    )
    boards.add_argument("--timeout", type=float, default=1.5, help="Probe seconds")
    boards.set_defaults(func=cmd_boards)

    flash = sub.add_parser(
        "flash", help="Build and flash firmware, then verify the board answers"
    )
    flash.add_argument(
        "--controller", type=int, default=None, help="One id (default: all registered)"
    )
    flash.add_argument(
        "--max-per-strip",
        type=int,
        default=None,
        help="LUMINARY_MAX_PER_STRIP: set to the longest strip installed",
    )
    flash.add_argument(
        "--color-order", default=None, help="LUMINARY_COLOR_ORDER (default NEO_GRB)"
    )
    flash.add_argument(
        "--no-verify", action="store_true", help="Skip the post-flash identity probe"
    )
    flash.add_argument("--timeout", type=float, default=1.5, help="Probe seconds")
    flash.set_defaults(func=cmd_flash)

    show = sub.add_parser(
        "show", help="Stream to the boards and mirror it to a preview page"
    )
    show.add_argument("--lights", required=True, help="Lights file or store id")
    show.add_argument("--pattern", required=True)
    show.add_argument(
        "--serial", help="Port, or controller=port[,...]; default: registered boards"
    )
    show.add_argument("--baud", type=int, default=2_000_000)
    show.add_argument("--fps", type=float, default=30.0)
    show.add_argument("--budget", type=int, default=None)
    show.add_argument("--host", default="127.0.0.1")
    show.add_argument("--port", type=int, default=8080)
    show.set_defaults(func=cmd_show)

    geometry = sub.add_parser(
        "geometry", help="Build the deployed geometry from the mapping records"
    )
    geometry.add_argument(
        "--config", default="4A-33", help="Net config name (default: 4A-33)"
    )
    geometry.add_argument(
        "--partial",
        action="store_true",
        help="Build what is mapped so far; unmapped panels stay dark",
    )
    geometry.add_argument(
        "-o", "--output", default=None, help="Write a file instead of the store"
    )
    geometry.set_defaults(func=cmd_geometry)

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

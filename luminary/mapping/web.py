"""Web adapters for the mapping session: mirror window, control, tutorial.

Design: plan/mapping/DESCRIPTION.md (mirror mode; the web/demo surface).
This is the mapping tool's *own* FastAPI app: a live mapping session runs
at the base station as its own process (:func:`serve_mapping`), and the
hardware-free tutorial (:func:`serve_demo`,
``python -m luminary.mapping.web``) is the same app around a scrambled
fake build. The main pattern server mounts that tutorial at
``/demo/mapping`` (``luminary.server.app``); the pages and client JS
resolve every URL relative to the page, so the app serves identically at
any mount prefix.

Light data is wire-codec-only (spec §1.3.1): the stream sockets carry
SESSION / KEYFRAME / DELTA bytes, decoded in the browser by the standard
JS decoder; JSON moves only control events and state snapshots.

Join/rebuild semantics: a socket that connects receives the current
SESSION frames immediately and a keyframe is requested, so it is in sync
at the very next tick. When the mapping state changes, ``SessionCore``
rebuilds fresh engines — their first tick emits a keyframe — and the
``on_state_change`` hook here forwards the new SESSION frames to every
connected stream socket first, so consumers of either stream resync at
every rebuild/keyframe by construction. Frames are handed to per-socket
``asyncio.Queue``s via ``call_soon_threadsafe``: sinks may be invoked
from the tick task or from another thread (a TUI driving the same core)
and the actual sends always happen on the socket's event loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Set

import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from luminary.engine.engine import Engine
from luminary.mapping.plan import Plan
from luminary.mapping.session import SessionCore
from luminary.mapping.state import Event, MappingState, initial_state, resume_state
from luminary.patterns.util import seeded_random
from luminary.render import projection

_CONFIGS = Path(__file__).resolve().parents[2] / "configs"
_STATIC = Path(__file__).resolve().parents[1] / "server" / "static"
_IDLE_POLL = 0.25  # seconds between viewer checks while the ticker idles

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- snapshots


def state_snapshot(state: MappingState, plan: Plan) -> Dict[str, Any]:
    """JSON-safe snapshot of the mapping state — everything a HUD needs."""
    unit = plan.units[state.board_cursor]
    panels = plan.panels[unit]
    panel = panels[min(state.panel_cursor, len(panels) - 1)]
    boards: Dict[str, Any] = {}
    locked = 0
    mapped = 0
    for v in plan.units:
        board = state.boards[v]
        if board.controller_id is not None:
            locked += 1
        mapped += len(board.channels)
        boards[str(v)] = {
            "controller_id": board.controller_id,
            "channels": {
                str(ch): {
                    "face": list(rec.face),
                    "winding": rec.winding,
                    "density": rec.density,
                }
                for ch, rec in sorted(board.channels.items())
            },
        }
    return {
        "stage": state.stage,
        "board_cursor": state.board_cursor,
        "panel_cursor": state.panel_cursor,
        "unit_vertex": unit,
        "face": list(panel.face),
        "tri_index": panel.tri_index,
        "candidate_controller": state.candidate_controller,
        "candidate_channel": state.candidate_channel,
        "candidate_winding": state.candidate_winding,
        "candidate_density": state.candidate_density,
        "controllers": list(state.controllers),
        "unassigned_controllers": state.unassigned_controllers(),
        "free_channels": state.free_channels(plan),
        "boards": boards,
        "progress": {
            "boards_locked": locked,
            "boards_total": len(plan.units),
            "panels_mapped": mapped,
            "panels_total": plan.n_panels,
        },
    }


def plan_json(core: SessionCore) -> Dict[str, Any]:
    """The plan as JSON: units, per-unit panels, and each panel's
    serpentine strip references — per density, the reference net light
    (an index into the layout's lights, which are in the same row
    order) for each hypothesis LED along the ccw path; cw is the same
    list reversed. The demo mockup paints decoded strips through
    exactly these references — the same bridge the wire renderer uses
    (``SessionCore.strip_refs``), so the mockup cannot diverge either."""
    plan = core.plan
    return {
        "net_name": plan.net_name,
        "units": list(plan.units),
        "n_panels": plan.n_panels,
        "panels": {
            str(unit): [
                {
                    "face": list(p.face),
                    "tri_index": p.tri_index,
                    "corner_vertex": p.corner_vertex,
                    "corner_xy": [float(p.corner_xy[0]), float(p.corner_xy[1])],
                    "refs": {
                        "180": core.strip_refs(p, 180, "ccw").tolist(),
                        "360": core.strip_refs(p, 360, "ccw").tolist(),
                    },
                }
                for p in plan.panels[unit]
            ]
            for unit in plan.units
        },
    }


# --------------------------------------------------------------- demo truth


def build_demo_truth(plan: Plan, seed: str) -> Dict[str, Any]:
    """A seeded scramble of the physical build, for the tutorial.

    Deterministic per ``seed`` (via :func:`seeded_random`, so it is stable
    for a server run and across requests): a permutation assigning each
    fake controller id to a physical cluster (data unit), a per-board
    permutation assigning that unit's panels to channels, and random
    winding / density per panel — exactly the four unknowns the mapping
    sequence resolves.
    """
    n = len(plan.units)
    ids = list(range(n))
    probe_order = np.argsort(seeded_random(f"{seed}-probe", n))
    controllers = [ids[int(i)] for i in probe_order]
    unit_perm = np.argsort(seeded_random(f"{seed}-units", n))
    boards: Dict[str, Any] = {}
    for cid in ids:
        unit = plan.units[int(unit_perm[cid])]
        panels = plan.panels[unit]
        chan_perm = np.argsort(seeded_random(f"{seed}-channels-{cid}", 8))
        winding_r = seeded_random(f"{seed}-winding-{cid}", len(panels))
        density_r = seeded_random(f"{seed}-density-{cid}", len(panels))
        channels: Dict[str, Any] = {}
        for j, panel in enumerate(panels):
            channels[str(int(chan_perm[j]))] = {
                "tri_index": panel.tri_index,
                "face": list(panel.face),
                "winding": "cw" if winding_r[j] < 0.5 else "ccw",
                "density": 360 if density_r[j] < 0.5 else 180,
            }
        boards[str(cid)] = {"unit_vertex": unit, "channels": channels}
    return {"seed": seed, "controllers": controllers, "boards": boards}


# ------------------------------------------------------------------ the app


class _LoopQueue:
    """A per-socket queue fed from any thread, drained on the socket's loop.

    Doubles as a ``FrameSink``: calling it with a frame list schedules the
    enqueue via ``call_soon_threadsafe``, so ``core.tick`` (tick task) and
    ``core.apply`` (control handler, or a TUI thread) never touch the
    socket directly.
    """

    def __init__(self) -> None:
        self.queue: "asyncio.Queue[Any]" = asyncio.Queue()
        self.loop = asyncio.get_running_loop()

    def put(self, item: Any) -> None:
        # A closed loop (server shutting down under a TUI thread's apply)
        # just drops the item — the socket it fed is gone anyway.
        with contextlib.suppress(RuntimeError):
            self.loop.call_soon_threadsafe(self.queue.put_nowait, item)

    def __call__(self, frames: List[bytes]) -> None:
        if frames:
            self.put(list(frames))


class _Disconnect(Exception):
    pass


def create_mapping_app(
    core: SessionCore,
    store: Any = None,
    *,
    demo_truth: Optional[Dict[str, Any]] = None,
    run_ticker: bool = True,
    root_page: str = "window",
    allow_reset: bool = False,
) -> FastAPI:
    """Build the mapping web app around a running :class:`SessionCore`.

    ``store`` is duck-typed (the CLI's board store, or None): when present,
    ``store.save_state(core.state, core.plan)`` runs on every state change.
    ``demo_truth`` enables ``/api/mapping/demo-truth`` for the tutorial.
    ``run_ticker=False`` skips the frame clock (tests drive ``core.tick``).
    ``root_page`` picks what ``/`` serves — ``"window"`` for a base
    station, ``"demo"`` for the mounted tutorial; both pages always stay
    reachable at ``/window`` and ``/demo``. ``allow_reset`` arms the
    control event ``reset`` (start the mapping over: clear the store's
    records, back to a fresh ports stage) — the tutorial only; a real
    session must never lose its records to a stray click.
    """
    plan_doc = plan_json(core)
    assert core.window_engine is not None  # rebuild() always constructs it
    layout_doc = projection.lights_layout(core.window_engine.lights)

    # Stream sinks owned by this app (a subset of core.*_sinks: the core may
    # also carry serial sinks registered by the CLI adapters).
    my_sinks: Dict[str, Set[_LoopQueue]] = {"window": set(), "wire": set()}
    control_queues: Set[_LoopQueue] = set()

    def _snapshot_text() -> str:
        return json.dumps({"state": state_snapshot(core.state, core.plan)})

    def _push_state_all() -> None:
        text = _snapshot_text()
        for q in list(control_queues):
            q.put(text)

    def _on_state_change(_new: MappingState) -> None:
        # Persist first, then restart this app's stream consumers with the
        # rebuilt engines' SESSION frames (their first tick emits a
        # keyframe), then refresh every HUD.
        if store is not None:
            store.save_state(core.state, core.plan)
        session = core.session_frames()
        for stream in ("window", "wire"):
            for sink in list(my_sinks[stream]):
                sink(session[stream])
        _push_state_all()

    core.on_state_change.append(_on_state_change)

    async def _ticker() -> None:
        loop = asyncio.get_running_loop()
        interval = 1.0 / core.fps
        start = loop.time()
        next_tick = start
        while True:
            if not (core.window_sinks or core.wire_sinks or control_queues):
                # Nobody is consuming frames — no sockets here and no
                # serial/TUI sinks on the core — so idle instead of
                # simulating at full fps (the tutorial mounts on the shared
                # pattern server). A joiner gets SESSION on accept and is
                # synced by the first tick after this poll notices it.
                await asyncio.sleep(_IDLE_POLL)
                next_tick = loop.time()
                continue
            try:
                core.tick(loop.time() - start)
            except Exception:  # keep the clock alive through a render bug
                logger.exception("mapping tick failed")
            next_tick += interval
            delay = next_tick - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                next_tick = loop.time()  # fell behind; don't spiral
                await asyncio.sleep(0)

    @asynccontextmanager
    async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(_ticker()) if run_ticker else None
        yield
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="Luminary Mapping", version="2.1", lifespan=_lifespan)
    app.state.core = core
    app.state.demo_truth = demo_truth

    # ------------------------------------------------------------- pages

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        page = "mapping-demo.html" if root_page == "demo" else "mapping.html"
        return (_STATIC / page).read_text()

    @app.get("/window", response_class=HTMLResponse)
    def window_page() -> str:
        return (_STATIC / "mapping.html").read_text()

    @app.get("/demo", response_class=HTMLResponse)
    def demo() -> str:
        return (_STATIC / "mapping-demo.html").read_text()

    # --------------------------------------------------------------- REST

    @app.get("/api/mapping/layout")
    def layout() -> JSONResponse:
        return JSONResponse(
            {
                "layout": layout_doc,
                "plan": plan_doc,
                "state": state_snapshot(core.state, core.plan),
            }
        )

    @app.get("/api/mapping/demo-truth")
    def get_demo_truth() -> JSONResponse:
        if demo_truth is None:
            raise HTTPException(
                404,
                detail="no demo truth on this server — start the tutorial "
                "with `python -m luminary.mapping.web`",
            )
        return JSONResponse(demo_truth)

    # ------------------------------------------------------------ streams

    def _engine_for(stream: str) -> Optional[Engine]:
        return core.window_engine if stream == "window" else core.wire_engine

    async def _stream_socket(websocket: WebSocket, stream: str) -> None:
        """One viewer of the window or wire stream: SESSION now, then the
        engine's frames as they tick. A late joiner is synced by the next
        tick — its keyframe is requested here — or by the next rebuild,
        whichever comes first (see the module docstring)."""
        await websocket.accept()
        sink = _LoopQueue()
        sinks = core.window_sinks if stream == "window" else core.wire_sinks
        sinks.append(sink)
        my_sinks[stream].add(sink)
        # Queue the current SESSION frames first: no await between the sink
        # registration and here, so no tick frame (and no rebuild's push)
        # can land in the queue ahead of them.
        sink(core.session_frames()[stream])
        engine = _engine_for(stream)
        if engine is not None:
            engine.request_keyframe()

        async def _send_loop() -> None:
            while True:
                frames = await sink.queue.get()
                for frame in frames:
                    await websocket.send_bytes(frame)

        async def _receive_loop() -> None:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    raise _Disconnect()
                text = message.get("text")
                if not text:
                    continue
                try:
                    control = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if control.get("type") == "resync":
                    current = _engine_for(stream)
                    if current is not None:
                        current.request_keyframe()

        try:
            await _run_pair(_send_loop(), _receive_loop())
        finally:
            my_sinks[stream].discard(sink)
            if sink in sinks:
                sinks.remove(sink)

    @app.websocket("/api/mapping/window")
    async def window_socket(websocket: WebSocket) -> None:
        await _stream_socket(websocket, "window")

    @app.websocket("/api/mapping/wire")
    async def wire_socket(websocket: WebSocket) -> None:
        await _stream_socket(websocket, "wire")

    # ------------------------------------------------------------ control

    @app.websocket("/api/mapping/control")
    async def control_socket(websocket: WebSocket) -> None:
        await websocket.accept()
        queue = _LoopQueue()
        control_queues.add(queue)
        queue.put(_snapshot_text())  # on connect: the current state

        async def _send_loop() -> None:
            while True:
                text = await queue.queue.get()
                await websocket.send_text(text)

        async def _receive_loop() -> None:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    raise _Disconnect()
                text = message.get("text")
                if not text:
                    continue
                try:
                    body = json.loads(text)
                except json.JSONDecodeError:
                    continue
                name = str(body.get("event"))
                if name == "reset":
                    # Start over (tutorial only): the records leave the
                    # store the same way they entered it, and the fresh
                    # state broadcasts through the usual change hooks.
                    if allow_reset:
                        if store is not None:
                            store.clear_records()
                        core.reset_state(
                            initial_state(core.plan, list(core.state.controllers))
                        )
                    continue
                try:
                    event = Event(name)
                except ValueError:
                    continue
                before = core.state
                after = core.apply(event)
                # A transition already broadcast via _on_state_change; a
                # no-op event still gets a confirming push to all HUDs.
                if after is before:
                    _push_state_all()

        try:
            await _run_pair(_send_loop(), _receive_loop())
        finally:
            control_queues.discard(queue)

    app.mount("/static", StaticFiles(directory=_STATIC), name="static")
    return app


async def _run_pair(send_coro: Any, receive_coro: Any) -> None:
    """Run sender+receiver until either finishes; a disconnect is clean."""
    sender = asyncio.create_task(send_coro)
    receiver = asyncio.create_task(receive_coro)
    done, pending = await asyncio.wait(
        {sender, receiver}, return_when=asyncio.FIRST_COMPLETED
    )
    for task in pending:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    for task in done:
        exc = task.exception()
        if exc is not None and not isinstance(exc, _Disconnect):
            raise exc


# --------------------------------------------------------------- entrypoints


def serve_mapping(
    core: SessionCore,
    store: Any,
    host: str = "127.0.0.1",
    port: int = 8090,
) -> None:
    """Serve the mirror window for a live mapping session (blocking)."""
    uvicorn.run(create_mapping_app(core, store), host=host, port=port)


def create_demo_app(
    seed: str = "mapping-demo",
    *,
    store_dir: Path,
    run_ticker: bool = True,
    root_page: str = "window",
) -> FastAPI:
    """The tutorial app: plan + net capture + scrambled fake controllers,
    no hardware and no CLI involved.

    The demo's mapping state lives ONLY where a production session's
    would: a real :class:`MappingStore` at ``store_dir`` (required — a
    storeless demo would be a second, unprincipled persistence path).
    The session resumes from the store's records exactly like
    ``map --continue``, so a restarted server picks up where the last
    operator left off; the page's ↺ restart control clears the records
    and starts the sequence over. The scrambled truth is seeded, so it
    is identical across restarts and needs no persistence of its own.
    """
    from luminary.geometry.net import Net
    from luminary.geometry.pentagon import capture
    from luminary.mapping.store import MappingStore

    plan = Plan.load()
    net_lights = capture(Net.from_json_file(_CONFIGS / f"{plan.net_name}.json"))
    truth = build_demo_truth(plan, seed)
    store = MappingStore(Path(store_dir))
    state = resume_state(
        plan,
        controllers=list(truth["controllers"]),
        boards=store.load_records(plan),
    )
    core = SessionCore(plan, net_lights, state)
    return create_mapping_app(
        core,
        store=store,
        demo_truth=truth,
        run_ticker=run_ticker,
        root_page=root_page,
        allow_reset=True,
    )


def serve_demo(
    host: str = "127.0.0.1",
    port: int = 8090,
    store_dir: Path = Path("var") / "mapping-demo",
) -> None:
    """Serve the hardware-free tutorial (blocking): / mirrors the window,
    /demo is the scrambled-build training page."""
    uvicorn.run(create_demo_app(store_dir=store_dir), host=host, port=port)


if __name__ == "__main__":  # pragma: no cover — `python -m luminary.mapping.web`
    serve_demo()

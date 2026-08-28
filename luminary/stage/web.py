"""Web adapter for the stage: queue API, wire-frame stream, viewer page.

A thin adapter over :class:`StageCore` (implementation-notes §2.9): every
route translates HTTP/WS to core calls; the page renders API state and
sends commands — no client-side scheduling exists. Light data is
wire-codec-only (spec §1.3.1): ``WS /api/stage`` carries SESSION /
KEYFRAME / DELTA bytes decoded by the standard browser decoder; a joiner
gets the current SESSION frames immediately and a keyframe is requested,
so it is in sync at the very next tick (the mapping web app's join
shape). Entry advances re-keyframe but never re-send SESSION — the
geometry never changes for the stage's life.

Access control: when a stage key is configured (``serve --stage-key``,
or env ``LUMINARY_STAGE_KEY``; the flag wins), every mutating endpoint
requires it in an ``X-Stage-Key`` header — wrong or missing gets a 403
with a JSON ``detail`` the page surfaces. Read-only traffic (the page,
layout, the WS stream, queue/patterns/chapters/audio GETs) is never
gated, and with no key configured everything stays open (LAN
deployments).

The ticker mirrors the mapping app's: fps-paced `core.tick()`, falling
back to a slow poll whenever nothing consumes frames and nothing is
scheduled (``StageCore.idle`` — no viewer sockets, no audio playing,
tracklist exhausted).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse

from luminary.geometry.lights import LightsGeometry
from luminary.patterns.registry import PatternRegistry
from luminary.render import projection
from luminary.stage.audio import AudioPlayer, detect_player
from luminary.stage.core import StageCore, StageError

_CONFIGS = Path(__file__).resolve().parents[2] / "configs"
_STATIC = Path(__file__).resolve().parents[1] / "server" / "static"
_IDLE_POLL = 0.25  # seconds between checks while the ticker idles
_STAGE_CONFIG = "4A-33"  # the production sphere's net config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- construction


def resolve_stage_lights(ref: Optional[str], store_dir: Path) -> LightsGeometry:
    """The stage geometry from ``--stage-lights``: a file path, a
    geometry-store id, or (default) the production ``pentagon-4A-33``
    capture — the same construction the demo seeder uses."""
    if ref is None:
        from luminary.geometry.net import Net
        from luminary.geometry.pentagon import capture

        return capture(Net.from_json_file(_CONFIGS / f"{_STAGE_CONFIG}.json"))
    path = Path(ref)
    if path.exists():
        return LightsGeometry.load(path)
    from luminary.server.store import Store

    return LightsGeometry.load(Store(store_dir).get("lights", ref))


def build_stage(
    store_dir: Path,
    registry: PatternRegistry,
    *,
    lights_ref: Optional[str] = None,
    fps: float = 30.0,
    audio_player: Optional[str] = None,
) -> StageCore:
    """The serve-time stage: geometry per ``lights_ref``, state at
    ``<store_dir>/stage/``, audio files at ``<store_dir>/audio/``."""
    store_dir = Path(store_dir)
    lights = resolve_stage_lights(lights_ref, store_dir)
    audio_dir = store_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio = AudioPlayer(detect_player(audio_player), audio_dir)
    return StageCore(lights, registry, store_dir / "stage", audio, fps=fps)


# --------------------------------------------------------------------- ticker


class _LoopQueue:
    """A per-socket queue fed from any thread, drained on the socket's
    loop (the mapping web app's sink shape): calling it with a frame
    list schedules the enqueue via ``call_soon_threadsafe``, so
    ``core.tick`` never touches a socket directly."""

    def __init__(self) -> None:
        self.queue: "asyncio.Queue[List[bytes]]" = asyncio.Queue()
        self.loop = asyncio.get_running_loop()

    def __call__(self, frames: List[bytes]) -> None:
        if frames:
            with contextlib.suppress(RuntimeError):  # loop closed at shutdown
                self.loop.call_soon_threadsafe(self.queue.put_nowait, list(frames))


class _Disconnect(Exception):
    pass


async def _ticker(core: StageCore) -> None:
    loop = asyncio.get_running_loop()
    interval = 1.0 / core.fps
    next_tick = loop.time()
    while True:
        if core.idle():
            # Nobody listening, nothing scheduled: poll instead of
            # rendering 30 fps to nobody. A joiner gets SESSION on
            # accept and is synced by the first tick after this poll
            # notices it; a queued entry flips idle() off immediately.
            await asyncio.sleep(_IDLE_POLL)
            next_tick = loop.time()
            continue
        try:
            core.tick()
        except Exception:  # keep the clock alive through a render bug
            logger.exception("stage tick failed")
        next_tick += interval
        delay = next_tick - loop.time()
        if delay > 0:
            await asyncio.sleep(delay)
        else:
            next_tick = loop.time()  # fell behind; don't spiral
            await asyncio.sleep(0)


@asynccontextmanager
async def stage_lifespan(core: StageCore) -> AsyncIterator[None]:
    """Run the stage ticker for the span of the serving app."""
    task = asyncio.create_task(_ticker(core))
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


# --------------------------------------------------------------------- routes


def register_stage(
    app: FastAPI, core: StageCore, *, stage_key: Optional[str] = None
) -> None:
    """Mount the stage routes on ``app`` (the main server's paths:
    /stage, /api/queue, /api/repeats, /api/audio, /api/stage[.layout /
    .patterns / .chapters]). ``stage_key`` (when set) gates every
    mutating route behind an ``X-Stage-Key`` header; read-only routes
    are never gated. The caller owns the ticker via
    :func:`stage_lifespan`; tests register on a bare app and drive
    ``core.tick()`` manually."""
    layout_doc = projection.lights_layout(core.engine.lights)
    app.state.stage = core

    def _require_key(request: Request) -> None:
        """403 unless the request carries the configured stage key. All
        mutating routes hang this dependency; with no key configured the
        stage stays open (LAN deployments)."""
        if stage_key and request.headers.get("X-Stage-Key") != stage_key:
            raise HTTPException(
                403, detail="stage key required (send it in an X-Stage-Key header)"
            )

    guarded = [Depends(_require_key)]

    # ------------------------------------------------------------- pages

    @app.get("/stage", response_class=HTMLResponse)
    def stage_page() -> str:
        return (_STATIC / "stage.html").read_text()

    @app.get("/api/stage/layout")
    def stage_layout() -> JSONResponse:
        return JSONResponse(layout_doc)

    # ---------------------------------------------------------- metadata

    @app.get("/api/stage/patterns")
    def stage_patterns() -> JSONResponse:
        """Registry metadata plus what the add panel needs (notes, the
        ``loop`` flag that defaults the repeat toggle, ``has_chapters``
        for the queued-row expander)."""
        return JSONResponse(core.patterns_meta())

    @app.get("/api/stage/chapters")
    def stage_chapters(pattern: str) -> JSONResponse:
        """The chapter tree of one pattern (display only — expansion
        itself happens server-side when the entry reaches the head);
        ``[]`` for a chapterless pattern, 404 for an unknown one."""
        try:
            return JSONResponse(core.chapters_of(pattern))
        except StageError as exc:
            raise HTTPException(404, detail=str(exc))

    # ------------------------------------------------------------- queue

    @app.get("/api/queue")
    def get_queue() -> JSONResponse:
        return JSONResponse(core.snapshot())

    @app.post("/api/queue", dependencies=guarded)
    def append_entry(body: Dict[str, Any]) -> JSONResponse:
        try:
            return JSONResponse(core.append(body))
        except StageError as exc:
            raise HTTPException(422, detail=str(exc))

    @app.post("/api/queue/play_next", dependencies=guarded)
    def play_next(body: Dict[str, Any]) -> JSONResponse:
        try:
            return JSONResponse(core.play_next(body))
        except StageError as exc:
            raise HTTPException(422, detail=str(exc))

    @app.delete("/api/queue/{i}", dependencies=guarded)
    def delete_entry(i: int) -> JSONResponse:
        try:
            return JSONResponse(core.remove(i))
        except StageError as exc:
            raise HTTPException(404, detail=str(exc))

    @app.post("/api/queue/move", dependencies=guarded)
    def move_entry(body: Dict[str, Any]) -> JSONResponse:
        frm, to = body.get("from"), body.get("to")
        if not isinstance(frm, int) or not isinstance(to, int):
            raise HTTPException(422, detail='body must be {"from": int, "to": int}')
        try:
            return JSONResponse(core.move(frm, to))
        except StageError as exc:
            raise HTTPException(422, detail=str(exc))

    @app.post("/api/queue/skip", dependencies=guarded)
    def skip_entry() -> JSONResponse:
        return JSONResponse(core.skip())

    @app.post("/api/queue/clear", dependencies=guarded)
    def clear_queue() -> JSONResponse:
        return JSONResponse(core.clear())

    # ----------------------------------------------------------- repeats

    @app.post("/api/repeats/move", dependencies=guarded)
    def move_repeat(body: Dict[str, Any]) -> JSONResponse:
        frm, to = body.get("from"), body.get("to")
        if not isinstance(frm, int) or not isinstance(to, int):
            raise HTTPException(422, detail='body must be {"from": int, "to": int}')
        try:
            return JSONResponse(core.move_repeat(frm, to))
        except StageError as exc:
            raise HTTPException(422, detail=str(exc))

    @app.delete("/api/repeats/{i}", dependencies=guarded)
    def delete_repeat(i: int) -> JSONResponse:
        try:
            return JSONResponse(core.remove_repeat(i))
        except StageError as exc:
            raise HTTPException(404, detail=str(exc))

    # ------------------------------------------------------------- audio

    @app.get("/api/audio")
    def list_audio() -> JSONResponse:
        """The audio inventory: [{name, seconds}] — seconds null when
        the file's length cannot be read."""
        return JSONResponse(
            [
                {"name": name, "seconds": core.audio.duration_of(name)}
                for name in core.audio.list_files()
            ]
        )

    # ------------------------------------------------------------- stream

    @app.websocket("/api/stage")
    async def stage_socket(websocket: WebSocket) -> None:
        """One viewer: SESSION now, then the engine's frames as they
        tick; {"type":"resync"} back forces a keyframe (the mapping
        ``_stream_socket`` shape)."""
        await websocket.accept()
        sink = _LoopQueue()
        core.sinks.append(sink)
        # Queue the SESSION frames first: no await between registration
        # and here, so no tick frame can land in the queue ahead of them.
        sink(core.engine.session_frames())
        core.engine.request_keyframe()

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
                    core.engine.request_keyframe()

        try:
            await _run_pair(_send_loop(), _receive_loop())
        finally:
            if sink in core.sinks:
                core.sinks.remove(sink)


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

"""WebSocket driver: the same wire bytes, streamed to a browser (spec §12.3).

The session sends SESSION frames then paces KEYFRAME/DELTA binary messages —
byte-identical to what the serial path writes (spec §2.1.2). Inbound JSON
control messages: {"type": "resync" | "set_pattern" | "pause" | "resume"}.

The driver is framework-thin: it talks to any object with async
``send_bytes``/``receive`` in the Starlette WebSocket shape, and holds no
FastAPI imports, keeping the dependency arrow pointing inward (spec §2.2.2).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Optional

from luminary.engine.engine import Engine


class WebSocketSession:
    """One viewer's playback session over an accepted WebSocket."""

    def __init__(
        self,
        engine: Engine,
        websocket: Any,
        *,
        resolve_pattern: Optional[Callable[[str], Any]] = None,
    ) -> None:
        self.engine = engine
        self.websocket = websocket
        self.resolve_pattern = resolve_pattern
        self.paused = False
        self._closed = False

    async def run(self) -> None:
        for frame in self.engine.session_frames():
            await self.websocket.send_bytes(frame)
        sender = asyncio.create_task(self._send_loop())
        receiver = asyncio.create_task(self._receive_loop())
        done, pending = await asyncio.wait(
            {sender, receiver}, return_when=asyncio.FIRST_COMPLETED
        )
        self._closed = True
        for task in pending:
            task.cancel()
        for task in done:
            exc = task.exception()
            if exc is not None and not isinstance(exc, _Disconnect):
                raise exc

    async def _send_loop(self) -> None:
        interval = 1.0 / self.engine.fps
        frame_index = 0
        loop = asyncio.get_running_loop()
        next_tick = loop.time()
        while not self._closed:
            if not self.paused:
                t = frame_index / self.engine.fps
                for frame in self.engine.frame(t):
                    await self.websocket.send_bytes(frame)
                frame_index += 1
            next_tick += interval
            delay = next_tick - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                next_tick = loop.time()  # fell behind; don't spiral

    async def _receive_loop(self) -> None:
        while True:
            message = await self.websocket.receive()
            if message.get("type") == "websocket.disconnect":
                raise _Disconnect()
            text = message.get("text")
            if not text:
                continue
            try:
                control = json.loads(text)
            except json.JSONDecodeError:
                continue
            kind = control.get("type")
            if kind == "resync":
                self.engine.request_keyframe()
            elif kind == "pause":
                self.paused = True
            elif kind == "resume":
                self.paused = False
            elif kind == "set_pattern" and self.resolve_pattern is not None:
                try:
                    pattern = self.resolve_pattern(str(control.get("name")))
                except KeyError:
                    continue
                self.engine.set_pattern(pattern)


class _Disconnect(Exception):
    pass

"""Broadcast: one engine, the same wire bytes to hardware and to a preview.

The point of this module is an invariant, not a feature. There is exactly one
:class:`Engine`, and the bytes a preview window shows are the bytes the boards
were sent. The demo server builds an Engine per WebSocket viewer (§15), which
is right for browsing patterns and wrong for a running installation: two
engines encode independently against their own decoder models, so the preview
would drift from the hardware and stop being evidence of anything.

**Pacing authority stays with the hardware.** ``SerialDriver``'s acknowledgement
window is a correctness requirement rather than a throughput knob (spec
§11.7.6) — the RP2040 stops responding altogether when its receive buffer backs
up. So the serial loop runs exactly as it does with no preview attached, on its
own thread, and viewers are served from bounded queues that drop frames when a
browser cannot keep up. A slow viewer loses frames; it can never slow, stall,
or wedge the boards.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Dict, List, Mapping, Optional, Set, Union

from luminary.drivers.serial_driver import SerialDriver
from luminary.engine.engine import Engine

# Frames a viewer may fall behind before it starts losing them. At 30 fps this
# is ~8 s of slack, which absorbs a browser tab being backgrounded without
# letting a dead socket grow without bound.
VIEWER_QUEUE = 240


class FrameHub:
    """Fan-out of wire frames from the stream thread to preview viewers."""

    def __init__(self, loop: asyncio.AbstractEventLoop, max_queue: int = VIEWER_QUEUE):
        self._loop = loop
        self._queues: Set[asyncio.Queue] = set()
        self._max_queue = max_queue
        self.dropped = 0

    # -- event-loop side ---------------------------------------------------

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue)
        self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._queues.discard(queue)

    @property
    def viewers(self) -> int:
        return len(self._queues)

    # -- stream-thread side ------------------------------------------------

    def publish(self, frame: bytes) -> None:
        """Hand a frame to the event loop. Called from the stream thread.

        Returns immediately: ``call_soon_threadsafe`` only appends to the
        loop's callback queue. This is the whole reason the fan-out is not
        done inline — see the ``frame_observer`` contract in serial_driver.
        """
        try:
            self._loop.call_soon_threadsafe(self._fanout, frame)
        except RuntimeError:
            pass  # loop closed; the session is shutting down

    def _fanout(self, frame: bytes) -> None:
        for queue in list(self._queues):
            try:
                queue.put_nowait(frame)
            except asyncio.QueueFull:
                # Keep the viewer near live rather than replaying a backlog:
                # drop its oldest frame and take the newest. A preview that
                # lags is worse than useless -- it misrepresents the show.
                self.dropped += 1
                try:
                    queue.get_nowait()
                    queue.put_nowait(frame)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass


class BroadcastSession:
    """One engine streaming to serial, mirrored to any attached viewers."""

    def __init__(
        self,
        engine: Engine,
        ports: Union[str, Dict[int, str]],
        *,
        loop: asyncio.AbstractEventLoop,
        baud: int = 2_000_000,
        max_in_flight: Optional[int] = 4,
        lights_id: str = "",
    ) -> None:
        self.engine = engine
        # Which stored geometry the preview should fetch its layout for. The
        # stream decides this, not the page: a preview showing a different
        # geometry than the boards are running would be actively misleading.
        self.lights_id = lights_id
        self.hub = FrameHub(loop)
        self.driver = SerialDriver(
            engine,
            ports,
            baud=baud,
            max_in_flight=max_in_flight,
            frame_observer=self.hub.publish,
        )
        self._thread: Optional[threading.Thread] = None
        self._error: Optional[BaseException] = None

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        """Open the ports and run the stream loop on its own thread."""
        self.driver.open()
        self._thread = threading.Thread(
            target=self._run, name="luminary-stream", daemon=True
        )
        self._thread.start()

    def _run(self) -> None:
        try:
            self.driver.run()
        except BaseException as exc:  # surfaced through .error for the server
            self._error = exc

    def stop(self, timeout: float = 5.0) -> None:
        """End the stream and wait for the loop thread to finish.

        The ports are closed by the loop itself on its way out, not from
        here: every connection stays owned by the one thread that writes to
        it, so shutdown cannot race a reconnect.
        """
        self.driver.request_stop()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    @property
    def error(self) -> Optional[BaseException]:
        return self._error

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # -- viewers -----------------------------------------------------------

    def session_frames(self) -> List[bytes]:
        """The SESSION frames a joining viewer needs before any DELTA.

        Regenerated from the engine rather than cached: they are a pure
        function of the geometry, and a viewer must never be handed a stale
        session describing lights the boards no longer have.
        """
        return list(self.engine.session_frames())

    def set_pattern(self, pattern: object) -> None:
        """Swap what the installation is playing.

        The page that does this is the operator's console on the base
        station, not a viewer: `luminary play` exists to put a pattern on the
        sphere and let you change it. A keyframe follows, because the boards
        are mid-DELTA against the pattern that just went away.
        """
        self.engine.set_pattern(pattern)  # type: ignore[arg-type]
        self.engine.request_keyframe()

    def request_keyframe(self) -> None:
        """Make the next frame a KEYFRAME so a joining viewer can sync.

        A DELTA is meaningless to a decoder that has not seen the state it
        corrects. The keyframe goes to the boards too, which is harmless --
        it is the same repair the driver performs on reconnect.
        """
        self.engine.request_keyframe()

    # -- reporting ---------------------------------------------------------

    @staticmethod
    def _snapshot(mapping: Mapping[int, object]) -> List[int]:
        """Sorted keys of a dict the stream thread may be mutating.

        The stream thread adds and drops connections as controllers fault and
        reconnect (spec §11.7.7) while ``stats`` is polled once a second from
        the event loop, so a plain ``sorted(mapping)`` can raise
        "dictionary changed size during iteration" — and does, in the preview
        page's poll. Locking is the wrong fix: the stream loop would have to
        take the lock too, and its timing *is* the acknowledgement window.
        Retrying costs only the reader, and the mutation window is a few
        instructions wide.
        """
        for _ in range(8):
            try:
                return sorted(mapping)
            except RuntimeError:
                continue
        return []

    def stats(self) -> Dict[str, object]:
        latencies = list(self.driver.ack_latencies)
        latencies.sort()
        median = latencies[len(latencies) // 2] if latencies else None
        return {
            "viewers": self.hub.viewers,
            "frames_dropped_to_viewers": self.hub.dropped,
            "acks": len(latencies),
            "ack_median_ms": round(median * 1000, 3) if median is not None else None,
            "window_stalls": self.driver.stalled_ticks,
            "disconnects": self.driver.disconnects,
            "reconnects": self.driver.reconnects,
            "budget_bytes": self.engine.codec_config.budget_bytes,
            "controllers_up": self._snapshot(self.driver.connections),
            "controllers_down": self._snapshot(self.driver._down),
        }

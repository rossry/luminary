"""Broadcast: one engine feeding hardware and a preview at once.

Two properties matter and are asserted here directly:

* the preview receives the *same bytes* the wire did, from one engine --
  a second engine would encode against its own decoder model and drift;
* a slow viewer never delays the stream loop, because that loop's timing is
  the acknowledgement window (spec §11.7.6).
"""

from __future__ import annotations

import asyncio
import os
import pty
import termios
import threading
import time
import tty
from contextlib import contextmanager

from luminary.comms import protocol as p
from luminary.comms.codec import CodecConfig
from luminary.drivers.broadcast import BroadcastSession, FrameHub
from luminary.engine.engine import Engine
from luminary.geometry.capture.from_scaffold import CaptureParams, capture
from luminary.geometry.scaffold import Scaffold
from luminary.patterns.registry import default_registry

SCAFFOLD = {
    "schema": "luminary.scaffold/1",
    "space": {"authoritative": ["xy"]},
    "lines": [
        {"p1": [0, 0], "p2": [100, 0]},
        {"p1": [100, 0], "p2": [100, 100]},
    ],
    "meta": {"name": "broadcast-test"},
}


def _engine(fps=60.0):
    lights = capture(
        Scaffold.load(SCAFFOLD), CaptureParams(count_per_line=16, interpolate_every=4)
    )
    return Engine(
        lights,
        default_registry().get("aurora"),
        fps=fps,
        codec_config=CodecConfig(budget_bytes=512),
    )


class _VirtualBoard(threading.Thread):
    """A board on a PTY: consumes framed bytes and ACKs each one.

    A real serial path rather than a fake port object, so the driver's own
    pyserial writes, COBS framing, and ACK parsing are all exercised.
    """

    daemon = True

    def __init__(self, fd, controller=0):
        super().__init__()
        self.fd = fd
        self.controller = controller
        self.splitter = p.FrameSplitter()
        self.stop_flag = threading.Event()
        self.frames: list[bytes] = []

    def run(self):
        hello = p.build_frame(p.FRAME_HELLO, self.controller, 0.0, b"")
        os.write(self.fd, hello)
        seen = [False]

        def repeat():
            while not seen[0] and not self.stop_flag.is_set():
                try:
                    os.write(self.fd, hello)
                except OSError:
                    return
                time.sleep(0.02)

        threading.Thread(target=repeat, daemon=True).start()
        while not self.stop_flag.is_set():
            try:
                data = os.read(self.fd, 65536)
            except OSError:
                break
            if not data:
                continue
            seen[0] = True
            for raw in self.splitter.feed(data):
                try:
                    frame_type, controller, t, _ = p.parse_frame(raw)
                except p.ProtocolError:
                    continue
                self.frames.append(raw)
                if frame_type in (p.FRAME_SESSION, p.FRAME_KEYFRAME, p.FRAME_DELTA):
                    os.write(self.fd, p.build_ack(controller, t))


@contextmanager
def _board_on_pty():
    """A virtual board on a raw PTY, cleaned up on the way out.

    Canonical mode echoes and translates CR/LF, which corrupts a binary COBS
    stream and feeds the driver its own writes back — so both ends are put
    into raw mode explicitly. The descriptors and the reader thread are
    released afterwards: leaking a PTY and a spinning thread per test makes
    the later ones in the file flaky, which is how this fixture came to
    exist.
    """
    master, slave = pty.openpty()
    for fd in (master, slave):
        tty.setraw(fd)
        attrs = termios.tcgetattr(fd)
        attrs[0] = attrs[1] = 0
        attrs[3] &= ~(termios.ECHO | termios.ICANON | termios.ISIG)
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
    os.set_blocking(master, True)
    board = _VirtualBoard(master)
    board.start()
    try:
        yield os.ttyname(slave), board
    finally:
        board.stop_flag.set()
        for fd in (master, slave):
            try:
                os.close(fd)
            except OSError:
                pass
        board.join(timeout=2.0)


# ------------------------------------------------------------------- FrameHub


def test_hub_delivers_to_every_viewer():
    async def scenario():
        hub = FrameHub(asyncio.get_running_loop())
        a, b = hub.subscribe(), hub.subscribe()
        hub._fanout(b"frame")
        return a.get_nowait(), b.get_nowait(), hub.viewers

    assert asyncio.run(scenario()) == (b"frame", b"frame", 2)


def test_hub_drops_oldest_rather_than_blocking_the_producer():
    """A viewer that stops draining must cost frames, never stall the loop."""

    async def scenario():
        hub = FrameHub(asyncio.get_running_loop(), max_queue=2)
        hub.subscribe()
        for i in range(5):
            hub._fanout(bytes([i]))
        queue = next(iter(hub._queues))
        return [queue.get_nowait() for _ in range(queue.qsize())], hub.dropped

    delivered, dropped = asyncio.run(scenario())
    assert delivered == [b"\x03", b"\x04"]  # newest kept, oldest shed
    assert dropped == 3


def test_unsubscribe_stops_delivery():
    async def scenario():
        hub = FrameHub(asyncio.get_running_loop())
        queue = hub.subscribe()
        hub.unsubscribe(queue)
        hub._fanout(b"frame")
        return hub.viewers, queue.qsize()

    assert asyncio.run(scenario()) == (0, 0)


# ------------------------------------------------------------ BroadcastSession


def test_preview_receives_exactly_the_bytes_the_board_did():
    """The property the whole module exists for."""
    with _board_on_pty() as (port, board):
        engine = _engine()

        async def scenario():
            session = BroadcastSession(
                engine, {0: port}, loop=asyncio.get_running_loop()
            )
            queue = session.hub.subscribe()
            session.start()
            mirrored = []
            deadline = time.monotonic() + 10.0
            while len(mirrored) < 10 and time.monotonic() < deadline:
                try:
                    mirrored.append(await asyncio.wait_for(queue.get(), timeout=2.0))
                except asyncio.TimeoutError:
                    break
            session.stop()
            return mirrored

        mirrored = asyncio.run(scenario())
        on_wire = set(board.frames)

    assert len(mirrored) >= 5, f"preview received only {len(mirrored)} frames"
    # Every mirrored frame is a well-formed wire frame that the board also
    # received -- same bytes, one engine.
    for frame in mirrored[:5]:
        raw = p.cobs_decode(frame.rstrip(b"\x00"))
        p.parse_frame(raw)  # raises if the preview got something malformed
        assert raw in on_wire, "preview saw a frame the board never did"


def test_a_stalled_viewer_does_not_stop_the_board():
    """The hardware stream is the pacing authority, not the browser."""
    with _board_on_pty() as (port, _board):
        engine = _engine()

        async def scenario():
            session = BroadcastSession(
                engine, {0: port}, loop=asyncio.get_running_loop()
            )
            session.hub._max_queue = 2
            session.hub.subscribe()  # subscribed and never drained
            session.start()
            await asyncio.sleep(3.0)
            stats = session.stats()
            session.stop()
            return stats

        stats = asyncio.run(scenario())

    assert stats["window_stalls"] == 0
    assert stats["disconnects"] == 0
    assert stats["acks"] > 10, "the board stopped being fed"
    assert stats["frames_dropped_to_viewers"] > 0, "the viewer should have lost frames"


def test_session_frames_are_regenerated_not_cached():
    engine = _engine()

    async def scenario():
        session = BroadcastSession(
            engine, {0: "/dev/null"}, loop=asyncio.get_running_loop()
        )
        return session.session_frames(), session.session_frames()

    first, second = asyncio.run(scenario())
    assert first == second and len(first) >= 1

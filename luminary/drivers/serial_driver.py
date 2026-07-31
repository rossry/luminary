"""Serial driver: engine frames -> Scorpio over USB-CDC (spec §12.2).

One process, one engine, one port per controller (spec §12.2.4): each frame's
header names its controller and the driver routes it to that controller's
port. Inbound bytes are scanned for RESYNC/HELLO/ACK frames (spec §13.3). The
driver contains no color or codec logic (spec §12.1.1).

Outbound frames are paced by an acknowledgement window (spec §11.7.6). This
is not an optimization: the RP2040's USB stack does not apply backpressure
when its receive buffer backs up, it stops responding altogether, and
recovering from that needs a physical replug. The window bounds how far ahead
of the board the sender may run so that state is never reached.
"""

from __future__ import annotations

import struct
import time
from collections import deque
from typing import Deque, Dict, Iterator, List, Optional, Tuple, Union

import serial as pyserial

from luminary.comms import protocol as p
from luminary.engine.engine import Engine


def budget_for_baud(baud: int, fps: float, utilization: float = 0.8) -> int:
    """Per-frame byte budget from the link rate (spec §11.6.1).

    10 bits per byte on the wire (8N1); ``utilization`` leaves headroom for
    COBS overhead, handshake traffic, and OS jitter.
    """
    return max(64, int(baud / 10.0 / fps * utilization))


class SerialDriver:
    """Streams one engine to one or more serial ports, paced at engine.fps."""

    def __init__(
        self,
        engine: Engine,
        ports: Union[str, Dict[int, str]],
        *,
        baud: int = 2_000_000,
        hello_timeout: float = 2.0,
        max_in_flight: Optional[int] = 4,
    ) -> None:
        self.engine = engine
        if isinstance(ports, str):
            controllers = engine.lights.controllers
            if len(controllers) != 1:
                raise ValueError(
                    f"Geometry has controllers {controllers}; pass a "
                    "{controller: port} mapping"
                )
            ports = {controllers[0]: ports}
        self.port_names = ports
        self.baud = baud
        self.hello_timeout = hello_timeout
        self.max_in_flight = max_in_flight
        self.connections: Dict[int, pyserial.Serial] = {}
        self._splitters: Dict[int, p.FrameSplitter] = {}
        # Frames written but not yet acknowledged, per controller: (t, sent_at).
        self._unacked: Dict[int, Deque[Tuple[float, float]]] = {}
        self._ever_acked: Dict[int, bool] = {}
        self._last_sent_t: Dict[int, float] = {}
        self.ack_latencies: List[float] = []
        self.stalled_ticks = 0
        if engine.codec_config.budget_bytes is None:
            engine.codec_config.budget_bytes = budget_for_baud(baud, engine.fps)

    # --------------------------------------------------------------- lifecycle

    def open(self) -> None:
        for controller, name in self.port_names.items():
            connection = pyserial.serial_for_url(name, baudrate=self.baud, timeout=0)
            self.connections[controller] = connection
            self._splitters[controller] = p.FrameSplitter()
            self._unacked[controller] = deque()
            self._ever_acked[controller] = False
        self._wait_for_hello()
        self._send_session()

    def close(self) -> None:
        for connection in self.connections.values():
            try:
                connection.close()
            except Exception:
                pass
        self.connections.clear()

    def _wait_for_hello(self) -> None:
        """Wait briefly for HELLO from each device; proceed regardless.

        Correctness does not depend on the handshake (a decoder syncs at the
        first keyframe, spec §11.7.3); HELLO is for logging and negotiation.
        """
        deadline = time.monotonic() + self.hello_timeout
        pending = set(self.connections)
        while pending and time.monotonic() < deadline:
            for controller in list(pending):
                for frame_type, _, _, _ in self._read_frames(controller):
                    if frame_type == p.FRAME_HELLO:
                        pending.discard(controller)
            time.sleep(0.01)

    def _send_session(self) -> None:
        for frame in self.engine.session_frames():
            self._route(frame)

    # ------------------------------------------------------------------ inbound

    def _read_frames(self, controller: int) -> Iterator[Tuple[int, int, float, bytes]]:
        connection = self.connections[controller]
        data = connection.read(4096)
        if not data:
            return
        for raw in self._splitters[controller].feed(data):
            try:
                yield p.parse_frame(raw)
            except p.ProtocolError:
                continue

    def _poll_inbound(self) -> None:
        for controller in self.connections:
            for frame_type, _, t, _ in self._read_frames(controller):
                if frame_type == p.FRAME_RESYNC:
                    self.engine.request_keyframe()
                elif frame_type == p.FRAME_ACK:
                    self._retire(controller, t)

    def _retire(self, controller: int, acked_t: float) -> None:
        """Retire every frame at or before ``acked_t`` (spec §11.7.6)."""
        self._ever_acked[controller] = True
        pending = self._unacked[controller]
        now = time.monotonic()
        while pending and pending[0][0] <= acked_t:
            _, sent_at = pending.popleft()
            self.ack_latencies.append(now - sent_at)

    # -------------------------------------------------------------- flow control

    def _window_full(self) -> bool:
        """True if any controller has reached its unacknowledged-frame limit.

        A controller that has never acknowledged anything is exempt: firmware
        without ACK support would otherwise deadlock the stream after
        ``max_in_flight`` frames rather than degrading to the old behaviour.
        """
        if not self.max_in_flight:
            return False
        for controller, pending in self._unacked.items():
            if not self._ever_acked.get(controller):
                continue
            if len(pending) >= self.max_in_flight:
                return True
        return False

    # ------------------------------------------------------------------ outbound

    def _route(self, frame: bytes) -> None:
        # Header layout is fixed; controller is byte 2 of the decoded frame,
        # but frames are COBS-encoded here — decode just the routing field.
        body = p.cobs_decode(frame.rstrip(b"\x00"))
        controller = body[2]
        connection = self.connections.get(controller)
        if connection is None:
            return
        connection.write(frame)
        if not self.max_in_flight:
            return
        (t,) = struct.unpack_from("<d", body, 3)
        pending = self._unacked.setdefault(controller, deque())
        # A non-monotonic t means the timeline restarted (pattern loop or
        # seek). Outstanding entries can never be retired by a later ACK
        # then, so drop them rather than let the window wedge shut.
        if t < self._last_sent_t.get(controller, float("-inf")):
            pending.clear()
        self._last_sent_t[controller] = t
        pending.append((t, time.monotonic()))

    def run(self, duration: Optional[float] = None, start_frame: int = 0) -> None:
        """Blocking stream loop at engine.fps until duration (or forever)."""
        if not self.connections:
            self.open()
        interval = 1.0 / self.engine.fps
        started = time.monotonic()
        frame_index = start_frame
        try:
            while duration is None or (time.monotonic() - started) < duration:
                tick_start = time.monotonic()
                self._poll_inbound()
                # Skip the whole tick when the window is full -- do not render
                # and discard. The encoder models the decoder's state, so
                # advancing it without sending would desync every subsequent
                # DELTA. Skipping leaves both ends on the last applied frame,
                # and the next DELTA is computed correctly from there.
                if self._window_full():
                    self.stalled_ticks += 1
                else:
                    t = frame_index / self.engine.fps
                    for frame in self.engine.frame(t):
                        self._route(frame)
                frame_index += 1
                sleep_for = interval - (time.monotonic() - tick_start)
                if sleep_for > 0:
                    time.sleep(sleep_for)
        finally:
            self.close()

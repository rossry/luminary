"""Serial driver: engine frames -> Scorpio over USB-CDC (spec §12.2).

One process, one engine, one port per controller (spec §12.2.4): each frame's
header names its controller and the driver routes it to that controller's
port. Inbound bytes are scanned for RESYNC/HELLO frames (spec §13.3). The
driver contains no color or codec logic (spec §12.1.1).
"""

from __future__ import annotations

import time
from typing import Dict, Iterator, Optional, Tuple, Union

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
        self.connections: Dict[int, pyserial.Serial] = {}
        self._splitters: Dict[int, p.FrameSplitter] = {}
        if engine.codec_config.budget_bytes is None:
            engine.codec_config.budget_bytes = budget_for_baud(baud, engine.fps)

    # --------------------------------------------------------------- lifecycle

    def open(self) -> None:
        for controller, name in self.port_names.items():
            connection = pyserial.serial_for_url(name, baudrate=self.baud, timeout=0)
            self.connections[controller] = connection
            self._splitters[controller] = p.FrameSplitter()
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
            for frame_type, _, _, _ in self._read_frames(controller):
                if frame_type == p.FRAME_RESYNC:
                    self.engine.request_keyframe()

    # ------------------------------------------------------------------ outbound

    def _route(self, frame: bytes) -> None:
        # Header layout is fixed; controller is byte 2 of the decoded frame,
        # but frames are COBS-encoded here — decode just the routing field.
        body = p.cobs_decode(frame.rstrip(b"\x00"))
        controller = body[2]
        connection = self.connections.get(controller)
        if connection is not None:
            connection.write(frame)

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
                t = frame_index / self.engine.fps
                for frame in self.engine.frame(t):
                    self._route(frame)
                frame_index += 1
                sleep_for = interval - (time.monotonic() - tick_start)
                if sleep_for > 0:
                    time.sleep(sleep_for)
        finally:
            self.close()

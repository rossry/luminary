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

Faults degrade per controller, not per driver (spec §11.7.7): a serial error
marks that one connection down and the stream continues for the others, with
reconnection attempted every second. A reconnect — and a HELLO seen
mid-session, which means the device rebooted while the port stayed up — gets
a fresh SESSION and a keyframe, because a device that lost its geometry can
never resynchronize from DELTAs alone; without this, one power blip left a
board dark until the server was restarted.
"""

from __future__ import annotations

import struct
import sys
import time
from collections import deque
from typing import Deque, Dict, Iterator, List, Optional, Tuple, Union

import serial as pyserial

from luminary.comms import protocol as p
from luminary.engine.engine import Engine


def _raise_timer_resolution() -> bool:
    """Ask Windows for 1 ms timer granularity; no-op elsewhere.

    Without this the scheduler quantum is ~15.6 ms, which the spin in
    :meth:`SerialDriver._pace` would otherwise have to absorb entirely --
    burning most of a core. Returns whether it was granted, so it can be
    released again.
    """
    if sys.platform == "win32":
        try:
            import ctypes

            return bool(ctypes.WinDLL("winmm").timeBeginPeriod(1) == 0)
        except Exception:
            return False
    return False


def _restore_timer_resolution() -> None:
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.WinDLL("winmm").timeEndPeriod(1)
        except Exception:
            pass


# How often a downed controller is retried, and how long a blocked write may
# take before it is treated as a fault. A wedged board never drains its
# buffer, so without the write timeout one dead device could hang the whole
# stream indefinitely.
RECONNECT_INTERVAL = 1.0
WRITE_TIMEOUT = 1.0


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
        # Bounded: an installation runs for days, and one float per frame at
        # 30 fps is ~21 MB/day if left to grow. The budget controller uses
        # its own per-interval accumulator, so the cap costs it nothing.
        self.ack_latencies: Deque[float] = deque(maxlen=4096)
        self._ack_interval: List[float] = []
        self.stalled_ticks = 0
        # Controllers whose connection faulted: controller -> next retry time.
        self._down: Dict[int, float] = {}
        self._last_session_sent: Dict[int, float] = {}
        self.disconnects = 0
        self.reconnects = 0
        # How early _pace stops sleeping and starts spinning. 2 ms covers
        # the residual jitter once the 1 ms timer period is granted.
        self._pace_slack = 0.002
        # Adaptive DELTA budget (spec §11.7.6.6). budget_for_baud answers
        # "what can the LINK carry", but the binding limit is what the BOARD
        # can decode and repaint at frame rate -- a Feather SCORPIO digests a
        # baud-sized 5333-byte frame in ~86 ms, less than 12 fps. The
        # sustainable size depends on geometry and hardware, so rather than
        # hardcode one measurement, the driver finds it: window stalls mean
        # the board is behind, so shrink multiplicatively; sustained clean
        # ticks grow it additively back toward the link-rate ceiling. An
        # explicitly configured budget is respected and never adapted.
        self._budget_auto = engine.codec_config.budget_bytes is None
        self._budget_cap = budget_for_baud(baud, engine.fps)
        if self._budget_auto:
            engine.codec_config.budget_bytes = min(512, self._budget_cap)
        self._adapt_ticks = 0
        self._adapt_last_stalls = 0
        self._adapt_clean_intervals = 0

    # --------------------------------------------------------------- lifecycle

    def open(self) -> None:
        """Open every controller port; degrade to reconnection on failures.

        A port that cannot be opened is scheduled for retry rather than
        aborting the stream — at installation start the boards may power up
        after the host. Only if *no* port opens does this raise, since that
        is far more likely a configuration error than a transient.
        """
        errors: Dict[int, Exception] = {}
        for controller, name in self.port_names.items():
            try:
                self._open_one(controller, name)
            except (pyserial.SerialException, OSError) as exc:
                errors[controller] = exc
                self._down[controller] = time.monotonic() + RECONNECT_INTERVAL
        if errors and not self.connections:
            raise pyserial.SerialException(
                f"No controller port could be opened: {errors}"
            )
        self._wait_for_hello()
        self._send_session()

    def _open_one(self, controller: int, name: str) -> None:
        connection = pyserial.serial_for_url(
            name, baudrate=self.baud, timeout=0, write_timeout=WRITE_TIMEOUT
        )
        self.connections[controller] = connection
        self._splitters[controller] = p.FrameSplitter()
        self._unacked[controller] = deque()
        self._ever_acked.setdefault(controller, False)

    def close(self) -> None:
        for connection in self.connections.values():
            try:
                connection.close()
            except Exception:
                pass
        self.connections.clear()
        self._down.clear()

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

    def _send_session(self, only: Optional[int] = None) -> None:
        now = time.monotonic()
        for frame in self.engine.session_frames():
            body = p.cobs_decode_header(frame.rstrip(b"\x00"))
            controller = body[2]
            if only is not None and controller != only:
                continue
            self._last_session_sent[controller] = now
            self._route(frame)

    # ---------------------------------------------------------------- recovery

    def _mark_down(self, controller: int) -> None:
        """Drop one faulted connection; the stream continues without it."""
        connection = self.connections.pop(controller, None)
        if connection is None:
            return
        try:
            connection.close()
        except Exception:
            pass
        self._unacked.pop(controller, None)
        self._splitters.pop(controller, None)
        self._down[controller] = time.monotonic() + RECONNECT_INTERVAL
        self.disconnects += 1

    def _try_reconnect(self) -> None:
        """Reopen downed controllers whose retry time has come.

        A reconnected device has no geometry (it likely rebooted), so it gets
        a fresh SESSION and a keyframe — DELTAs alone can never resync it.
        The keyframe also repairs the other direction: while the device was
        gone the encoder's decoder-model kept advancing past it.
        """
        if not self._down:
            return
        now = time.monotonic()
        for controller, retry_at in list(self._down.items()):
            if now < retry_at:
                continue
            try:
                self._open_one(controller, self.port_names[controller])
            except (pyserial.SerialException, OSError):
                self._down[controller] = now + RECONNECT_INTERVAL
                continue
            del self._down[controller]
            self.reconnects += 1
            self._send_session(only=controller)
            self.engine.request_keyframe()

    def _on_hello(self, controller: int) -> None:
        """HELLO after the session started: the device rebooted in place.

        The port never dropped (or reconnected before we noticed), but the
        decoder state is gone — it repeats HELLO until its first frame
        precisely so this case is detectable. Throttled because several
        HELLOs may already be in flight when the SESSION lands.
        """
        last = self._last_session_sent.get(controller)
        if last is None:
            return  # pre-session HELLO during open(); _wait_for_hello's job
        if time.monotonic() - last < 1.0:
            return
        self._send_session(only=controller)
        self.engine.request_keyframe()

    # ------------------------------------------------------------------ inbound

    def _read_frames(self, controller: int) -> Iterator[Tuple[int, int, float, bytes]]:
        connection = self.connections.get(controller)
        if connection is None:
            return
        try:
            data = connection.read(4096)
        except (pyserial.SerialException, OSError):
            self._mark_down(controller)
            return
        if not data:
            return
        for raw in self._splitters[controller].feed(data):
            try:
                yield p.parse_frame(raw)
            except p.ProtocolError:
                continue

    def _poll_inbound(self) -> None:
        for controller in list(self.connections):
            for frame_type, _, t, _ in self._read_frames(controller):
                if frame_type == p.FRAME_RESYNC:
                    self.engine.request_keyframe()
                elif frame_type == p.FRAME_ACK:
                    self._retire(controller, t)
                elif frame_type == p.FRAME_HELLO:
                    self._on_hello(controller)

    def _retire(self, controller: int, acked_t: float) -> None:
        """Retire every frame at or before ``acked_t`` (spec §11.7.6)."""
        self._ever_acked[controller] = True
        pending = self._unacked[controller]
        now = time.monotonic()
        while pending and pending[0][0] <= acked_t:
            _, sent_at = pending.popleft()
            self.ack_latencies.append(now - sent_at)
            # Separate accumulator for the budget controller: the stats deque
            # above is bounded and shared, so index-based windowing over it
            # would shift as old entries fall off.
            if len(self._ack_interval) < 4096:
                self._ack_interval.append(now - sent_at)

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

    def _adapt_budget(self) -> None:
        """AIMD control of the DELTA byte budget (spec §11.7.6.6).

        Runs once per second of ticks. Two overload signals, because
        saturation shows up in different places depending on where it bites:

        * a skipped tick (window full) — the board is behind and the window
          caught it;
        * median ACK round trip above the frame interval — the board takes
          longer to service a frame than the frame rate allows. This is the
          one that actually fires in practice: serial writes block when the
          OS buffer backs up, ACKs arrive *during* the blocked write, and so
          the window never fills — frame rate just quietly sinks. RTT
          measures the service time directly and cannot be masked that way.

        Either shrinks the budget by a quarter. Growth needs two consecutive
        clean seconds with the median RTT under 70% of the interval — the
        band between 70% and 100% deliberately holds steady. The encoder
        reads the budget fresh on every DELTA and DELTA frames are
        self-describing, so decoders never notice it moving.
        """
        if not self._budget_auto:
            return
        self._adapt_ticks += 1
        if self._adapt_ticks < max(1, int(self.engine.fps)):
            return
        self._adapt_ticks = 0
        stalls = self.stalled_ticks - self._adapt_last_stalls
        self._adapt_last_stalls = self.stalled_ticks
        recent = self._ack_interval
        self._ack_interval = []
        median_rtt = sorted(recent)[len(recent) // 2] if recent else None
        interval = 1.0 / self.engine.fps
        budget = int(self.engine.codec_config.budget_bytes or 64)
        if stalls > 0 or (median_rtt is not None and median_rtt > interval):
            self._adapt_clean_intervals = 0
            budget = max(64, (budget * 3) // 4)
        elif median_rtt is None or median_rtt < 0.7 * interval:
            self._adapt_clean_intervals += 1
            if self._adapt_clean_intervals >= 2:
                budget = min(self._budget_cap, budget + max(64, budget // 8))
        self.engine.codec_config.budget_bytes = budget

    # ------------------------------------------------------------------ outbound

    def _route(self, frame: bytes) -> None:
        # Header layout is fixed; controller is byte 2 and t bytes 3..10 of
        # the decoded frame. Decode only the header: a full cobs_decode here
        # is O(frame) Python and at production frame sizes costs more than
        # rendering and encoding the frame did.
        body = p.cobs_decode_header(frame.rstrip(b"\x00"))
        controller = body[2]
        connection = self.connections.get(controller)
        if connection is None:
            return  # controller is down; reconnection re-syncs it later
        try:
            connection.write(frame)
        except (pyserial.SerialException, OSError):
            # Covers the write timeout too: a board that stops draining its
            # buffer (the wedge) must not hang the stream for the others.
            self._mark_down(controller)
            return
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

    def _pace(self, deadline: float) -> None:
        """Wait until ``deadline``, accurately, polling inbound while at it.

        ``time.sleep`` alone cannot pace 30 fps on Windows: the default system
        timer granularity is ~15.6 ms, so a requested 20 ms sleep returns after
        ~31 ms and the loop settles around 24 fps no matter how fast the board
        is. Sleep in short slices to within a slack margin, then spin the
        remainder.

        The slices matter beyond accuracy: inbound is polled between them, so
        an ACK is seen within ~2 ms of arriving. Polling only once per tick
        quantizes every measured round trip up to a full frame interval, which
        blinds the budget controller (§11.7.6.6) — a fast board reads as
        border-line and the growth path becomes unreachable.
        """
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= self._pace_slack:
                break
            self._poll_inbound()
            time.sleep(min(0.002, remaining - self._pace_slack))
        while time.monotonic() < deadline:
            pass

    def run(self, duration: Optional[float] = None, start_frame: int = 0) -> None:
        """Blocking stream loop at engine.fps until duration (or forever)."""
        if not self.connections:
            self.open()
        interval = 1.0 / self.engine.fps
        started = time.monotonic()
        frame_index = start_frame
        timer_raised = _raise_timer_resolution()
        try:
            while duration is None or (time.monotonic() - started) < duration:
                tick_start = time.monotonic()
                self._poll_inbound()
                self._try_reconnect()
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
                self._adapt_budget()
                self._pace(tick_start + interval)
        finally:
            if timer_raised:
                _restore_timer_resolution()
            self.close()

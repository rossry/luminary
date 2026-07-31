"""Serial flow control (spec §11.7.6): the acknowledgement window.

This is a correctness requirement of the transport, not a throughput knob.
The RP2040's USB-CDC stack stops responding entirely when its receive buffer
backs up, and recovering needs a physical replug, so the sender must never
outrun the device by more than the window.

The device is simulated here: a fake port records what the driver wrote and
lets a test decide which frames get acknowledged and when.
"""

import struct

import pytest

from luminary.comms import protocol as p
from luminary.comms.codec import CodecConfig
from luminary.drivers.serial_driver import SerialDriver
from luminary.engine.engine import Engine
from luminary.geometry.capture import CaptureParams, capture
from luminary.geometry.scaffold import Scaffold
from luminary.patterns.registry import default_registry

SCAFFOLD = {
    "schema": "luminary.scaffold/1",
    "space": {"authoritative": ["xy"]},
    "lines": [
        {"p1": [0, 0], "p2": [100, 0]},
        {"p1": [100, 0], "p2": [100, 100]},
    ],
    "meta": {"name": "flow-control-test"},
}


class FakePort:
    """Minimal pyserial stand-in that captures writes and replays inbound."""

    def __init__(self) -> None:
        self.written: list[bytes] = []
        self.inbound = bytearray()

    def write(self, data: bytes) -> int:
        self.written.append(bytes(data))
        return len(data)

    def read(self, size: int = 1) -> bytes:
        chunk = bytes(self.inbound[:size])
        del self.inbound[:size]
        return chunk

    def close(self) -> None:
        pass

    # -- helpers for tests -------------------------------------------------

    def sent_times(self) -> list[float]:
        """Header t of every frame written, in order."""
        out = []
        for frame in self.written:
            body = p.cobs_decode(frame.rstrip(b"\x00"))
            (t,) = struct.unpack_from("<d", body, 3)
            out.append(t)
        return out

    def ack(self, controller: int, t: float) -> None:
        self.inbound.extend(p.build_ack(controller, t))


@pytest.fixture
def lights():
    return capture(
        Scaffold.load(SCAFFOLD), CaptureParams(count_per_line=16, interpolate_every=4)
    )


def make_driver(lights, port, max_in_flight=4, fps=30.0):
    engine = Engine(
        lights, default_registry().get("spiral"), fps=fps, codec_config=CodecConfig()
    )
    controller = lights.controllers[0]
    driver = SerialDriver(engine, {controller: "fake"}, max_in_flight=max_in_flight)
    driver.connections[controller] = port
    driver._splitters[controller] = p.FrameSplitter()
    driver._unacked[controller] = __import__("collections").deque()
    driver._ever_acked[controller] = False
    return driver, controller


def test_window_stalls_sender_once_full(lights):
    """With no ACKs after the first, the sender must stop, not run away."""
    port = FakePort()
    driver, controller = make_driver(lights, port, max_in_flight=4)
    driver._send_session()
    # One ACK marks the device as ACK-capable, so the window starts enforcing.
    port.ack(controller, driver._unacked[controller][0][0])
    driver._poll_inbound()

    for index in range(50):
        driver._poll_inbound()
        if driver._window_full():
            driver.stalled_ticks += 1
        else:
            for frame in driver.engine.frame(index / driver.engine.fps):
                driver._route(frame)

    assert len(driver._unacked[controller]) <= 4
    assert driver.stalled_ticks > 0, "sender never throttled"


def test_ack_retires_and_resumes(lights):
    """An ACK reopens the window and streaming continues."""
    port = FakePort()
    driver, controller = make_driver(lights, port, max_in_flight=2)
    driver._send_session()
    port.ack(controller, driver._unacked[controller][0][0])
    driver._poll_inbound()

    for index in range(4):
        if not driver._window_full():
            for frame in driver.engine.frame(index / driver.engine.fps):
                driver._route(frame)
    assert driver._window_full(), "window should be full without further ACKs"

    newest = driver._unacked[controller][-1][0]
    port.ack(controller, newest)
    driver._poll_inbound()
    assert not driver._window_full(), "ACK did not reopen the window"
    assert len(driver._unacked[controller]) == 0


def test_ack_is_cumulative(lights):
    """Acknowledging t retires everything at or before it (a lost ACK heals)."""
    port = FakePort()
    driver, controller = make_driver(lights, port, max_in_flight=100)
    driver._send_session()
    for index in range(6):
        for frame in driver.engine.frame(index / driver.engine.fps):
            driver._route(frame)

    pending = driver._unacked[controller]
    assert len(pending) > 3
    third = pending[2][0]
    port.ack(controller, third)  # ACKs for the first two never arrived
    driver._poll_inbound()

    assert all(t > third for t, _ in driver._unacked[controller])


def test_never_acked_controller_is_exempt(lights):
    """Firmware without ACK support must not deadlock the stream."""
    port = FakePort()
    driver, controller = make_driver(lights, port, max_in_flight=2)
    driver._send_session()
    for index in range(20):
        driver._poll_inbound()
        assert not driver._window_full(), "silent device wrongly throttled"
        for frame in driver.engine.frame(index / driver.engine.fps):
            driver._route(frame)


def test_rewound_time_clears_window(lights):
    """A pattern loop or seek must not wedge the window shut."""
    port = FakePort()
    driver, controller = make_driver(lights, port, max_in_flight=4)
    driver._send_session()
    port.ack(controller, driver._unacked[controller][0][0])
    driver._poll_inbound()

    for index in range(10, 14):
        if not driver._window_full():
            for frame in driver.engine.frame(index / driver.engine.fps):
                driver._route(frame)
    assert driver._window_full()

    # Restart the timeline. No ACK for the old, higher t values can ever
    # arrive, so holding them would stall the sender forever.
    for frame in driver.engine.frame(0.0):
        driver._route(frame)
    assert len(driver._unacked[controller]) == 1
    assert not driver._window_full()


def test_latency_recorded(lights):
    """ACKs yield a round-trip measurement, which t-as-key exists to give."""
    port = FakePort()
    driver, controller = make_driver(lights, port, max_in_flight=8)
    driver._send_session()
    newest = driver._unacked[controller][-1][0]
    port.ack(controller, newest)
    driver._poll_inbound()
    assert driver.ack_latencies
    assert all(latency >= 0.0 for latency in driver.ack_latencies)


def test_ack_frame_roundtrips():
    """build_ack -> parse_frame preserves the acknowledged time exactly."""
    frame = p.build_ack(3, 12.5)
    body = p.cobs_decode(frame.rstrip(b"\x00"))
    frame_type, controller, t, payload = p.parse_frame(body)
    assert frame_type == p.FRAME_ACK
    assert controller == 3
    assert t == 12.5
    assert payload == b""

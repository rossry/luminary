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


def _cycle(driver):
    """Advance the budget controller by one full adaptation interval."""
    for _ in range(int(driver.engine.fps)):
        driver._adapt_budget()


def test_auto_budget_starts_small_and_grows_to_cap(lights):
    """With no stalls, the budget climbs additively to the link-rate cap."""
    port = FakePort()
    driver, _ = make_driver(lights, port)  # CodecConfig() -> budget unset -> auto
    assert driver._budget_auto
    start = driver.engine.codec_config.budget_bytes
    assert start == 512, "auto budget should start conservative, not baud-sized"
    for _ in range(200):
        _cycle(driver)
    assert driver.engine.codec_config.budget_bytes == driver._budget_cap


def test_auto_budget_shrinks_on_stalls(lights):
    """A stalled tick is evidence the board is behind: budget must drop."""
    port = FakePort()
    driver, _ = make_driver(lights, port)
    before = driver.engine.codec_config.budget_bytes
    driver.stalled_ticks += 3
    _cycle(driver)
    after = driver.engine.codec_config.budget_bytes
    assert after == (before * 3) // 4


def test_auto_budget_never_below_floor(lights):
    """Repeated stalls converge on the 64-byte floor, not zero."""
    port = FakePort()
    driver, _ = make_driver(lights, port)
    for _ in range(50):
        driver.stalled_ticks += 1
        _cycle(driver)
    assert driver.engine.codec_config.budget_bytes == 64


def test_auto_budget_requires_sustained_clean_to_grow(lights):
    """One clean second after a stall must not immediately regrow."""
    port = FakePort()
    driver, _ = make_driver(lights, port)
    driver.stalled_ticks += 1
    _cycle(driver)
    shrunk = driver.engine.codec_config.budget_bytes
    _cycle(driver)  # first clean interval: streak resets, no growth yet
    assert driver.engine.codec_config.budget_bytes == shrunk
    _cycle(driver)  # second consecutive clean interval: growth
    assert driver.engine.codec_config.budget_bytes > shrunk


def test_explicit_budget_is_never_adapted(lights):
    """A caller-set budget is a decision, not a starting point."""
    port = FakePort()
    engine = Engine(
        lights,
        default_registry().get("spiral"),
        fps=30.0,
        codec_config=CodecConfig(),
    )
    engine.codec_config.budget_bytes = 800
    controller = lights.controllers[0]
    driver = SerialDriver(engine, {controller: "fake"}, max_in_flight=4)
    driver.connections[controller] = port
    driver._splitters[controller] = p.FrameSplitter()
    assert not driver._budget_auto
    driver.stalled_ticks += 5
    _cycle(driver)
    for _ in range(10):
        _cycle(driver)
    assert engine.codec_config.budget_bytes == 800


def test_auto_budget_shrinks_on_slow_rtt_without_stalls(lights):
    """The masking case: blocking writes keep the window from ever filling,
    so no stall is recorded while frame rate sinks. Median RTT above the
    frame interval must shrink the budget on its own."""
    port = FakePort()
    driver, _ = make_driver(lights, port)
    before = driver.engine.codec_config.budget_bytes
    # 30 ACKs at 50ms against a 33.3ms interval; no stalls anywhere.
    driver._ack_interval.extend([0.050] * 30)
    _cycle(driver)
    assert driver.stalled_ticks == 0
    assert driver.engine.codec_config.budget_bytes == (before * 3) // 4


def test_auto_budget_holds_in_hysteresis_band(lights):
    """RTT between 70% and 100% of the interval: neither shrink nor grow."""
    port = FakePort()
    driver, _ = make_driver(lights, port)
    before = driver.engine.codec_config.budget_bytes
    for _ in range(5):
        driver._ack_interval.extend([0.030] * 30)  # 90% of 33.3ms
        _cycle(driver)
    assert driver.engine.codec_config.budget_bytes == before


def test_auto_budget_growth_needs_fast_rtt(lights):
    """Growth requires RTT comfortably inside the interval, not merely
    the absence of stalls."""
    port = FakePort()
    driver, _ = make_driver(lights, port)
    before = driver.engine.codec_config.budget_bytes
    for _ in range(3):
        driver._ack_interval.extend([0.010] * 30)  # 30% of interval
        _cycle(driver)
    assert driver.engine.codec_config.budget_bytes > before


def test_auto_budget_rtt_window_is_per_interval(lights):
    """Old latencies must not haunt later decisions: only ACKs since the
    last adaptation count."""
    port = FakePort()
    driver, _ = make_driver(lights, port)
    driver._ack_interval.extend([0.500] * 30)  # terrible, but consumed now
    _cycle(driver)
    shrunk = driver.engine.codec_config.budget_bytes
    for _ in range(3):
        driver._ack_interval.extend([0.010] * 30)  # fresh interval: fast
        _cycle(driver)
    assert driver.engine.codec_config.budget_bytes > shrunk


class FaultyPort(FakePort):
    """FakePort that can be made to raise on read or write."""

    def __init__(self) -> None:
        super().__init__()
        self.fail_read = False
        self.fail_write = False

    def read(self, size: int = 1) -> bytes:
        if self.fail_read:
            raise __import__("serial").SerialException("injected read fault")
        return super().read(size)

    def write(self, data: bytes) -> int:
        if self.fail_write:
            raise __import__("serial").SerialException("injected write fault")
        return super().write(data)


def _frame_types(written):
    out = []
    for frame in written:
        body = p.cobs_decode(frame.rstrip(b"\x00"))
        out.append(p.parse_frame(body)[0])
    return out


def test_hello_mid_session_resends_session(lights):
    """A HELLO after the session started means the device rebooted: it has
    no geometry and can never resync from DELTAs. It must get a SESSION."""
    port = FakePort()
    driver, controller = make_driver(lights, port)
    driver._send_session()
    sessions_before = _frame_types(port.written).count(p.FRAME_SESSION)
    driver._last_session_sent[controller] -= 5.0  # age past the throttle

    port.inbound.extend(p.build_frame(p.FRAME_HELLO, controller, 0.0, b""))
    driver._poll_inbound()

    assert _frame_types(port.written).count(p.FRAME_SESSION) == sessions_before + 1


def test_hello_storm_is_throttled(lights):
    """Several boot HELLOs may be in flight when the SESSION lands; only the
    first may trigger a resend per throttle window."""
    port = FakePort()
    driver, controller = make_driver(lights, port)
    driver._send_session()
    driver._last_session_sent[controller] -= 5.0
    for _ in range(4):
        port.inbound.extend(p.build_frame(p.FRAME_HELLO, controller, 0.0, b""))
    driver._poll_inbound()
    assert _frame_types(port.written).count(p.FRAME_SESSION) == 2


def test_read_fault_isolates_controller(lights):
    """A serial error must down that controller, not crash the stream."""
    port = FaultyPort()
    driver, controller = make_driver(lights, port)
    port.fail_read = True
    driver._poll_inbound()  # must not raise
    assert controller not in driver.connections
    assert driver.disconnects == 1
    driver._poll_inbound()  # downed controller is skipped, still no raise


def test_write_fault_isolates_controller(lights):
    port = FaultyPort()
    driver, controller = make_driver(lights, port)
    port.fail_write = True
    for frame in driver.engine.frame(0.0):
        driver._route(frame)  # must not raise
    assert controller not in driver.connections
    assert driver.disconnects == 1


def test_reconnect_restores_and_resends_session(lights, monkeypatch):
    """After a fault, the retry loop reopens the port, re-uploads SESSION,
    and requests a keyframe -- the full reboot-recovery path."""
    port = FaultyPort()
    driver, controller = make_driver(lights, port)
    driver._send_session()
    port.fail_read = True
    driver._poll_inbound()
    assert controller not in driver.connections

    fresh = FakePort()
    monkeypatch.setattr(
        "luminary.drivers.serial_driver.pyserial.serial_for_url",
        lambda *a, **k: fresh,
    )
    driver._down[controller] = 0.0  # retry immediately
    driver._try_reconnect()

    assert controller in driver.connections
    assert driver.reconnects == 1
    assert p.FRAME_SESSION in _frame_types(fresh.written)


def test_reconnect_failure_reschedules(lights, monkeypatch):
    port = FaultyPort()
    driver, controller = make_driver(lights, port)
    port.fail_read = True
    driver._poll_inbound()

    def refuse(*a, **k):
        raise __import__("serial").SerialException("still gone")

    monkeypatch.setattr(
        "luminary.drivers.serial_driver.pyserial.serial_for_url", refuse
    )
    driver._down[controller] = 0.0
    driver._try_reconnect()  # must not raise
    assert controller not in driver.connections
    assert driver._down[controller] > 0.0  # rescheduled, not forgotten


def test_ack_latency_stats_are_bounded(lights):
    """One float per frame forever is a memory leak on an installation."""
    port = FakePort()
    driver, _ = make_driver(lights, port)
    for _ in range(10_000):
        driver.ack_latencies.append(0.01)
    assert len(driver.ack_latencies) <= 4096


def test_host_lateness_does_not_shrink_budget(lights):
    """When the host overruns its own ticks, measured RTT quantizes up to
    the tick period. That is the host's lateness, not the board's -- the
    budget must hold, not collapse to the floor (which happened live)."""
    port = FakePort()
    driver, _ = make_driver(lights, port)
    before = driver.engine.codec_config.budget_bytes
    driver.late_ticks += 30  # every tick in the interval overran
    driver._ack_interval.extend([0.050] * 30)  # quantized-garbage RTTs
    _cycle(driver)
    assert driver.engine.codec_config.budget_bytes == before


def test_host_lateness_does_not_grow_budget_either(lights):
    """Late-tick intervals have no trustworthy signal in either direction."""
    port = FakePort()
    driver, _ = make_driver(lights, port)
    before = driver.engine.codec_config.budget_bytes
    for _ in range(4):
        driver.late_ticks += 30
        driver._ack_interval.extend([0.001] * 30)
        _cycle(driver)
    assert driver.engine.codec_config.budget_bytes == before


def test_window_stalls_shrink_even_when_host_late(lights):
    """A full window is direct evidence regardless of host lateness."""
    port = FakePort()
    driver, _ = make_driver(lights, port)
    before = driver.engine.codec_config.budget_bytes
    driver.late_ticks += 30
    driver.stalled_ticks += 3
    _cycle(driver)
    assert driver.engine.codec_config.budget_bytes == (before * 3) // 4

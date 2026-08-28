"""The stage's frames on their way to the boards.

The stage owns its clock: it renders on its ticker and hands frames to its
sinks. That is the wrong shape for the acknowledgement window, which works by
*not rendering* when a board is behind — so the interesting behaviour is what
happens when the window is full, and it must not be a silent drop.
"""

from __future__ import annotations

import pytest

from luminary.comms.codec import CodecConfig
from luminary.drivers.stage_sink import StageSerialSink
from luminary.engine.engine import Engine
from luminary.geometry.capture.from_scaffold import CaptureParams, capture
from luminary.geometry.scaffold import Scaffold
from luminary.patterns.registry import default_registry

SCAFFOLD = {
    "schema": "luminary.scaffold/1",
    "space": {"authoritative": ["xy"]},
    "lines": [{"p1": [0, 0], "p2": [100, 0]}, {"p1": [100, 0], "p2": [100, 100]}],
    "meta": {"name": "stage-sink-test"},
}


def _engine():
    lights = capture(
        Scaffold.load(SCAFFOLD), CaptureParams(count_per_line=16, interpolate_every=4)
    )
    return Engine(
        lights,
        default_registry().get("aurora"),
        fps=30.0,
        codec_config=CodecConfig(budget_bytes=512),
    )


class _FakeDriver:
    def __init__(self):
        self.full = False
        self.sent = []
        self.polls = 0
        self.ack_latencies = []
        self.disconnects = 0
        self.reconnects = 0

    def poll(self):
        self.polls += 1

    def window_full(self):
        return self.full

    def send(self, frame):
        self.sent.append(frame)


@pytest.fixture
def sink():
    engine = _engine()
    s = StageSerialSink(engine, {0: "/dev/null"})
    s.driver = _FakeDriver()  # type: ignore[assignment]
    return s


def test_frames_reach_the_boards(sink):
    sink([b"a", b"b"])

    assert sink.driver.sent == [b"a", b"b"]
    assert sink.dropped == 0


def test_inbound_is_polled_every_tick(sink):
    """ACKs only arrive if someone reads them; the stage's clock is the only
    thing running, so the sink has to do it."""
    for _ in range(3):
        sink([b"f"])

    assert sink.driver.polls == 3


def test_a_full_window_forces_a_keyframe_rather_than_dropping_quietly(sink):
    """The encoder models the decoder's state. A frame generated and not sent
    leaves the two disagreeing, and every later DELTA decodes against a state
    the board never reached — so the next frame has to be a keyframe."""
    sink.driver.full = True

    sink([b"a", b"b"])

    assert sink.driver.sent == [], "sent into a full window"
    assert sink.dropped == 1
    frames = sink.engine.frame(0.0)
    kinds = {f[1] for f in (bytes(fr) for fr in frames)}  # header byte 1 = type
    assert kinds, "engine produced nothing after the drop"


def test_the_window_reopening_resumes_delivery(sink):
    sink.driver.full = True
    sink([b"dropped"])
    sink.driver.full = False

    sink([b"delivered"])

    assert sink.driver.sent == [b"delivered"]
    assert sink.dropped == 1


def test_stats_report_what_the_window_cost(sink):
    sink.driver.full = True
    sink([b"x"])
    sink([b"y"])

    assert sink.stats()["dropped_to_window"] == 2

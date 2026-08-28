"""The stage's frames, out to the boards (spec §11.7.6, §16.2.10).

:class:`~luminary.stage.core.StageCore` owns its own clock: it renders on its
ticker and hands the frames to every registered sink. That is the wrong shape
for the acknowledgement window, which works by *not rendering* when a board is
behind — the encoder models the decoder's state, so a frame generated and then
dropped leaves the two disagreeing and every later DELTA wrong.

So this sink does not drop silently. When the window is full it discards the
frames and asks the engine for a keyframe, which resynchronizes the boards
from whatever state they are in. That costs bandwidth exactly when bandwidth
is short, which is why it is a fallback rather than the mechanism: at 30 fps
against a board measured at 67 it should never fire, and `dropped` says so.

Two consequences of the caller owning the clock, both measured:

* Inbound is polled once per tick rather than every couple of milliseconds as
  ``SerialDriver.run`` does, so every ACK round trip is rounded up to a whole
  frame interval. On a board whose true median is ~4 ms this reads ~33 ms at
  30 fps. Flow control is unaffected -- the window counts unacknowledged
  frames, not their latency -- but the number in ``stats()`` is a ceiling, not
  a measurement.
* The adaptive DELTA budget (§11.7.6.6) does not run at all, because it lives
  in ``run()``. The stage's ``CodecConfig`` is used as configured.
"""

from __future__ import annotations

from typing import Dict, List, Union

from luminary.drivers.serial_driver import SerialDriver
from luminary.engine.engine import Engine


class StageSerialSink:
    """A :data:`~luminary.stage.core.FrameSink` backed by the serial driver."""

    def __init__(
        self,
        engine: Engine,
        ports: Union[str, Dict[int, str]],
        *,
        baud: int = 2_000_000,
        max_in_flight: int = 4,
    ) -> None:
        self.engine = engine
        self.driver = SerialDriver(
            engine, ports, baud=baud, max_in_flight=max_in_flight
        )
        self.dropped = 0

    def open(self) -> None:
        self.driver.open()

    def close(self) -> None:
        self.driver.close()

    def __call__(self, frames: List[bytes]) -> None:
        self.driver.poll()
        if self.driver.window_full():
            # Not a silent drop: the next frame will be a keyframe, so the
            # boards resynchronize rather than decoding against a state the
            # encoder has already moved past.
            self.dropped += 1
            self.engine.request_keyframe()
            return
        for frame in frames:
            self.driver.send(frame)

    def stats(self) -> Dict[str, object]:
        latencies = sorted(self.driver.ack_latencies)
        median = latencies[len(latencies) // 2] if latencies else None
        return {
            "acks": len(latencies),
            "ack_median_ms": round(median * 1000, 3) if median is not None else None,
            "dropped_to_window": self.dropped,
            "disconnects": self.driver.disconnects,
            "reconnects": self.driver.reconnects,
        }

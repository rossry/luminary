"""Presentation timing: host frame time -> a local deadline (spec §13.9).

The reference implementation. The C++ firmware and the browser decoder mirror
it, and `tests/test_presentation.py` holds all three to the same golden
vector — the same discipline the three wire decoders are held to, and for the
same reason: the boards, the web viewer and the local preview are fed the
identical wire stream, so if they disagree about *when* a frame is shown the
preview stops being evidence of what the installation is doing.

Without this, every surface paints on arrival, so boards drift apart by their
own decode times and the preview drifts from both. With it, each surface maps
the frame header's `t` onto its own local clock and shows then; they share the
stream and the delay, so they agree without exchanging a clock.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# Observations per minimum window before the estimate is republished. The
# first window is short and each one doubles up to the ceiling: fast
# acquisition, then slow tracking. A flat 64 meant the first correction landed
# 2.1 s into a 30 fps show, and every frame until then ran on whatever queuing
# delay the very first frame happened to carry -- about 100 frames shown past
# their deadline at startup, and none at all afterwards.
ACQUIRE_WINDOW = 4
WINDOW = 64
# micros() on the board wraps here; the reference wraps identically so the
# three implementations agree bit for bit.
MICROS_MOD = 1 << 32


def _wrap(value: int) -> int:
    return value % MICROS_MOD


def _signed(value: int) -> int:
    value %= MICROS_MOD
    return value - MICROS_MOD if value >= MICROS_MOD // 2 else value


@dataclass
class PresentationClock:
    """Maps host frame time onto a local presentation deadline."""

    have: bool = False
    base_t: float = 0.0
    base_us: int = 0
    skew_us: int = 0
    interval_us: int = 0
    _window_min: int = 0
    _window_count: int = 0
    _window_target: int = ACQUIRE_WINDOW
    _last_t: float = 0.0

    def reset(self) -> None:
        self.__init__()  # type: ignore[misc]

    def nominal(self, t: float) -> int:
        """Local micros at which frame ``t`` nominally lands."""
        return _wrap(self.base_us + int((t - self.base_t) * 1e6))

    def observe(self, t: float, now_us: int) -> None:
        """Record that the frame with header time ``t`` arrived at ``now_us``."""
        if not self.have:
            self.have = True
            self.base_t = t
            self.base_us = _wrap(now_us)
            self.skew_us = 0
            self._window_min = 0
            self._window_count = 1
            self._window_target = ACQUIRE_WINDOW
            self._last_t = t
            return

        delta = (t - self._last_t) * 1e6
        if 0.0 < delta < 1e6:
            sample = int(delta)
            self.interval_us = (
                (self.interval_us * 7 + sample) // 8 if self.interval_us else sample
            )
        self._last_t = t

        # Arrival delay is the true offset plus a non-negative queuing term, so
        # the minimum over a window converges on the offset. A mean would bake
        # each surface's own average queuing into its estimate — the standard
        # NTP argument — and the surfaces would sit at different offsets.
        err = _signed(now_us - self.nominal(t))
        if self._window_count == 0 or err < self._window_min:
            self._window_min = err
        self._window_count += 1
        if self._window_count >= self._window_target:
            self.skew_us = self._window_min
            self._window_count = 0
            self._window_min = 0
            self._window_target = min(WINDOW, self._window_target * 2)

    def usable_delay(self, want_us: int, slots: int) -> int:
        """The display delay actually affordable with ``slots`` play-out slots.

        Staging is eager, so a full queue holds ``slots - 1`` frames ahead of
        the one being shown; the delay must budget for exactly that or the
        frame reaching the head arrives with its deadline already past.
        """
        if self.interval_us == 0:
            return want_us
        cap = self.interval_us * (slots - 1 if slots > 1 else 1)
        return min(want_us, cap)

    def deadline(self, t: float, delay_us: int) -> int:
        """Local micros at which frame ``t`` should be shown."""
        return _wrap(self.nominal(t) + self.skew_us + delay_us)


@dataclass
class PlayoutQueue:
    """Frames staged ahead of time, shown when their deadline arrives."""

    depth: int = 4
    _items: List[Tuple[int, object]] = field(default_factory=list)

    def push(self, frame: object, deadline_us: int) -> bool:
        """Stage a frame; False when the queue is full."""
        if len(self._items) >= self.depth:
            return False
        self._items.append((deadline_us, frame))
        return True

    def due(self, now_us: int) -> Optional[object]:
        """The oldest frame whose deadline has arrived, else None."""
        if not self._items:
            return None
        deadline, frame = self._items[0]
        if _signed(now_us - deadline) < 0:
            return None
        self._items.pop(0)
        return frame

    def __len__(self) -> int:
        return len(self._items)

"""Composition: sequence primitives into shows, statelessly.

A show is itself a Pattern — same contract (spec §9.1), same engine,
same registry — assembled from :class:`Movement`\\ s played in order by
a :class:`Conductor`. Time does all the work: the conductor maps the
global ``t`` onto one movement (two during a crossfade) and blends
frames perceptually with :func:`~luminary.patterns.palettes.blend_oklch`,
so a one-hour arc stays a pure function of ``(lights, t)`` — seekable,
dead-reckonable, and free of per-frame Python state.

Performance: at most two child renders per frame, ever. Movement
lookup is a searchsorted over a precomputed start-time array; outside
fade windows exactly one child renders. Composition overhead is O(1)
per frame regardless of show length.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from luminary.patterns.base import Pattern
from luminary.patterns.easing import smoothstep
from luminary.patterns.palettes import blend_oklch


class Movement:
    """One chapter of a show: a pattern, how long it holds the floor,
    and how many seconds it takes to fade in from whatever preceded it.

    During the fade the *previous* movement keeps rendering past its
    nominal end (patterns are functions of t, so "keep rendering" is
    free), and the incoming frame blends over it on a smoothstep.
    ``fade`` must fit inside ``duration``; the first movement of a
    non-looping show fades in from black.
    """

    __slots__ = ("pattern", "duration", "fade")

    def __init__(self, pattern: Pattern, duration: float, fade: float = 10.0) -> None:
        if duration <= 0.0:
            raise ValueError(f"movement duration must be positive, got {duration}")
        if fade < 0.0 or fade > duration:
            raise ValueError(
                f"movement fade must be in [0, duration={duration}], got {fade}"
            )
        self.pattern = pattern
        self.duration = float(duration)
        self.fade = float(fade)


class Conductor(Pattern):
    """Plays movements in sequence with perceptual crossfades.

    Subclasses define a show by calling ``super().__init__([...])`` from
    a no-argument ``__init__`` (the registry instantiates with no
    arguments). With ``loop=True`` the whole sequence repeats and the
    first movement fades in from the last; otherwise the conductor
    exposes ``duration`` — the total length — as the finished-signal
    for whatever is queueing shows, and holds its final movement if
    rendered past the end.
    """

    name = "conductor"
    description = "Movements in sequence, crossfaded perceptually"

    def __init__(self, movements: Sequence[Movement], loop: bool = False) -> None:
        if not movements:
            raise ValueError("a conductor needs at least one movement")
        self._movements = list(movements)
        self._starts = np.concatenate(
            ([0.0], np.cumsum([m.duration for m in self._movements]))
        )
        self._total = float(self._starts[-1])
        self._loop = bool(loop)
        self.duration: Optional[float] = None if loop else self._total

    @property
    def total(self) -> float:
        """Length of one full pass through the movements, seconds."""
        return self._total

    def schedule(self) -> List[Dict[str, Any]]:
        """The show sheet: one row per movement, for status surfaces."""
        return [
            {
                "pattern": movement.pattern.name,
                "start": float(start),
                "duration": movement.duration,
                "fade": movement.fade,
            }
            for movement, start in zip(self._movements, self._starts[:-1])
        ]

    def _slot(self, t: float) -> Tuple[int, float]:
        """(movement index, movement-local time) for global time t."""
        tt = t % self._total if self._loop else t
        idx = int(
            np.clip(
                np.searchsorted(self._starts, tt, side="right") - 1,
                0,
                len(self._movements) - 1,
            )
        )
        return idx, tt - float(self._starts[idx])

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        idx, local = self._slot(t)
        current = self._movements[idx]
        frame: np.ndarray = current.pattern.render(lights, local)
        if current.fade <= 0.0 or local >= current.fade:
            return frame
        # Crossfade window: blend the previous movement (index -1 wraps
        # to the last, which is exactly the loop seam) over this one.
        if idx > 0 or self._loop:
            previous = self._movements[idx - 1]
            prev_frame = previous.pattern.render(lights, local + previous.duration)
        else:
            prev_frame = np.zeros_like(frame)
        weight = float(smoothstep(0.0, current.fade, local))
        out: np.ndarray = blend_oklch(prev_frame, frame, weight)
        return out

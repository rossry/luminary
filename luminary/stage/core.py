"""StageCore: the one place that decides what the sphere is playing.

The stage is the production control plane: a tracklist of queue entries
played gaplessly on ONE :class:`Engine` over one lights geometry (spec
§1.3.1 — every consumer gets wire bytes from ``Engine.frame(t)``; the
web page decodes the same codec frames as firmware would). Surfaces —
the web API/page, and any future serial sink appended to ``sinks`` —
are thin adapters over this core; no playback decision exists anywhere
else (implementation-notes §2.9).

Model: ``entries`` is the whole tracklist and ``index`` the position in
it — the entry at ``index`` is playing; ``index == len(entries)`` means
the tracklist is exhausted and the stage is **holding** (the last
pattern keeps playing, looping at its length — the sphere never goes
dark). A fresh stage holds the default pattern (``spiral``).

Gapless advance: entries swap via ``engine.set_pattern`` on the SAME
engine and geometry — no SESSION change, no dark gap; the forced
keyframe resyncs every decoder on the next tick. Each entry's pattern
receives t measured from that entry's own start (long-form shows and
audio cue sheets align at 0): the core tracks ``entry start`` on its
own monotonic clock and calls ``engine.frame(now - start)``. An entry
plays for its ``duration``, else for the pattern's own ``duration``
attribute if it defines one, else until skipped.

Persistence: the tracklist and index live in ``queue.json`` under the
stage's state directory (always below the server's resolved state dir,
``luminary/statedir.py``), written tmp+rename on every change and
loaded at startup. A restart resumes the current entry from its
beginning (audio restarts with it — there is no mid-file seek).

Concurrency: HTTP handlers and the ticker share this object; every
mutation and ``tick`` runs under one re-entrant lock, and sinks are
called outside it (they are ``call_soon_threadsafe`` queue feeders,
mapping-web's ``_LoopQueue`` shape).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from luminary.comms.codec import CodecConfig
from luminary.engine.engine import Engine
from luminary.geometry.lights import LightsGeometry
from luminary.patterns.base import Pattern
from luminary.patterns.registry import PatternRegistry
from luminary.stage.audio import AudioPlayer

logger = logging.getLogger(__name__)

DEFAULT_PATTERN = "spiral"

FrameSink = Callable[[List[bytes]], None]


class StageError(ValueError):
    """A queue operation that cannot be honored (bad entry, bad index)."""


class QueueEntry(BaseModel):
    """One tracklist entry: what to play, for how long, with what sound.

    ``duration`` None defers to the pattern's own ``duration`` attribute
    (long-form shows carry one); a pattern with neither plays until
    skipped. ``audio`` names a file in the stage's audio directory.
    """

    pattern: str
    duration: Optional[float] = Field(default=None, gt=0)
    audio: Optional[str] = None


def _pattern_duration(pattern: Pattern) -> Optional[float]:
    """The pattern's own runtime, when it declares one (getattr — the
    attribute is a convention for long-form shows, not part of the
    Pattern ABC)."""
    value = getattr(pattern, "duration", None)
    if value is None:
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    return seconds if seconds > 0 else None


class StageCore:
    def __init__(
        self,
        lights: LightsGeometry,
        registry: PatternRegistry,
        state_dir: Path,
        audio: AudioPlayer,
        *,
        fps: float = 30.0,
        default_pattern: str = DEFAULT_PATTERN,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.registry = registry
        self.audio = audio
        self.fps = fps
        self.sinks: List[FrameSink] = []
        self._lock = threading.RLock()
        self._clock = clock
        self._state_dir = Path(state_dir)
        self._queue_path = self._state_dir / "queue.json"
        self._default_pattern = default_pattern

        self.entries: List[QueueEntry] = []
        self.index = 0
        held = self._load()

        base = self._resolve(default_pattern)
        if base is None:
            raise StageError(
                f"default pattern {default_pattern!r} is not in the registry"
            )
        # THE engine: one geometry, one codec session, for the stage's life.
        self.engine = Engine(lights, base, fps=fps, codec_config=CodecConfig())
        self._playing_pattern = base.name
        self._length = _pattern_duration(base)
        self._entry_start = self._clock()
        self._started_wall = time.time()

        if self.index < len(self.entries):
            # Resume the persisted position: the entry restarts from its
            # own t=0 (audio included — there is no mid-file seek).
            self._start_entry(self.index)
        else:
            name = held or (
                self.entries[-1].pattern if self.entries else default_pattern
            )
            if name != base.name:
                self._hold_pattern(name)
            self._save()

    # ------------------------------------------------------------------ state

    @property
    def holding(self) -> bool:
        """Exhausted tracklist: nothing scheduled, last pattern looping."""
        return self.index >= len(self.entries)

    def idle(self) -> bool:
        """True when rendering would reach nobody and nothing must
        advance on schedule: no sinks, no audio playing, tracklist
        exhausted. The ticker polls slowly instead of rendering 30 fps
        to nobody (a registered serial sink keeps the stage live)."""
        with self._lock:
            return not self.sinks and not self.audio.playing and self.holding

    def snapshot(self) -> Dict[str, Any]:
        """The API view: the tracklist plus now-playing."""
        with self._lock:
            return {
                "entries": [entry.model_dump() for entry in self.entries],
                "now": {
                    "index": self.index,
                    "pattern": self._playing_pattern,
                    "started_at": self._started_wall,
                    "elapsed": self._t_rel(self._clock()),
                    "length": self._length,
                    "holding": self.holding,
                },
                "audio_player": self.audio.player_name,
                "audio_playing": self.audio.playing,
            }

    # ------------------------------------------------------------- operations

    def append(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Append one entry; a holding stage starts it immediately."""
        with self._lock:
            try:
                entry = QueueEntry.model_validate(raw)
            except ValidationError as exc:
                raise StageError(_first_error(exc))
            if self._resolve(entry.pattern) is None:
                raise StageError(f"unknown pattern {entry.pattern!r}")
            if entry.audio is not None and not self.audio.has(entry.audio):
                raise StageError(
                    f"unknown audio file {entry.audio!r} (GET /api/audio lists them)"
                )
            was_holding = self.holding
            self.entries.append(entry)
            if was_holding:
                self._start_entry(len(self.entries) - 1)
            else:
                self._save()
            return self.snapshot()

    def remove(self, i: int) -> Dict[str, Any]:
        """Remove entry ``i``. Removing history shifts the index with it;
        removing the playing entry starts whatever slides into its slot."""
        with self._lock:
            if not 0 <= i < len(self.entries):
                raise StageError(f"no queue entry {i}")
            del self.entries[i]
            if i < self.index:
                self.index -= 1
                self._save()
            elif i == self.index:
                self._start_entry(self.index)
            else:
                self._save()
            return self.snapshot()

    def move(self, frm: int, to: int) -> Dict[str, Any]:
        """Reorder the tracklist; the playing entry keeps playing and the
        index tracks it wherever it lands."""
        with self._lock:
            n = len(self.entries)
            if not (0 <= frm < n and 0 <= to < n):
                raise StageError(f"move {frm}->{to} out of range (0..{n - 1})")
            if frm != to:
                entry = self.entries.pop(frm)
                self.entries.insert(to, entry)
                if self.index == frm:
                    self.index = to
                elif frm < self.index <= to:
                    self.index -= 1
                elif to <= self.index < frm:
                    self.index += 1
                self._save()
            return self.snapshot()

    def skip(self) -> Dict[str, Any]:
        """Cut the current entry short: audio dies, the next entry (or the
        hold) starts now. Skipping while already holding is a no-op."""
        with self._lock:
            if not self.holding:
                self._advance()
            else:
                self.audio.stop()  # defensive; hold entry never has audio
            return self.snapshot()

    def clear(self) -> Dict[str, Any]:
        """Drop the whole tracklist. The current pattern keeps playing as
        the hold — an emptied queue never goes dark."""
        with self._lock:
            self.entries = []
            self._enter_hold()
            return self.snapshot()

    # ------------------------------------------------------------------ frames

    def tick(self) -> None:
        """One frame: advance if the entry's time is up, then render at
        the entry's own t. Called by the web ticker at fps (or manually
        by tests); sinks fire outside the lock."""
        with self._lock:
            now = self._clock()
            if (
                not self.holding
                and self._length is not None
                and now - self._entry_start >= self._length
            ):
                self._advance()
            frames = self.engine.frame(self._t_rel(now))
        for sink in list(self.sinks):
            sink(frames)

    def _t_rel(self, now: float) -> float:
        """Per-entry time: seconds since the entry's start; the hold
        loops (t wraps at the held entry's length — patterns are
        stateless, so the wrap is just another frame)."""
        t = now - self._entry_start
        if self.holding and self._length is not None:
            t %= self._length
        return t

    # ------------------------------------------------------------- transitions

    def _resolve(self, name: str) -> Optional[Pattern]:
        try:
            return self.registry.get(name)
        except KeyError:
            return None

    def _advance(self) -> None:
        """The current entry is over (time up, or skipped)."""
        if self.index + 1 < len(self.entries):
            self._start_entry(self.index + 1)
        else:
            self._enter_hold()

    def _start_entry(self, i: int) -> None:
        """Start ``entries[i]`` on the SAME engine: ``set_pattern`` only
        (gapless — no SESSION change; the forced keyframe resyncs every
        decoder at the next tick). An entry whose pattern is no longer
        in the registry is skipped over, logged."""
        pattern: Optional[Pattern] = None
        while i < len(self.entries):
            pattern = self._resolve(self.entries[i].pattern)
            if pattern is not None:
                break
            logger.warning(
                "stage: unknown pattern %r — skipping entry %d",
                self.entries[i].pattern,
                i,
            )
            i += 1
        self.index = i
        if i >= len(self.entries) or pattern is None:
            self._enter_hold()
            return
        entry = self.entries[i]
        self.engine.set_pattern(pattern)
        self._playing_pattern = pattern.name
        self._length = (
            entry.duration if entry.duration is not None else _pattern_duration(pattern)
        )
        self._entry_start = self._clock()
        self._started_wall = time.time()
        self.audio.stop()
        if entry.audio is not None:
            self.audio.start(entry.audio)
        self._save()

    def _enter_hold(self) -> None:
        """Tracklist exhausted: keep the current pattern on the engine
        (its clock keeps running; a finite entry wraps at its length via
        ``_t_rel``, so the hold reads as a seamless loop)."""
        self.index = len(self.entries)
        self.audio.stop()
        self._save()

    def _hold_pattern(self, name: str) -> None:
        """Adopt ``name`` as the held pattern (startup: the persisted
        hold, or the last tracklist entry). Loop length is the pattern's
        own duration, if it declares one."""
        pattern = self._resolve(name) or self._resolve(self._default_pattern)
        assert pattern is not None  # the default resolved in __init__
        self.engine.set_pattern(pattern)
        self._playing_pattern = pattern.name
        self._length = _pattern_duration(pattern)
        self._entry_start = self._clock()
        self._started_wall = time.time()

    # ------------------------------------------------------------- persistence

    def _load(self) -> Optional[str]:
        """Adopt queue.json if present; returns the persisted held
        pattern name (what to keep playing when the index is past the
        end). Malformed entries are dropped, not fatal."""
        try:
            doc = json.loads(self._queue_path.read_text())
        except (OSError, ValueError):
            return None
        entries: List[QueueEntry] = []
        for raw in doc.get("entries", []):
            try:
                entries.append(QueueEntry.model_validate(raw))
            except ValidationError:
                logger.warning("stage: dropping malformed queue entry %r", raw)
        self.entries = entries
        index = doc.get("index")
        if isinstance(index, int) and not isinstance(index, bool):
            self.index = min(max(index, 0), len(entries))
        else:
            self.index = len(entries)
        held = doc.get("held_pattern")
        return held if isinstance(held, str) else None

    def _save(self) -> None:
        """Write queue.json (tmp+rename) — called on every change."""
        self._state_dir.mkdir(parents=True, exist_ok=True)
        doc = {
            "version": 1,
            "entries": [entry.model_dump() for entry in self.entries],
            "index": self.index,
            "held_pattern": self._playing_pattern,
        }
        tmp = self._queue_path.with_name(self._queue_path.name + ".tmp")
        tmp.write_text(json.dumps(doc, indent=2))
        tmp.replace(self._queue_path)


def _first_error(exc: ValidationError) -> str:
    first = exc.errors()[0]
    location = ".".join(str(part) for part in first.get("loc", ()))
    return f"invalid entry: {location}: {first.get('msg', 'invalid')}"

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
the tracklist is exhausted. An exhausted tracklist first consults the
``repeats`` cycle (below); with that empty too, the stage is **holding**
(the last pattern keeps playing, looping at its length — the sphere
never goes dark). A fresh stage holds the default pattern (``spiral``).

Chapters: an entry whose pattern is a composition (it answers
``chapters()`` — a :class:`~luminary.patterns.compose.Conductor`) is a
whole-composition *instance* until it reaches the head of the queue.
At that moment it is expanded in place, one entry per top-level
chapter, titled ``composition/chapter``; if the new head is itself a
nested composition it expands one level again immediately, while later
chapters stay one level deep until they reach the head. A chapter
entry keeps the top-level pattern name — the engine plays the
composition itself — plus the chapter's absolute ``offset`` into that
composition's timeline, its ``duration``, its ``title`` path, and its
liner ``notes``; frame time is ``(now - entry start) + offset``. Audio
at expansion: an instance left to the default gives every chapter its
own declared track (``Movement.audio``, when the file is present); an
instance with an explicit file plays it through (first chapter only);
an explicitly silent instance ("") stays silent. An instance of a
``loop=True`` composition gets one full pass (``pattern.total``) as
its duration.

Gapless advance: entries swap via ``engine.set_pattern`` on the SAME
engine and geometry — no SESSION change, no dark gap; the forced
keyframe resyncs every decoder on the next tick. Adjacent chapters of
the same composition advance *seamlessly*: same pattern object and
``next.offset == prev.offset + prev.duration`` means no ``set_pattern``,
no keyframe, and an entry start adjusted so t is continuous — the
composition plays exactly as if unchaptered (its own crossfades and
audio intact) while skip/board controls see chapter granularity. Any
jump (a skip landing mid-timeline, a different pattern) takes the
keyframe path.

Repeats: ``repeats`` is a round-robin cycle of tokens
``{pattern, title, audio}``. Adding an entry with ``repeat`` on queues
one instance *and* one token; whenever the play-through queue runs out,
the head token is popped, one instance of it is appended (to expand
into chapters at the head as usual), and the token goes back to the end
— the cycle plays forever until its tokens are cancelled. ``repeat``
left unspecified defaults to the pattern's own ``loop`` flag ("is this
configured to repeat").

Persistence: the tracklist, index, and repeats cycle live in
``queue.json`` under the stage's state directory (always below the
server's resolved state dir, ``luminary/statedir.py``), written
tmp+rename on every change and loaded at startup; files from before
the chapter/repeats schema load with the new fields defaulted. A
restart resumes the current entry from its beginning (audio restarts
with it — there is no mid-file seek).

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
from typing import Any, Callable, Dict, List, NamedTuple, Optional

from pydantic import BaseModel, Field, ValidationError

from luminary.comms.codec import CodecConfig
from luminary.engine.engine import Engine
from luminary.geometry.lights import LightsGeometry
from luminary.patterns.base import Pattern
from luminary.patterns.registry import PatternRegistry
from luminary.stage.audio import AudioPlayer

logger = logging.getLogger(__name__)

DEFAULT_PATTERN = "spiral"

#: Two chapter entries whose offsets meet within this are one timeline.
SEAMLESS_EPS = 1e-6

FrameSink = Callable[[List[bytes]], None]


class StageError(ValueError):
    """A queue operation that cannot be honored (bad entry, bad index)."""


class QueueEntry(BaseModel):
    """One tracklist entry: what to play, for how long, with what sound.

    ``audio`` names a file in the stage's audio directory ("" is
    explicitly silent). With audio, the track times the entry:
    ``duration`` None means the file's exact length, and an explicit
    duration is trimmed to it at add time (shorter cuts fade the audio
    out at the cut). Without audio, ``duration`` None defers to the
    pattern's own ``duration`` attribute (long-form shows carry one);
    a pattern with neither plays until skipped.

    Chapter fields: ``offset`` is where this entry starts on its
    pattern's own timeline (0 for a whole pattern; a chapter's absolute
    ``start`` after expansion); ``title`` is the display title (the
    ``composition/chapter`` path — None shows the pattern name);
    ``notes`` are the liner notes (None defers to the pattern's own);
    ``chapter`` is the index path into ``pattern.chapters()`` this entry
    was expanded from (None: a whole-composition instance, expanded when
    it reaches the head). ``repeat`` marks an instance that feeds the
    repeats cycle.
    """

    pattern: str
    duration: Optional[float] = Field(default=None, gt=0)
    audio: Optional[str] = None
    offset: float = Field(default=0.0, ge=0)
    title: Optional[str] = None
    notes: Optional[str] = None
    repeat: bool = False
    chapter: Optional[List[int]] = None


class RepeatToken(BaseModel):
    """One turn of the repeats cycle: what to re-queue when the
    play-through queue runs out."""

    pattern: str
    title: Optional[str] = None
    audio: Optional[str] = None


class _Seam(NamedTuple):
    """The continuation point a natural advance offers the next entry:
    if the next entry plays the same pattern object from ``offset``, the
    timeline is continuous and the advance needs no keyframe."""

    pattern: Pattern
    offset: float
    clock: float  # the boundary on the stage clock: prev start + length


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


def _loop_total(pattern: Pattern) -> Optional[float]:
    """One full pass of a ``loop=True`` composition (its instance
    duration), else None."""
    if not bool(getattr(pattern, "loop", False)):
        return None
    try:
        total = float(getattr(pattern, "total"))
    except (AttributeError, TypeError, ValueError):
        return None
    return total if total > 0 else None


def _chapter_nodes(pattern: Pattern) -> List[Dict[str, Any]]:
    """The pattern's top-level chapter tree, ``[]`` for a chapterless
    pattern (compositions answer ``chapters()`` — duck-typed, like the
    ``duration`` convention)."""
    fn = getattr(pattern, "chapters", None)
    if not callable(fn):
        return []
    try:
        nodes = fn()
    except Exception:  # a broken show must not take the stage down
        logger.exception("stage: %s.chapters() failed", pattern.name)
        return []
    return list(nodes) if isinstance(nodes, list) else []


def _chapter_audio(pattern: Pattern) -> List[str]:
    """Every distinct audio file the pattern's chapter tree declares, in
    play order — the show's recommended per-chapter soundtrack."""
    out: List[str] = []

    def walk(nodes: List[Dict[str, Any]]) -> None:
        for node in nodes:
            name = str(node.get("audio") or "")
            if name and name not in out:
                out.append(name)
            children = node.get("children")
            if isinstance(children, list):
                walk(children)

    walk(_chapter_nodes(pattern))
    return out


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
        self.repeats: List[RepeatToken] = []
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
        self._playing_title = base.name
        self._playing_notes = getattr(base, "notes", "")
        self._playing_offset = 0.0
        self._length = _pattern_duration(base)
        self._entry_start = self._clock()
        self._started_wall = time.time()

        if self.index < len(self.entries):
            # Resume the persisted position: the entry restarts from its
            # own t=0 (audio included — there is no mid-file seek).
            self._start_entry(self.index)
        elif self.repeats:
            # Never hold while the repeats cycle has turns to take.
            self._hold_or_repeat()
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
        """The API view: the tracklist, the repeats cycle, now-playing."""
        with self._lock:
            return {
                "entries": [entry.model_dump() for entry in self.entries],
                "repeats": [token.model_dump() for token in self.repeats],
                "now": {
                    "index": self.index,
                    "pattern": self._playing_pattern,
                    "title": self._playing_title,
                    "notes": self._playing_notes,
                    "offset": self._playing_offset,
                    "started_at": self._started_wall,
                    "elapsed": self._elapsed(self._clock()),
                    "length": self._length,
                    "holding": self.holding,
                },
                "audio_player": self.audio.player_name,
                "audio_playing": self.audio.playing,
            }

    def patterns_meta(self) -> List[Dict[str, Any]]:
        """Registry metadata extended with what the queue panel needs:
        liner ``notes``, the ``loop`` flag (the repeat toggle's default),
        and ``has_chapters`` (whether a queued row can expand)."""
        with self._lock:
            out: List[Dict[str, Any]] = []
            for row in self.registry.list():
                if not row.get("ok"):
                    out.append(dict(row))
                    continue
                pattern = self._resolve(str(row["name"]))
                if pattern is None:  # racing a reload; skip the ghost
                    continue
                declared_audio = str(getattr(pattern, "audio", "") or "")
                wanted = _chapter_audio(pattern)
                out.append(
                    {
                        **row,
                        "notes": str(getattr(pattern, "notes", "") or ""),
                        "loop": bool(getattr(pattern, "loop", False)),
                        "has_chapters": bool(_chapter_nodes(pattern)),
                        "audio": declared_audio,
                        "audio_present": bool(
                            declared_audio and self.audio.has(declared_audio)
                        ),
                        "chapter_audio": wanted,
                        "chapter_audio_present": [
                            name for name in wanted if self.audio.has(name)
                        ],
                    }
                )
            return out

    def chapters_of(self, name: str) -> List[Dict[str, Any]]:
        """The chapter tree for one pattern (display: the queued-row
        expander), ``[]`` for a chapterless pattern."""
        with self._lock:
            pattern = self._resolve(name)
            if pattern is None:
                raise StageError(f"unknown pattern {name!r}")
            return _chapter_nodes(pattern)

    # ------------------------------------------------------------- operations

    def append(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Append one entry; a holding stage starts it immediately.
        ``repeat`` on (default: the pattern's own ``loop`` flag) also
        appends a token to the repeats cycle."""
        with self._lock:
            entry = self._make_entry(raw)
            was_holding = self.holding
            self.entries.append(entry)
            if entry.repeat:
                self._append_token(entry)
            if was_holding:
                self._start_entry(len(self.entries) - 1)
            else:
                self._save()
            return self.snapshot()

    def play_next(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Insert one entry immediately after the playing entry (it
        plays as soon as the current one ends or is skipped); honors
        ``repeat`` exactly like :meth:`append`."""
        with self._lock:
            entry = self._make_entry(raw)
            if entry.repeat:
                self._append_token(entry)
            if self.holding:
                self.entries.append(entry)
                self._start_entry(len(self.entries) - 1)
            else:
                self.entries.insert(self.index + 1, entry)
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
        """Cut the current entry short: audio dies, the next entry (after
        chapter expansion, the next *chapter*) or the hold starts now.
        A skip is a jump on the timeline, so it always re-keyframes.
        Skipping while already holding is a no-op."""
        with self._lock:
            if not self.holding:
                self._advance(jump=True)
            else:
                self.audio.stop()  # defensive; hold entry never has audio
            return self.snapshot()

    def clear(self) -> Dict[str, Any]:
        """Drop the whole play-through tracklist. The repeats cycle is
        its own list with its own controls and keeps cycling; with no
        repeats either, the current pattern keeps playing as the hold —
        an emptied queue never goes dark."""
        with self._lock:
            self.entries = []
            self._hold_or_repeat()
            return self.snapshot()

    def remove_repeat(self, i: int) -> Dict[str, Any]:
        """Cancel one turn of the repeats cycle."""
        with self._lock:
            if not 0 <= i < len(self.repeats):
                raise StageError(f"no repeat entry {i}")
            del self.repeats[i]
            self._save()
            return self.snapshot()

    def move_repeat(self, frm: int, to: int) -> Dict[str, Any]:
        """Reorder the repeats cycle."""
        with self._lock:
            n = len(self.repeats)
            if not (0 <= frm < n and 0 <= to < n):
                raise StageError(f"repeats move {frm}->{to} out of range (0..{n - 1})")
            if frm != to:
                token = self.repeats.pop(frm)
                self.repeats.insert(to, token)
                self._save()
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
                self._advance(jump=False)
            frames = self.engine.frame(self._t_rel(now))
        for sink in list(self.sinks):
            sink(frames)

    def _elapsed(self, now: float) -> float:
        """Seconds into the current entry (the hold loops: t wraps at
        the held entry's length — patterns are stateless, so the wrap
        is just another frame)."""
        t = now - self._entry_start
        if self.holding and self._length is not None:
            t %= self._length
        return t

    def _t_rel(self, now: float) -> float:
        """The pattern's frame time: entry-elapsed plus the entry's
        offset into the pattern's own timeline (a chapter's absolute
        start; 0 for a whole pattern)."""
        return self._elapsed(now) + self._playing_offset

    # ------------------------------------------------------------- transitions

    def _resolve(self, name: str) -> Optional[Pattern]:
        try:
            return self.registry.get(name)
        except KeyError:
            return None

    def _make_entry(self, raw: Dict[str, Any]) -> QueueEntry:
        """Validate one add/play-next request into an instance entry.
        ``repeat`` left unspecified defaults to the pattern's own
        ``loop`` flag; a ``loop=True`` composition with no explicit
        duration gets one full pass (``pattern.total``); audio left
        unspecified means "as declared" — the pattern's own ``audio``
        file when present, and for a composition whose chapters declare
        their own tracks, each chapter's file at expansion. ``""`` is
        explicitly silent and stays silent through expansion."""
        data = dict(raw)
        explicit_repeat = data.get("repeat") is not None
        if not explicit_repeat:
            data.pop("repeat", None)  # null means "the pattern's default"
        try:
            entry = QueueEntry.model_validate(data)
        except ValidationError as exc:
            raise StageError(_first_error(exc))
        pattern = self._resolve(entry.pattern)
        if pattern is None:
            raise StageError(f"unknown pattern {entry.pattern!r}")
        if entry.audio and not self.audio.has(entry.audio):
            raise StageError(
                f"unknown audio file {entry.audio!r} (GET /api/audio lists them)"
            )
        if entry.audio is None and not _chapter_audio(pattern):
            declared = str(getattr(pattern, "audio", "") or "")
            if declared and self.audio.has(declared):
                entry.audio = declared
        if not explicit_repeat:
            entry.repeat = bool(getattr(pattern, "loop", False))
        if entry.audio:
            # The track times the entry: auto duration is the file's
            # exact length, and an explicit duration can only cut it
            # shorter (the cut gets a fade at playback), never outlive
            # it — a longer ask trims to the track here at add time.
            length = self.audio.duration_of(entry.audio)
            if length is not None and length > 0:
                entry.duration = (
                    length if entry.duration is None else min(entry.duration, length)
                )
        if entry.duration is None:
            entry.duration = _loop_total(pattern)
        return entry

    def _append_token(self, entry: QueueEntry) -> None:
        self.repeats.append(
            RepeatToken(pattern=entry.pattern, title=entry.title, audio=entry.audio)
        )

    def _advance(self, *, jump: bool) -> None:
        """The current entry is over. A natural advance (time reached
        the entry's end, ``jump=False``) offers the next entry the
        seam — the continuation point where the timeline would be
        continuous; a skip lands mid-timeline and never does."""
        seam: Optional[_Seam] = None
        if not jump and not self.holding and self._length is not None:
            seam = _Seam(
                pattern=self.engine.pattern,
                offset=self._playing_offset + self._length,
                clock=self._entry_start + self._length,
            )
        if self.index + 1 < len(self.entries):
            self._start_entry(self.index + 1, seam=seam)
        else:
            self._hold_or_repeat(seam=seam)

    def _hold_or_repeat(self, *, seam: Optional[_Seam] = None) -> None:
        """The play-through queue is out: take the next turn of the
        repeats cycle (pop the head, append one instance — it expands
        into chapters at the head as usual — and put the token back at
        the end), else hold. Tokens whose pattern vanished from the
        registry are dropped, never cycled forever."""
        while self.repeats:
            token = self.repeats.pop(0)
            pattern = self._resolve(token.pattern)
            if pattern is None:
                logger.warning(
                    "stage: dropping repeat of unknown pattern %r", token.pattern
                )
                continue
            self.repeats.append(token)
            self.entries.append(
                QueueEntry(
                    pattern=token.pattern,
                    duration=_loop_total(pattern),
                    audio=token.audio,
                    title=token.title,
                    repeat=True,
                )
            )
            self._start_entry(len(self.entries) - 1, seam=seam)
            return
        self._enter_hold()

    def _expand_at(self, i: int) -> bool:
        """Expand ``entries[i]`` in place by one chapter level, if it has
        one: a whole-composition instance becomes its top-level chapters
        (``composition/chapter`` titles; audio on the first only); a
        chapter entry whose node has children becomes those children
        (``…/subchapter``). Returns True when it expanded."""
        entry = self.entries[i]
        pattern = self._resolve(entry.pattern)
        if pattern is None:
            return False
        nodes = _chapter_nodes(pattern)
        if not nodes:
            return False
        if entry.chapter is None:
            children = nodes
            base_title = entry.title or pattern.name
            base_path: List[int] = []
        else:
            try:
                node: Dict[str, Any] = {}
                remaining = nodes
                for j in entry.chapter:
                    node = remaining[j]
                    remaining = node.get("children", [])
            except (IndexError, TypeError, KeyError):
                logger.warning(
                    "stage: chapter path %r no longer fits %r — playing as-is",
                    entry.chapter,
                    entry.pattern,
                )
                return False
            children = node.get("children") or []
            if not children:
                return False
            base_title = entry.title or pattern.name
            base_path = list(entry.chapter)
        self.entries[i : i + 1] = [
            QueueEntry(
                pattern=entry.pattern,
                duration=float(child["duration"]),
                audio=self._chapter_entry_audio(entry, child, j),
                offset=float(child["start"]),
                title=f"{base_title}/{child['title']}",
                notes=str(child.get("notes") or ""),
                repeat=entry.repeat,
                chapter=base_path + [j],
            )
            for j, child in enumerate(children)
        ]
        return True

    def _chapter_entry_audio(
        self, entry: QueueEntry, child: Dict[str, Any], j: int
    ) -> Optional[str]:
        """A chapter entry's audio at expansion. An instance left to the
        default (None) gives every chapter its own declared track when
        the file is present; an explicit file plays through (attached to
        the first chapter only); explicit silence ("") stays silent."""
        if entry.audio is None:
            declared = str(child.get("audio") or "")
            return declared if declared and self.audio.has(declared) else None
        if entry.audio == "":
            return ""
        return entry.audio if j == 0 else None

    def _start_entry(self, i: int, *, seam: Optional[_Seam] = None) -> None:
        """Start ``entries[i]`` on the SAME engine. A composition
        reaching the head expands into chapters first (nested heads
        expand again, one level at a time). The seam makes an adjacent
        chapter of the same composition continuous — no ``set_pattern``,
        no keyframe, audio untouched; every other start is a
        ``set_pattern`` swap (gapless — no SESSION change; the forced
        keyframe resyncs every decoder at the next tick). An entry whose
        pattern is no longer in the registry is skipped over, logged."""
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
            self._hold_or_repeat()
            return
        while self._expand_at(i):
            pass  # a nested composition head expands one level per pass
        entry = self.entries[i]
        seamless = (
            seam is not None
            and pattern is seam.pattern
            and abs(entry.offset - seam.offset) <= SEAMLESS_EPS
        )
        if seamless:
            assert seam is not None
            # One continuous timeline: t keeps flowing through the
            # boundary, so the composition's own crossfade carries the
            # transition and the wire needs only deltas. A chapter with
            # its own track starts it at the boundary; an audio-less
            # chapter (None) lets whatever is playing play on.
            self._entry_start = seam.clock
            if entry.audio:
                self.audio.stop()
                self.audio.start(entry.audio, cut_at=entry.duration)
        else:
            self.engine.set_pattern(pattern)
            self._entry_start = self._clock()
            self.audio.stop()
            if entry.audio:
                self.audio.start(entry.audio, cut_at=entry.duration)
        self._playing_pattern = pattern.name
        self._playing_title = entry.title or pattern.name
        self._playing_notes = (
            entry.notes if entry.notes is not None else getattr(pattern, "notes", "")
        )
        self._playing_offset = entry.offset
        self._length = (
            entry.duration if entry.duration is not None else _pattern_duration(pattern)
        )
        self._started_wall = time.time()
        self._save()

    def _enter_hold(self) -> None:
        """Tracklist exhausted (and no repeats): keep the current pattern
        on the engine (its clock keeps running; a finite entry wraps at
        its length via ``_t_rel``, so the hold reads as a seamless
        loop)."""
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
        self._playing_title = pattern.name
        self._playing_notes = getattr(pattern, "notes", "")
        self._playing_offset = 0.0
        self._length = _pattern_duration(pattern)
        self._entry_start = self._clock()
        self._started_wall = time.time()

    # ------------------------------------------------------------- persistence

    def _load(self) -> Optional[str]:
        """Adopt queue.json if present; returns the persisted held
        pattern name (what to keep playing when the index is past the
        end). Malformed entries are dropped, not fatal; files from
        before the chapter/repeats schema default the new fields."""
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
        repeats: List[RepeatToken] = []
        for raw in doc.get("repeats", []):
            try:
                repeats.append(RepeatToken.model_validate(raw))
            except ValidationError:
                logger.warning("stage: dropping malformed repeat token %r", raw)
        self.repeats = repeats
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
            "version": 2,
            "entries": [entry.model_dump() for entry in self.entries],
            "index": self.index,
            "held_pattern": self._playing_pattern,
            "repeats": [token.model_dump() for token in self.repeats],
        }
        tmp = self._queue_path.with_name(self._queue_path.name + ".tmp")
        tmp.write_text(json.dumps(doc, indent=2))
        tmp.replace(self._queue_path)


def _first_error(exc: ValidationError) -> str:
    first = exc.errors()[0]
    location = ".".join(str(part) for part in first.get("loc", ()))
    return f"invalid entry: {location}: {first.get('msg', 'invalid')}"

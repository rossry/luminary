"""StageCore: the play-queue decision logic (luminary/stage/core.py).

Everything here drives the core directly — a fake monotonic clock, a
fake audio spawn (never a real player), manual ``tick()`` — so every
frame, advance, and subprocess call is accounted for. The invariants
under test: one engine for the stage's life (gapless advance via
``set_pattern``, keyframe but never a fresh SESSION), per-entry t,
duration from the pattern's own attribute, hold-on-empty (never dark),
audio lifecycle, and queue.json persistence.
"""

import json

import pytest

from luminary.comms import protocol as p
from luminary.comms.codec import Decoder
from luminary.geometry.lights import LightsGeometry, LightSpec, SpaceSpec
from luminary.patterns.registry import PatternRegistry
from luminary.stage.audio import AudioPlayer, detect_player
from luminary.stage.core import QueueEntry, StageCore, StageError

# --------------------------------------------------------------------- fakes


class FakeClock:
    """Injectable monotonic clock: tests advance it by hand."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


class FakeProc:
    def __init__(self, argv):
        self.argv = argv
        self.returncode = None
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


class FakeSpawn:
    """Stands in for subprocess.Popen; records every spawned player."""

    def __init__(self):
        self.procs = []

    def __call__(self, argv, **kwargs):
        proc = FakeProc(argv)
        self.procs.append(proc)
        return proc


# ------------------------------------------------------------------ fixtures

# Tiny self-contained pattern set: "spiral" is the stage default, "timed"
# carries the long-form pattern ``duration`` attribute, "plain" has none.
PATTERN_SOURCES = {
    "spiral.py": """
import numpy as np
from luminary.patterns.base import Pattern

class StandInSpiral(Pattern):
    name = "spiral"
    description = "test stand-in for the default"

    def render(self, lights, t):
        out = np.zeros((lights.shape[0], 3))
        out[:, 0] = 0.5
        out[:, 1] = 0.1
        out[:, 2] = (t * 10.0) % 360.0
        return out
""",
    "timed.py": """
import numpy as np
from luminary.patterns.base import Pattern

class Timed(Pattern):
    name = "timed"
    description = "declares its own duration"
    duration = 2.0

    def render(self, lights, t):
        out = np.zeros((lights.shape[0], 3))
        out[:, 0] = 0.6
        out[:, 1] = 0.2
        out[:, 2] = (t * 20.0) % 360.0
        return out
""",
    "plain.py": """
import numpy as np
from luminary.patterns.base import Pattern

class Plain(Pattern):
    name = "plain"
    description = "no duration: plays until skipped"
    notes = "steady and plain"

    def render(self, lights, t):
        out = np.zeros((lights.shape[0], 3))
        out[:, 0] = 0.4
        out[:, 1] = 0.05
        out[:, 2] = (t * 30.0) % 360.0
        return out
""",
    "scored.py": """
import numpy as np
from luminary.patterns.base import Pattern

class Scored(Pattern):
    name = "scored"
    description = "declares its soundtrack"
    audio = "track1.mp3"

    def render(self, lights, t):
        out = np.zeros((lights.shape[0], 3))
        out[:, 0] = 0.3
        return out
""",
    "unscored.py": """
import numpy as np
from luminary.patterns.base import Pattern

class Unscored(Pattern):
    name = "unscored"
    description = "declares a soundtrack that is not on disk"
    audio = "nowhere.mp3"

    def render(self, lights, t):
        out = np.zeros((lights.shape[0], 3))
        out[:, 0] = 0.3
        return out
""",
    # Compositions for the chapter tests. Helper voices are deliberately
    # NOT Pattern subclasses (the registry would try to instantiate the
    # first local Pattern subclass it finds); Movement only needs
    # .name/.notes/.render, and Conductor is importable inside pattern
    # sources exactly like the real book-two shows.
    "suite.py": """
import numpy as np
from luminary.patterns.compose import Conductor, Movement

class _Tone:
    def __init__(self, hue, name, notes=""):
        self.name = name
        self.notes = notes
        self._hue = float(hue)

    def render(self, lights, t):
        out = np.zeros((lights.shape[0], 3))
        out[:, 0] = 0.5
        out[:, 1] = 0.1
        out[:, 2] = (self._hue + t * 5.0) % 360.0
        return out

class Suite(Conductor):
    name = "suite"
    description = "two chapters, no fades"
    notes = "a small suite"

    def __init__(self):
        super().__init__([
            Movement(_Tone(0.0, "s1"), 4.0, fade=0.0,
                     title="one", notes="the first part"),
            Movement(_Tone(120.0, "s2"), 3.0, fade=0.0,
                     title="two", notes="the second part"),
        ])
""",
    "album.py": """
import numpy as np
from luminary.patterns.compose import Conductor, Movement

class _Tone:
    def __init__(self, hue, name, notes=""):
        self.name = name
        self.notes = notes
        self._hue = float(hue)

    def render(self, lights, t):
        out = np.zeros((lights.shape[0], 3))
        out[:, 0] = 0.5
        out[:, 1] = 0.1
        out[:, 2] = (self._hue + t * 5.0) % 360.0
        return out

def _inner():
    return Conductor([
        Movement(_Tone(40.0, "i1"), 4.0, fade=0.0,
                 title="one", notes="inner one"),
        Movement(_Tone(200.0, "i2"), 3.0, fade=0.0,
                 title="two", notes="inner two"),
    ])

class Album(Conductor):
    name = "album"
    description = "nested looping program"

    def __init__(self):
        super().__init__([
            Movement(_Tone(0.0, "dawn"), 5.0, fade=0.0,
                     title="dawn", notes="first light"),
            Movement(_inner(), 7.0, fade=0.0,
                     title="mid", notes="the middle"),
            Movement(_Tone(300.0, "coda"), 5.0, fade=0.0,
                     title="coda", notes="the end"),
        ], loop=True)
""",
}

AUDIO_FILES = ["b side.wav", "track1.mp3"]


@pytest.fixture(scope="module")
def registry(tmp_path_factory):
    pattern_dir = tmp_path_factory.mktemp("stage-patterns")
    for name, source in PATTERN_SOURCES.items():
        (pattern_dir / name).write_text(source)
    return PatternRegistry([pattern_dir])


@pytest.fixture(scope="module")
def lights():
    specs = [
        LightSpec(
            controller=0, channel=ch, index=i, kind="active", pos=[float(i), float(ch)]
        )
        for ch in range(2)
        for i in range(4)
    ]
    return LightsGeometry.from_specs(specs, space=SpaceSpec(authoritative=["xy"]))


def make_stage(tmp_path, registry, lights, command=("fakeplay",), **kwargs):
    """A StageCore over tmp state, fake clock, fake audio spawn."""
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(exist_ok=True)
    for name in AUDIO_FILES:
        (audio_dir / name).write_bytes(b"\x00")
    spawn = FakeSpawn()
    audio = AudioPlayer(list(command) if command else None, audio_dir, spawn=spawn)
    clock = kwargs.pop("clock", FakeClock())
    core = StageCore(lights, registry, tmp_path / "stage", audio, clock=clock, **kwargs)
    return core, spawn, clock


# --------------------------------------------------------------------- tests


def test_fresh_stage_holds_default(tmp_path, registry, lights):
    core, spawn, _clock = make_stage(tmp_path, registry, lights)
    snap = core.snapshot()
    assert snap["entries"] == []
    assert snap["now"]["holding"] is True
    assert snap["now"]["pattern"] == "spiral"
    assert snap["now"]["index"] == 0
    assert snap["audio_player"] == "fakeplay"
    assert snap["audio_playing"] is False
    assert spawn.procs == []
    # Nothing scheduled, nobody listening: the ticker may idle.
    assert core.idle() is True


def test_append_validation(tmp_path, registry, lights):
    core, _spawn, _clock = make_stage(tmp_path, registry, lights)
    with pytest.raises(StageError, match="unknown pattern"):
        core.append({"pattern": "nope"})
    with pytest.raises(StageError, match="invalid entry"):
        core.append({"pattern": "plain", "duration": -3})
    with pytest.raises(StageError, match="unknown audio"):
        core.append({"pattern": "plain", "audio": "missing.mp3"})
    with pytest.raises(StageError, match="unknown audio"):
        core.append({"pattern": "plain", "audio": "../track1.mp3"})
    assert core.snapshot()["entries"] == []  # nothing slipped in


def test_gapless_advance_same_engine_no_session(tmp_path, registry, lights):
    """Entries advance by set_pattern on the SAME engine: the stream shows
    a keyframe at each entry start and never a SESSION; each entry's
    pattern gets t from its own start."""
    core, _spawn, clock = make_stage(tmp_path, registry, lights)
    engine = core.engine
    seen_t = []
    original_frame = engine.frame
    engine.frame = lambda t: (seen_t.append(t), original_frame(t))[1]

    stream = []
    core.sinks.append(stream.extend)
    decoder = Decoder()
    for frame in engine.session_frames():
        decoder.decode(frame)

    core.append({"pattern": "plain", "duration": 1.0})
    core.append({"pattern": "timed", "duration": 1.0})
    clock.advance(0.4)
    core.tick()  # entry 0, keyframed (its start forced one)
    assert seen_t[-1] == pytest.approx(0.4)
    # Keyframe plus its same-tick healing delta (spec §11.7.3a).
    assert decoder.decode(stream[-2])[0] == p.FRAME_KEYFRAME
    assert decoder.decode(stream[-1])[0] == p.FRAME_DELTA

    clock.advance(0.3)
    core.tick()
    assert decoder.decode(stream[-1])[0] == p.FRAME_DELTA

    clock.advance(0.5)  # t=1.2: entry 0's second is up
    core.tick()
    snap = core.snapshot()
    assert core.engine is engine  # the one engine, for the stage's life
    assert snap["now"]["index"] == 1 and snap["now"]["pattern"] == "timed"
    assert snap["now"]["holding"] is False
    assert seen_t[-1] == pytest.approx(0.0)  # per-entry t: restarts at 0
    # The whole stream: keyframe (+ same-tick heal, §11.7.3a), delta,
    # keyframe-on-advance (+ heal) — and never a mid-show SESSION (the
    # geometry lives as long as the stage).
    types = _decode_all(engine, stream)
    assert types == [
        p.FRAME_KEYFRAME,
        p.FRAME_DELTA,
        p.FRAME_DELTA,
        p.FRAME_KEYFRAME,
        p.FRAME_DELTA,
    ]
    assert p.FRAME_SESSION not in types


def _decode_all(engine, frames):
    """Frame types of a captured stream, via a fresh primed decoder."""
    decoder = Decoder()
    for frame in engine.session_frames():
        decoder.decode(frame)
    return [decoder.decode(frame)[0] for frame in frames]


def test_duration_from_pattern_attribute(tmp_path, registry, lights):
    core, _spawn, clock = make_stage(tmp_path, registry, lights)
    core.append({"pattern": "timed"})  # duration None -> pattern's 2.0
    assert core.snapshot()["now"]["length"] == pytest.approx(2.0)
    clock.advance(1.9)
    core.tick()
    assert core.snapshot()["now"]["holding"] is False
    clock.advance(0.2)  # t=2.1 > 2.0
    core.tick()
    assert core.snapshot()["now"]["holding"] is True

    # "plain" declares nothing: plays until skipped.
    core.append({"pattern": "plain"})
    assert core.snapshot()["now"]["length"] is None
    clock.advance(1000.0)
    core.tick()
    assert core.snapshot()["now"]["pattern"] == "plain"
    assert core.snapshot()["now"]["holding"] is False


def test_hold_on_empty_keeps_last_pattern_looping(tmp_path, registry, lights):
    core, _spawn, clock = make_stage(tmp_path, registry, lights)
    seen_t = []
    original_frame = core.engine.frame
    core.engine.frame = lambda t: (seen_t.append(t), original_frame(t))[1]

    core.append({"pattern": "plain", "duration": 1.0})
    clock.advance(1.5)
    core.tick()  # expired -> hold; never dark
    snap = core.snapshot()
    assert snap["now"]["holding"] is True
    assert snap["now"]["pattern"] == "plain"  # the LAST pattern, held
    assert snap["now"]["index"] == 1 == len(snap["entries"])
    # The hold loops at the entry's length: t wraps, seamlessly.
    assert seen_t[-1] == pytest.approx(0.5)  # 1.5 % 1.0
    clock.advance(0.8)
    core.tick()
    assert seen_t[-1] == pytest.approx(0.3)  # 2.3 % 1.0
    # Skipping while already holding changes nothing.
    core.skip()
    assert core.snapshot()["now"]["holding"] is True


def test_audio_lifecycle_skip_and_advance_kill_player(tmp_path, registry, lights):
    core, spawn, clock = make_stage(tmp_path, registry, lights)
    core.append({"pattern": "plain", "audio": "track1.mp3"})
    core.append({"pattern": "timed", "duration": 5.0, "audio": "b side.wav"})
    assert len(spawn.procs) == 1
    first = spawn.procs[0]
    assert first.argv[0] == "fakeplay"
    assert first.argv[-1].endswith("track1.mp3")
    assert core.audio.playing is True
    assert core.snapshot()["audio_playing"] is True

    core.skip()  # skip kills the player and starts the next entry's audio
    assert first.terminated is True
    assert len(spawn.procs) == 2
    second = spawn.procs[1]
    assert second.argv[-1].endswith("b side.wav")
    assert core.snapshot()["now"]["pattern"] == "timed"

    clock.advance(5.1)
    core.tick()  # timed advance (to hold) kills audio too
    assert second.terminated is True
    assert core.audio.playing is False
    assert core.snapshot()["now"]["holding"] is True


def test_no_player_entries_still_play(tmp_path, registry, lights):
    core, spawn, _clock = make_stage(tmp_path, registry, lights, command=None)
    core.append({"pattern": "plain", "audio": "track1.mp3"})
    assert spawn.procs == []  # nothing to spawn
    snap = core.snapshot()
    assert snap["audio_player"] is None
    assert snap["now"]["pattern"] == "plain"  # the entry plays regardless


def test_queue_crud_and_index_fixups(tmp_path, registry, lights):
    core, _spawn, _clock = make_stage(tmp_path, registry, lights)
    for name in ("plain", "timed", "plain", "timed"):
        core.append({"pattern": name})
    assert core.snapshot()["now"]["index"] == 0  # first append started

    # Move an upcoming entry up; the playing index is untouched.
    core.move(3, 1)
    assert [e["pattern"] for e in core.snapshot()["entries"]] == [
        "plain",
        "timed",
        "timed",
        "plain",
    ]
    assert core.snapshot()["now"]["index"] == 0

    # Moving across the playing entry keeps the index on the same entry.
    core.move(0, 2)
    snap = core.snapshot()
    assert snap["now"]["index"] == 2 and snap["now"]["pattern"] == "plain"

    # Removing history shifts the index with it.
    core.remove(0)
    snap = core.snapshot()
    assert snap["now"]["index"] == 1 and snap["now"]["pattern"] == "plain"

    # Removing the playing entry starts what slides into its slot.
    core.remove(1)
    snap = core.snapshot()
    assert [e["pattern"] for e in snap["entries"]] == ["timed", "plain"]
    assert snap["now"]["index"] == 1 and snap["now"]["pattern"] == "plain"

    # Out-of-range operations are refused whole.
    with pytest.raises(StageError):
        core.remove(99)
    with pytest.raises(StageError):
        core.move(0, 99)

    # Clear drops the tracklist but keeps the pattern playing (hold).
    core.clear()
    snap = core.snapshot()
    assert snap["entries"] == []
    assert snap["now"]["holding"] is True
    assert snap["now"]["pattern"] == "plain"


def test_persistence_roundtrip(tmp_path, registry, lights):
    core, _spawn, _clock = make_stage(tmp_path, registry, lights)
    core.append({"pattern": "plain", "duration": 30.0})
    core.append({"pattern": "timed", "audio": "track1.mp3"})
    core.skip()  # now playing entry 1

    doc = json.loads((tmp_path / "stage" / "queue.json").read_text())
    assert doc["index"] == 1 and len(doc["entries"]) == 2

    # A restarted stage resumes the same entry from ITS OWN start —
    # fresh clock, fresh audio process.
    core2, spawn2, _clock2 = make_stage(tmp_path, registry, lights)
    snap = core2.snapshot()
    assert [e["pattern"] for e in snap["entries"]] == ["plain", "timed"]
    assert snap["now"]["index"] == 1 and snap["now"]["pattern"] == "timed"
    assert snap["now"]["elapsed"] == pytest.approx(0.0)
    assert spawn2.procs[-1].argv[-1].endswith("track1.mp3")  # audio restarts

    # A cleared stage remembers what it was holding.
    core2.clear()
    core3, _spawn3, _clock3 = make_stage(tmp_path, registry, lights)
    snap = core3.snapshot()
    assert snap["entries"] == [] and snap["now"]["holding"] is True
    assert snap["now"]["pattern"] == "timed"


def test_unknown_persisted_pattern_skipped(tmp_path, registry, lights):
    """A queue.json whose entry names a pattern the registry lost is
    skipped over (never a crash, never dark)."""
    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    (stage_dir / "queue.json").write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {"pattern": "deleted_show", "duration": None, "audio": None},
                    {"pattern": "plain", "duration": None, "audio": None},
                ],
                "index": 0,
                "held_pattern": "spiral",
            }
        )
    )
    core, _spawn, _clock = make_stage(tmp_path, registry, lights)
    snap = core.snapshot()
    assert snap["now"]["index"] == 1 and snap["now"]["pattern"] == "plain"


def test_queue_entry_model():
    entry = QueueEntry.model_validate({"pattern": "x"})
    assert entry.duration is None and entry.audio is None
    assert QueueEntry.model_validate(
        {"pattern": "x", "duration": 12, "audio": "a.mp3"}
    ).duration == pytest.approx(12.0)


# ---------------------------------------------------------------- chapters


def test_expansion_at_head_titles_offsets_notes(tmp_path, registry, lights):
    """A composition reaching the head becomes one entry per top-level
    chapter (composition/chapter titles, absolute offsets, chapter
    notes); the instance's audio rides the first chapter only; a nested
    composition stays one level deep until IT reaches the head."""
    core, spawn, _clock = make_stage(tmp_path, registry, lights)
    core.append({"pattern": "album", "audio": "track1.mp3", "repeat": False})
    snap = core.snapshot()
    rows = snap["entries"]
    # Expanded at head (the append started it): top-level chapters only.
    assert [e["title"] for e in rows] == ["album/dawn", "album/mid", "album/coda"]
    assert [e["pattern"] for e in rows] == ["album"] * 3
    assert [e["offset"] for e in rows] == [0.0, 5.0, 12.0]
    assert [e["duration"] for e in rows] == [5.0, 7.0, 5.0]
    assert [e["notes"] for e in rows] == ["first light", "the middle", "the end"]
    assert [e["audio"] for e in rows] == ["track1.mp3", None, None]
    assert [e["chapter"] for e in rows] == [[0], [1], [2]]
    assert len(spawn.procs) == 1  # the instance's audio started with chapter 1
    assert snap["now"]["index"] == 0 and snap["now"]["title"] == "album/dawn"
    assert snap["now"]["notes"] == "first light"

    # The nested chapter expands (one level again) when it becomes head.
    core.skip()
    rows = core.snapshot()["entries"]
    assert [e["title"] for e in rows] == [
        "album/dawn",
        "album/mid/one",
        "album/mid/two",
        "album/coda",
    ]
    assert [e["offset"] for e in rows] == [0.0, 5.0, 9.0, 12.0]
    assert [e["duration"] for e in rows] == [5.0, 4.0, 3.0, 5.0]
    assert [e["notes"] for e in rows][1:3] == ["inner one", "inner two"]
    assert [e["chapter"] for e in rows][1:3] == [[1, 0], [1, 1]]
    now = core.snapshot()["now"]
    assert now["index"] == 1 and now["title"] == "album/mid/one"
    assert now["pattern"] == "album" and now["offset"] == pytest.approx(5.0)


def test_loop_instance_duration_is_one_pass(tmp_path, registry, lights):
    """An instance of a loop=True composition gets pattern.total; queued
    behind something, it stays an unexpanded instance until head."""
    core, _spawn, _clock = make_stage(tmp_path, registry, lights)
    core.append({"pattern": "plain", "repeat": False})
    core.append({"pattern": "album", "repeat": False})
    entry = core.snapshot()["entries"][1]
    assert entry["duration"] == pytest.approx(17.0)  # 5 + 7 + 5: one pass
    assert entry["chapter"] is None and entry["title"] is None  # not yet expanded


def test_seamless_chapter_advance_only_deltas(tmp_path, registry, lights):
    """Adjacent chapters of one composition advance with NO keyframe and
    NO set_pattern: the timeline is continuous (t keeps counting through
    the boundary) and audio keeps playing — the composition plays
    exactly as if unchaptered."""
    core, spawn, clock = make_stage(tmp_path, registry, lights)
    engine = core.engine
    seen_t = []
    original_frame = engine.frame
    engine.frame = lambda t: (seen_t.append(t), original_frame(t))[1]
    swaps = []
    original_set = engine.set_pattern
    engine.set_pattern = lambda pat: (swaps.append(pat.name), original_set(pat))[1]

    stream = []
    core.sinks.append(stream.extend)
    core.append({"pattern": "suite", "audio": "track1.mp3", "repeat": False})
    assert [e["title"] for e in core.snapshot()["entries"]] == [
        "suite/one",
        "suite/two",
    ]
    assert swaps == ["suite"]  # the instance start swapped the pattern in

    clock.advance(0.5)
    core.tick()  # entry start forced a keyframe (+ same-tick heal)
    boundary_start = len(stream)
    for _ in range(8):  # 0.5 s steps through the 4.0 s chapter boundary
        clock.advance(0.5)
        core.tick()
    snap = core.snapshot()
    assert snap["now"]["index"] == 1 and snap["now"]["title"] == "suite/two"
    assert snap["now"]["notes"] == "the second part"
    assert swaps == ["suite"]  # NO second set_pattern at the boundary
    assert spawn.procs[0].terminated is False  # audio plays straight through
    # t is continuous through the boundary: strictly increasing, and the
    # first frame of chapter two picks up at boundary + lag, not at 4.0.
    assert seen_t == sorted(seen_t)
    assert seen_t[-1] == pytest.approx(4.5)
    assert snap["now"]["elapsed"] == pytest.approx(0.5)  # 4.5 on the timeline
    # The wire across the boundary: deltas only — never a keyframe.
    types = _decode_all(engine, stream)
    assert set(types[boundary_start:]) == {p.FRAME_DELTA}


def test_skip_is_next_chapter_and_jumps_keyframe(tmp_path, registry, lights):
    """Skip advances exactly one chapter; landing mid-timeline is a jump,
    so it re-keyframes (unlike the seamless natural advance)."""
    core, _spawn, clock = make_stage(tmp_path, registry, lights)
    engine = core.engine
    stream = []
    core.sinks.append(stream.extend)
    core.append({"pattern": "suite", "repeat": False})
    clock.advance(0.5)
    core.tick()  # keyframe + heal for the instance start
    clock.advance(0.5)
    core.tick()  # delta
    core.skip()  # t=1.0 of 4.0: a jump to chapter two's start
    snap = core.snapshot()
    assert snap["now"]["index"] == 1 and snap["now"]["title"] == "suite/two"
    assert snap["now"]["offset"] == pytest.approx(4.0)
    assert snap["now"]["elapsed"] == pytest.approx(0.0)
    clock.advance(0.5)
    core.tick()
    types = _decode_all(engine, stream)
    # keyframe+heal (start), delta, then keyframe+heal again: the skip.
    assert types == [
        p.FRAME_KEYFRAME,
        p.FRAME_DELTA,
        p.FRAME_DELTA,
        p.FRAME_KEYFRAME,
        p.FRAME_DELTA,
    ]
    # Skipping the last chapter (nothing queued, no repeats) holds.
    core.skip()
    assert core.snapshot()["now"]["holding"] is True


# ----------------------------------------------------------------- repeats


def test_repeat_flag_defaults_to_pattern_loop(tmp_path, registry, lights):
    core, _spawn, _clock = make_stage(tmp_path, registry, lights)
    core.append({"pattern": "album"})  # loop=True: repeat defaults ON
    snap = core.snapshot()
    assert [t["pattern"] for t in snap["repeats"]] == ["album"]
    assert all(e["repeat"] for e in snap["entries"])  # the marker survives expansion

    core.append({"pattern": "plain"})  # not configured to repeat
    assert [t["pattern"] for t in core.snapshot()["repeats"]] == ["album"]

    core.append({"pattern": "album", "repeat": False})  # the VJ unchecked it
    snap = core.snapshot()
    assert [t["pattern"] for t in snap["repeats"]] == ["album"]
    assert snap["entries"][-1]["repeat"] is False


def test_repeats_cycle_round_robin(tmp_path, registry, lights):
    """Queue out -> pop the head token, append one instance (it expands
    at head as usual), token to the end — the cycle plays forever in
    order. Tokens are {pattern, title, audio}: a respawned instance runs
    its pattern's own length."""
    core, _spawn, clock = make_stage(tmp_path, registry, lights)
    core.append({"pattern": "timed", "repeat": True})  # own duration: 2.0
    core.append({"pattern": "suite", "repeat": True})  # 4.0 + 3.0 chapters
    snap = core.snapshot()
    assert [t["pattern"] for t in snap["repeats"]] == ["timed", "suite"]
    assert len(snap["entries"]) == 2

    clock.advance(2.1)
    core.tick()  # timed -> suite: a normal advance; suite expands at head
    snap = core.snapshot()
    assert snap["now"]["title"] == "suite/one" and len(snap["entries"]) == 3

    clock.advance(4.1)
    core.tick()  # suite/one -> suite/two (seamless)
    clock.advance(3.1)
    core.tick()  # queue out: spawn timed (head token), token to the end
    snap = core.snapshot()
    assert snap["now"]["holding"] is False
    assert snap["now"]["pattern"] == "timed"
    assert snap["now"]["index"] == 3 and len(snap["entries"]) == 4
    assert snap["entries"][-1]["repeat"] is True
    assert snap["entries"][-1]["duration"] is None  # the pattern's own 2.0 rules
    assert snap["now"]["length"] == pytest.approx(2.0)
    assert [t["pattern"] for t in snap["repeats"]] == ["suite", "timed"]

    clock.advance(2.1)
    core.tick()  # and around again: suite spawns and expands
    snap = core.snapshot()
    assert snap["now"]["title"] == "suite/one"
    assert [t["pattern"] for t in snap["repeats"]] == ["timed", "suite"]

    # Cancelling every token ends the cycle: the next run-out holds.
    core.remove_repeat(1)
    core.remove_repeat(0)
    assert core.snapshot()["repeats"] == []
    core.skip()  # suite/one -> suite/two (the play-through remainder)
    core.skip()
    assert core.snapshot()["now"]["holding"] is True


def test_repeats_move_and_bounds(tmp_path, registry, lights):
    core, _spawn, _clock = make_stage(tmp_path, registry, lights)
    for name in ("plain", "timed", "suite"):
        core.append({"pattern": name, "repeat": True})
    assert [t["pattern"] for t in core.snapshot()["repeats"]] == [
        "plain",
        "timed",
        "suite",
    ]
    core.move_repeat(2, 0)
    assert [t["pattern"] for t in core.snapshot()["repeats"]] == [
        "suite",
        "plain",
        "timed",
    ]
    with pytest.raises(StageError):
        core.move_repeat(0, 9)
    with pytest.raises(StageError):
        core.remove_repeat(9)


def test_play_next_inserts_after_playing(tmp_path, registry, lights):
    core, _spawn, _clock = make_stage(tmp_path, registry, lights)
    for name in ("plain", "timed", "plain"):
        core.append({"pattern": name, "repeat": False})
    assert core.snapshot()["now"]["index"] == 0

    core.play_next({"pattern": "suite", "repeat": False})
    snap = core.snapshot()
    assert [e["pattern"] for e in snap["entries"]] == [
        "plain",
        "suite",
        "timed",
        "plain",
    ]
    assert snap["now"]["index"] == 0  # still the playing entry
    assert snap["entries"][1]["chapter"] is None  # expands only at head

    # play_next honors the repeat checkbox: token to the END of repeats.
    core.append({"pattern": "album"})  # seeds a token first
    core.play_next({"pattern": "timed", "repeat": True})
    snap = core.snapshot()
    assert [t["pattern"] for t in snap["repeats"]] == ["album", "timed"]
    assert snap["entries"][1]["pattern"] == "timed"  # newest play-next is next

    # From the hold, play_next starts immediately (same as append).
    core.clear()
    (tmp_path / "b").mkdir()
    core2, _spawn2, _clock2 = make_stage(tmp_path / "b", registry, lights)
    assert core2.snapshot()["now"]["holding"] is True
    snap = core2.play_next({"pattern": "plain", "repeat": False})
    assert snap["now"]["holding"] is False and snap["now"]["pattern"] == "plain"


def test_old_queue_json_loads_with_defaults(tmp_path, registry, lights):
    """A pre-chapter/repeats queue.json (no offset/title/notes/repeat,
    no repeats list) loads with the new fields defaulted."""
    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    (stage_dir / "queue.json").write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {"pattern": "plain", "duration": None, "audio": None},
                    {"pattern": "timed", "duration": 5.0, "audio": None},
                ],
                "index": 0,
                "held_pattern": "spiral",
            }
        )
    )
    core, _spawn, _clock = make_stage(tmp_path, registry, lights)
    snap = core.snapshot()
    assert snap["repeats"] == []
    assert snap["now"]["index"] == 0 and snap["now"]["pattern"] == "plain"
    assert snap["now"]["title"] == "plain"
    assert snap["now"]["notes"] == "steady and plain"  # the pattern's own
    entry = snap["entries"][0]
    assert entry["offset"] == 0.0 and entry["repeat"] is False
    assert entry["title"] is None and entry["chapter"] is None
    # The rewritten file carries the new schema.
    doc = json.loads((stage_dir / "queue.json").read_text())
    assert doc["version"] == 2 and doc["repeats"] == []


def test_persistence_roundtrip_with_chapters_and_repeats(tmp_path, registry, lights):
    """A restart resumes the same chapter entry (offset intact, from its
    own start) and keeps the repeats cycle."""
    core, _spawn, _clock = make_stage(tmp_path, registry, lights)
    core.append({"pattern": "album"})  # repeat defaults on; expands at head
    core.skip()  # album/mid/one is now playing (offset 5.0)
    snap = core.snapshot()
    assert snap["now"]["title"] == "album/mid/one"

    core2, _spawn2, _clock2 = make_stage(tmp_path, registry, lights)
    snap = core2.snapshot()
    assert snap["now"]["title"] == "album/mid/one"
    assert snap["now"]["offset"] == pytest.approx(5.0)
    assert snap["now"]["elapsed"] == pytest.approx(0.0)  # restarts at ITS start
    assert [t["pattern"] for t in snap["repeats"]] == ["album"]


def test_status_notes_fallback_for_plain_patterns(tmp_path, registry, lights):
    core, _spawn, _clock = make_stage(tmp_path, registry, lights)
    core.append({"pattern": "plain", "repeat": False})
    now = core.snapshot()["now"]
    assert now["title"] == "plain" and now["notes"] == "steady and plain"
    core.skip()  # hold keeps the last title/notes on display
    now = core.snapshot()["now"]
    assert now["holding"] is True and now["notes"] == "steady and plain"


def test_patterns_meta_and_chapters_of(tmp_path, registry, lights):
    core, _spawn, _clock = make_stage(tmp_path, registry, lights)
    meta = {row["name"]: row for row in core.patterns_meta()}
    assert meta["album"]["loop"] is True and meta["album"]["has_chapters"] is True
    assert meta["suite"]["loop"] is False and meta["suite"]["has_chapters"] is True
    assert meta["suite"]["notes"] == "a small suite"
    assert meta["plain"]["loop"] is False and meta["plain"]["has_chapters"] is False
    assert meta["plain"]["notes"] == "steady and plain"

    tree = core.chapters_of("album")
    assert [node["title"] for node in tree] == ["dawn", "mid", "coda"]
    assert [c["title"] for c in tree[1]["children"]] == ["one", "two"]
    assert [c["start"] for c in tree[1]["children"]] == [5.0, 9.0]
    assert core.chapters_of("plain") == []
    with pytest.raises(StageError, match="unknown pattern"):
        core.chapters_of("nope")


def test_detect_player_override_and_fallback(monkeypatch):
    assert detect_player("mycmd --flag x") == ["mycmd", "--flag", "x"]
    monkeypatch.setattr("luminary.stage.audio.shutil.which", lambda name: None)
    assert detect_player(None) is None
    monkeypatch.setattr(
        "luminary.stage.audio.shutil.which",
        lambda name: "/usr/bin/cvlc" if name == "cvlc" else None,
    )
    assert detect_player(None) == ["cvlc", "--play-and-exit", "--intf", "dummy"]


def test_declared_audio_defaults_into_entries(tmp_path, registry, lights):
    """A pattern's declared soundtrack attaches by default when the file
    exists; an explicit empty string means none; a declared file that is
    not on disk never attaches (and never errors)."""
    core, _spawn, _clock = make_stage(tmp_path, registry, lights)

    core.append({"pattern": "scored"})
    assert core.snapshot()["entries"][-1]["audio"] == "track1.mp3"

    core.append({"pattern": "scored", "audio": ""})
    assert core.snapshot()["entries"][-1]["audio"] is None

    core.append({"pattern": "scored", "audio": "b side.wav"})
    assert core.snapshot()["entries"][-1]["audio"] == "b side.wav"

    core.append({"pattern": "unscored"})
    assert core.snapshot()["entries"][-1]["audio"] is None

    meta = {row["name"]: row for row in core.patterns_meta() if row.get("ok")}
    assert meta["scored"]["audio"] == "track1.mp3"
    assert meta["scored"]["audio_present"] is True
    assert meta["unscored"]["audio"] == "nowhere.mp3"
    assert meta["unscored"]["audio_present"] is False
    assert meta["plain"]["audio"] == ""

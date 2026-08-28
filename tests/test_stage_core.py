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

    def render(self, lights, t):
        out = np.zeros((lights.shape[0], 3))
        out[:, 0] = 0.4
        out[:, 1] = 0.05
        out[:, 2] = (t * 30.0) % 360.0
        return out
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


def test_detect_player_override_and_fallback(monkeypatch):
    assert detect_player("mycmd --flag x") == ["mycmd", "--flag", "x"]
    monkeypatch.setattr("luminary.stage.audio.shutil.which", lambda name: None)
    assert detect_player(None) is None
    monkeypatch.setattr(
        "luminary.stage.audio.shutil.which",
        lambda name: "/usr/bin/cvlc" if name == "cvlc" else None,
    )
    assert detect_player(None) == ["cvlc", "--play-and-exit", "--intf", "dummy"]

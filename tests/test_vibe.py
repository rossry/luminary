"""Vibe mode (luminary/vibe/): a prompt goes to a coding model, the reply
is validated on the stage's own lights, saved as generation #N — never
overwritten — and hot-cut onto the stage; every page shares that state.

The model is a fake on both backends: ``Coder(transport=...)`` answers
with scripted replies, and ``SessionCoder(runner=...)`` is driven by a
fake Claude Code session that calls the ``ship_pattern`` tool the way
the SDK would. No network, no CLI, no real player — the stage is the
same fake-clock core the stage tests use.
"""

import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from luminary.patterns.registry import PatternRegistry
from luminary.stage.web import register_stage
from luminary.vibe.coder import Coder, extract
from luminary.vibe.core import VibeCore, VibeError, assign_identity
from luminary.vibe.session import SHIP_TOOL, SessionCoder
from luminary.vibe.web import register_vibe
from tests.test_stage_core import (  # noqa: F401 — imported fixtures
    PATTERN_SOURCES,
    lights,
    make_stage,
)

# ----------------------------------------------------------------- replies

GOOD = """
import numpy as np
from luminary.patterns.base import Pattern

class SlowTide(Pattern):
    name = "slow-tide"
    description = "a slow tide"
    notes = "Rising and falling, slowly."

    def render(self, lights, t):
        out = np.zeros((lights.shape[0], 3))
        out[:, 0] = 0.1 + 0.05 * np.sin(t / 7.0)
        out[:, 1] = 0.08
        out[:, 2] = 250.0
        return out
"""

BROKEN = """
import numpy as np
from luminary.patterns.base import Pattern

class TwoWide(Pattern):
    name = "two-wide"
    description = "returns the wrong shape"

    def render(self, lights, t):
        return np.zeros((lights.shape[0], 2))
"""

NONFINITE = GOOD.replace(
    "out[:, 0] = 0.1 + 0.05 * np.sin(t / 7.0)", "out[:, 0] = np.nan"
)

STATEFUL = """
import numpy as np
from luminary.patterns.base import Pattern

class Counter(Pattern):
    name = "counter"
    description = "depends on call order"

    def render(self, lights, t):
        self.k = getattr(self, "k", 0) + 1
        out = np.zeros((lights.shape[0], 3))
        out[:, 0] = 0.01 * self.k
        return out
"""


def reply(code, note=""):
    return (note + "\n" if note else "") + "```python\n" + code.strip() + "\n```\n"


class ScriptedModel:
    """A transport for ``Coder``: canned replies in order, every call kept."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, system, messages):
        self.calls.append(messages)
        if not self.replies:
            raise RuntimeError("model went away")
        return self.replies.pop(0)


# ----------------------------------------------------------------- fixture

REPO_FILES = {
    "spiral.py": PATTERN_SOURCES["spiral.py"],
    "book-two/plain.py": PATTERN_SOURCES["plain.py"],
    "conifer/timed.py": PATTERN_SOURCES["timed.py"],
}


def make_vibe(tmp_path, lights, coder, models=("m-fast", "m-deep")):  # noqa: F811
    """A VibeCore over a repo-shaped pattern tree plus its own vibe dir,
    on a fake-clock stage. Returns (core, stage, registry)."""
    patterns = tmp_path / "patterns"
    for rel, source in REPO_FILES.items():
        (patterns / rel).parent.mkdir(parents=True, exist_ok=True)
        (patterns / rel).write_text(source)
    vibe_dir = tmp_path / "state" / "vibe"
    vibe_dir.mkdir(parents=True, exist_ok=True)
    registry = PatternRegistry([patterns, vibe_dir])
    stage, _spawn, _clock = make_stage(tmp_path / "state", registry, lights)
    core = VibeCore(
        vibe_dir, registry, stage, coder, models=list(models), backend="fake"
    )
    if hasattr(coder, "validator"):
        coder.validator = core.validate
    return core, stage, registry


# ------------------------------------------------------------- the parser


def test_extract_note_and_fence():
    code, note = extract("Slower this time?\n```python\nclass A: pass\n```\n")
    assert code == "class A: pass\n" and note == "Slower this time?"
    # No fence, but it is plainly a module: taken as code.
    code, note = extract("class B(Pattern):\n    def render(self, l, t): ...")
    assert code.startswith("class B") and note == ""
    # No code at all: the words are the note.
    assert extract("I need more to go on.") == ("", "I need more to go on.")


def test_assign_identity_cases():
    out = assign_identity(GOOD, "vibe-3", "unused")
    assert "name = 'vibe-3'" in out and "slow-tide" not in out
    assert 'description = "a slow tide"' in out  # kept: it had one

    bare = 'class X(Pattern):\n    """doc"""\n    def render(self, l, t):\n        return l\n'
    out = assign_identity(bare, "vibe-4", "from the prompt")
    lines = out.splitlines()
    assert lines[1].strip() == '"""doc"""'  # after the docstring...
    assert lines[2] == "    name = 'vibe-4'"  # ...name, then description
    assert lines[3] == "    description = 'from the prompt'"

    described = 'class Y(Pattern):\n    description = "d"\n    def render(self, l, t):\n        return l\n'
    out = assign_identity(described, "vibe-5", "x")
    assert out.splitlines()[1] == "    name = 'vibe-5'"

    tuned = "from luminary.patterns.primitives import NoiseGlow\n\nclass Dusk(NoiseGlow):\n    speed = 0.02\n"
    out = assign_identity(tuned, "vibe-6", "dusk")  # no render: the last class
    assert "    name = 'vibe-6'\n    description = 'dusk'\n    speed = 0.02" in out

    with pytest.raises(ValueError, match="no class"):
        assign_identity("x = 1\n", "vibe-7", "d")
    with pytest.raises(ValueError, match="does not parse"):
        assign_identity("class (:\n", "vibe-8", "d")


# ------------------------------------------------------------ the thread


def test_submit_numbers_from_one_and_captures_context(tmp_path, lights):  # noqa: F811
    core, stage, _registry = make_vibe(
        tmp_path, lights, Coder(transport=ScriptedModel())
    )
    entry = core.submit(
        {"prompt": "  something blue ", "name": "Blue", "author": "ross"}
    )
    assert entry["n"] == 1 and entry["pattern"] == "vibe-1"
    assert entry["status"] == "queued" and entry["model"] == "m-fast"  # the default
    assert entry["shown"] == "spiral"  # the holding stage's default, at submit time
    assert entry["prompt"] == "something blue"

    queued = core._pending.get_nowait()
    assert "StandInSpiral" in queued["shown_source"]  # the source travels with it

    log = json.loads((tmp_path / "state" / "vibe" / "log.json").read_text())
    assert log["version"] == 1 and log["generations"][0]["n"] == 1

    snap = core.snapshot()
    assert snap["queue"][0]["n"] == 1 and snap["generations"][0]["n"] == 1
    assert snap["models"] == ["m-fast", "m-deep"] and snap["enabled"] is True

    with pytest.raises(VibeError, match="say what"):
        core.submit({"prompt": "   "})
    with pytest.raises(VibeError, match="unknown model"):
        core.submit({"prompt": "x", "model": "gpt-9"})


def test_cook_saves_registers_and_cuts(tmp_path, lights):  # noqa: F811
    model = ScriptedModel(reply(GOOD, "Went slow and blue."), reply(GOOD))
    core, stage, registry = make_vibe(tmp_path, lights, Coder(transport=model))
    core.submit({"prompt": "slow and blue", "name": "Tide", "author": "ross"})
    assert core.process_one() is True

    entry = core.generations[0]
    assert entry["status"] == "ok" and entry["note"] == "Went slow and blue."
    assert entry["file"] == "vibe-0001.py"
    source = (tmp_path / "state" / "vibe" / "vibe-0001.py").read_text()
    assert source.startswith("# vibe #1 — Tide\n# by: ross   model: m-fast")
    assert "# prompt: slow and blue\n# shown when typed: spiral\n" in source
    assert "name = 'vibe-1'" in source

    assert "vibe-1" in registry.patterns  # a real pattern now
    assert stage.snapshot()["now"]["pattern"] == "vibe-1"  # hot-cut
    assert stage.snapshot()["now"]["holding"] is False

    snap = core.snapshot()
    assert snap["now"] == {
        "pattern": "vibe-1",
        "title": "#1 Tide",
        "n": 1,
        "author": "ross",
        "prompt": "slow and blue",
        "notes": "Rising and falling, slowly.",
    }
    assert [g["n"] for g in snap["menu"]["named"]] == [1]
    assert [g["n"] for g in snap["menu"]["all"]] == [1]
    assert snap["working"] is None and snap["queue"] == []

    # The next prompt is about THIS one: its source rides along, and the
    # model is told what was showing.
    core.submit({"prompt": "more purple"})
    assert core.process_one() is True
    brief = model.calls[1][0]["content"]
    assert "was typed was `vibe-1`" in brief and "# vibe #1 — Tide" in brief
    assert core.generations[1]["shown_title"] == "#1 Tide"
    assert core.generations[1]["pattern"] == "vibe-2"
    assert stage.snapshot()["now"]["pattern"] == "vibe-2"
    assert sorted(p.name for p in (tmp_path / "state" / "vibe").glob("vibe-*.py")) == [
        "vibe-0001.py",
        "vibe-0002.py",
    ]


def test_from_scratch_drops_the_context(tmp_path, lights):  # noqa: F811
    model = ScriptedModel(reply(GOOD))
    core, _stage, _registry = make_vibe(tmp_path, lights, Coder(transport=model))
    core.submit({"prompt": "something new", "from_scratch": True})
    core.process_one()
    brief = model.calls[0][0]["content"]
    assert "Start from scratch; ignore the current pattern (spiral)" in brief
    assert "StandInSpiral" not in brief
    assert (
        "(started from scratch)"
        in (tmp_path / "state" / "vibe" / "vibe-0001.py").read_text()
    )


def test_repair_round_keeps_the_rejected_draft(tmp_path, lights):  # noqa: F811
    model = ScriptedModel(reply(BROKEN, "first try"), reply(GOOD, "fixed the shape"))
    core, stage, _registry = make_vibe(tmp_path, lights, Coder(transport=model))
    core.submit({"prompt": "anything"})
    core.process_one()

    entry = core.generations[0]
    assert entry["status"] == "ok" and entry["note"] == "fixed the shape"
    repair = model.calls[1]  # brief, the draft, what broke
    assert repair[1]["role"] == "assistant" and "TwoWide" in repair[1]["content"]
    assert "(n, 3) array" in repair[2]["content"]

    vibe_dir = tmp_path / "state" / "vibe"
    kept = (vibe_dir / "_vibe-0001-attempt1.py").read_text()
    assert "TwoWide" in kept and "name = 'vibe-1'" in kept  # stamped, and kept
    assert (vibe_dir / "vibe-0001.py").is_file()
    assert stage.snapshot()["now"]["pattern"] == "vibe-1"


def test_failed_generation_is_kept_and_numbering_moves_on(
    tmp_path, lights
):  # noqa: F811
    model = ScriptedModel(reply(BROKEN), reply(NONFINITE), reply(GOOD))
    core, stage, registry = make_vibe(tmp_path, lights, Coder(transport=model))
    core.submit({"prompt": "doomed", "name": "Doomed"})
    core.process_one()

    entry = core.generations[0]
    assert entry["status"] == "failed" and "non-finite" in entry["error"]
    assert entry["file"] == "_vibe-0001-failed.py"
    vibe_dir = tmp_path / "state" / "vibe"
    assert (vibe_dir / "_vibe-0001-attempt1.py").is_file()
    assert (vibe_dir / "_vibe-0001-failed.py").is_file()
    assert not (vibe_dir / "vibe-0001.py").exists()
    assert "vibe-1" not in registry.patterns
    assert stage.snapshot()["now"]["pattern"] == "spiral"  # untouched

    snap = core.snapshot()
    assert snap["menu"]["named"] == [] and snap["menu"]["all"] == []
    assert snap["generations"][0]["status"] == "failed"

    core.submit({"prompt": "again"})  # #2, never a reuse of #1
    core.process_one()
    assert core.generations[1]["pattern"] == "vibe-2"
    assert core.generations[1]["status"] == "ok"
    assert stage.snapshot()["now"]["pattern"] == "vibe-2"


def test_model_failure_is_a_failed_generation_not_a_dead_worker(
    tmp_path, lights
):  # noqa: F811
    core, _stage, _registry = make_vibe(
        tmp_path, lights, Coder(transport=ScriptedModel())
    )
    core.submit({"prompt": "hello"})
    assert core.process_one() is True
    entry = core.generations[0]
    assert entry["status"] == "failed" and "model went away" in entry["error"]
    assert core.snapshot()["working"] is None
    assert core.process_one() is False  # nothing left, still alive


def test_validate_names_what_broke(tmp_path, lights):  # noqa: F811
    core, _stage, _registry = make_vibe(
        tmp_path, lights, Coder(transport=ScriptedModel())
    )
    assert core.validate(GOOD) is None
    assert "(n, 3) array" in core.validate(BROKEN)
    assert "non-finite" in core.validate(NONFINITE)
    assert "not stateless" in core.validate(STATEFUL)
    assert "SyntaxError" in core.validate("class (:\n")
    assert "No Pattern subclass" in core.validate("x = 1\n")
    # The scratch module never reaches the real registry.
    assert not any(
        "candidate" in name for name in core.registry.patterns
    ) and "_scratch" not in str(core.registry.list())


def test_menu_groups_the_repo_by_folder(tmp_path, lights):  # noqa: F811
    core, _stage, _registry = make_vibe(
        tmp_path, lights, Coder(transport=ScriptedModel(reply(GOOD)))
    )
    core.submit({"prompt": "x"})
    core.process_one()
    repo = core.snapshot()["menu"]["repo"]
    assert [group["folder"] for group in repo] == ["patterns", "book-two", "conifer"]
    assert [p["name"] for p in repo[0]["patterns"]] == ["spiral"]
    assert repo[1]["patterns"][0] == {
        "name": "plain",
        "description": "no duration: plays until skipped",
    }
    # Generations live in the menu's own sections, not the repo's.
    assert "vibe-1" not in {p["name"] for g in repo for p in g["patterns"]}


def test_select_cuts_to_any_registered_pattern(tmp_path, lights):  # noqa: F811
    core, stage, _registry = make_vibe(
        tmp_path, lights, Coder(transport=ScriptedModel())
    )
    snap = core.select("plain")
    assert snap["now"]["pattern"] == "plain" and snap["now"]["title"] == "plain"
    assert stage.snapshot()["now"]["pattern"] == "plain"
    with pytest.raises(VibeError, match="unknown pattern"):
        core.select("nope")
    # What is showing is the context of the next prompt.
    assert core.submit({"prompt": "brighter"})["shown"] == "plain"


def test_restart_leaves_no_prompt_silently_lost(tmp_path, lights):  # noqa: F811
    vibe_dir = tmp_path / "state" / "vibe"
    vibe_dir.mkdir(parents=True)
    stale = {
        "n": 1,
        "pattern": "vibe-1",
        "name": "",
        "author": "",
        "prompt": "was cooking",
        "model": "m-fast",
        "shown": "spiral",
        "shown_title": "spiral",
        "from_scratch": False,
        "note": "",
        "status": "cooking",
        "error": "",
        "file": "",
        "created": "2026-09-21T00:00:00+00:00",
    }
    (vibe_dir / "log.json").write_text(
        json.dumps({"version": 1, "generations": [stale]})
    )
    core, _stage, _registry = make_vibe(
        tmp_path, lights, Coder(transport=ScriptedModel())
    )
    entry = core.generations[0]
    assert entry["status"] == "failed" and "restarted" in entry["error"]
    assert core.submit({"prompt": "next"})["n"] == 2  # the thread continues


# ------------------------------------------------------ the session backend


class _Block:
    def __init__(self, text):
        self.text = text


class TextBlock(_Block):
    pass


class AssistantMessage:
    def __init__(self, *blocks):
        self.content = list(blocks)


def test_session_backend_ships_through_the_tool():
    seen = {}

    async def runner(prompt, options):
        seen["prompt"], seen["options"] = prompt, options
        ship = options["ship"]
        first = await ship({"code": "BROKEN", "note": "try one"})
        assert first["content"][0]["text"].startswith("rejected:\nno good")
        second = await ship({"code": "GOOD", "note": "try two"})
        assert second["content"][0]["text"].startswith("ok: accepted")
        yield AssistantMessage(TextBlock("Slower this time — want it bluer?"))

    coder = SessionCoder(
        "/repo",
        model="m-deep",
        validator=lambda code: None if code == "GOOD" else "no good",
        runner=runner,
    )
    assert coder.available is True
    code, note = coder.draft({"prompt": "slower", "author": "ross", "shown": ""})
    assert code == "GOOD\n" and note == "try two"
    assert seen["prompt"].startswith("Prompt from ross: slower")
    options = seen["options"]
    assert options["cwd"] == "/repo" and options["model"] == "m-deep"
    assert SHIP_TOOL in options["allowed_tools"] and "Read" in options["allowed_tools"]
    assert (
        "Bash" in options["disallowed_tools"] and "Write" in options["disallowed_tools"]
    )
    assert options["permission_mode"] == "default"  # root refuses bypass
    assert options["setting_sources"] == []
    assert "ship_pattern" in options["system_prompt"]


def test_session_backend_falls_back_to_spoken_code_or_fails():
    async def talker(prompt, options):
        yield AssistantMessage(TextBlock("Here you go.\n```python\nclass A: pass\n```"))

    coder = SessionCoder("/repo", runner=talker)
    assert coder.draft({"prompt": "x"}) == ("class A: pass\n", "Here you go.")

    async def silent(prompt, options):
        yield AssistantMessage(TextBlock("Hmm."))

    with pytest.raises(RuntimeError, match="without shipping"):
        SessionCoder("/repo", runner=silent).draft({"prompt": "x"})

    async def repairer(prompt, options):
        assert "It failed on the server:" in prompt and "boom" in prompt
        await options["ship"]({"code": "GOOD", "note": ""})
        yield AssistantMessage(TextBlock("fixed"))

    coder = SessionCoder("/repo", validator=lambda c: None, runner=repairer)
    assert coder.repair({"prompt": "x"}, "old", "boom") == ("GOOD\n", "fixed")


def test_session_backend_end_to_end_on_the_stage(tmp_path, lights):  # noqa: F811
    """The session validates inside its turn against the core's own
    validator, and the core still runs its gates after."""
    attempts = []

    async def runner(prompt, options):
        for code in (BROKEN, GOOD):
            result = await options["ship"]({"code": code, "note": "shipped"})
            attempts.append(result["content"][0]["text"].split("\n")[0])
        yield AssistantMessage(TextBlock("Two tries."))

    core, stage, _registry = make_vibe(
        tmp_path, lights, SessionCoder("/repo", runner=runner)
    )
    core.submit({"prompt": "tide"})
    core.process_one()
    assert attempts == [
        "rejected:",
        "ok: accepted — it runs on the sphere. Say your note and stop.",
    ]
    assert core.generations[0]["status"] == "ok"
    assert core.generations[0]["note"] == "shipped"
    assert stage.snapshot()["now"]["pattern"] == "vibe-1"


# ---------------------------------------------------------------- the web


def test_http_routes(tmp_path, lights):  # noqa: F811
    core, stage, _registry = make_vibe(
        tmp_path, lights, Coder(transport=ScriptedModel(reply(GOOD)))
    )
    app = FastAPI()
    register_stage(app, stage)
    register_vibe(app, core)
    with TestClient(app) as client:
        page = client.get("/vibe")
        assert page.status_code == 200 and "stage-canvas" in page.text
        assert './static/vibe.js"' in page.text  # page-relative import

        snap = client.get("/api/vibe").json()
        assert snap["enabled"] is True and snap["models"] == ["m-fast", "m-deep"]
        assert snap["now"]["pattern"] == "spiral" and snap["generations"] == []

        response = client.post(
            "/api/vibe", json={"prompt": "hi", "author": "a", "model": "m-deep"}
        )
        assert response.status_code == 202
        assert response.json()["n"] == 1 and response.json()["model"] == "m-deep"
        assert client.post("/api/vibe", json={"prompt": " "}).status_code == 422
        assert client.get("/api/vibe").json()["queue"][0]["n"] == 1

        core.process_one()  # the worker's job, by hand
        snap = client.get("/api/vibe").json()
        assert snap["generations"][0]["status"] == "ok"
        assert snap["now"]["pattern"] == "vibe-1"

        assert (
            client.post("/api/vibe/select", json={"pattern": "nope"}).status_code == 404
        )
        snap = client.post("/api/vibe/select", json={"pattern": "plain"}).json()
        assert snap["now"]["pattern"] == "plain"
        # The stage page's own view agrees: one state.
        assert client.get("/api/queue").json()["now"]["pattern"] == "plain"


def test_http_mutations_take_the_stage_key(tmp_path, lights):  # noqa: F811
    core, stage, _registry = make_vibe(
        tmp_path, lights, Coder(transport=ScriptedModel())
    )
    app = FastAPI()
    register_stage(app, stage, stage_key="hush")
    register_vibe(app, core, stage_key="hush")
    with TestClient(app) as client:
        assert client.get("/api/vibe").status_code == 200  # reading is open
        assert client.post("/api/vibe", json={"prompt": "x"}).status_code == 403
        assert (
            client.post("/api/vibe/select", json={"pattern": "plain"}).status_code
            == 403
        )
        assert (
            client.post(
                "/api/vibe", json={"prompt": "x"}, headers={"X-Stage-Key": "hush"}
            ).status_code
            == 202
        )


def test_create_app_mounts_vibe_with_a_live_worker(tmp_path, lights):  # noqa: F811
    from luminary.server.app import create_app

    lights_path = tmp_path / "tiny.lights.json"
    lights.save(lights_path)
    fake = Coder(transport=ScriptedModel(reply(GOOD, "done")))
    app = create_app(
        state_dir=tmp_path / "state",
        stage=True,
        stage_lights=str(lights_path),
        vibe_coder=fake,
    )
    with TestClient(app) as client:
        health = client.get("/api/health").json()
        assert health["vibe"] is True and health["status"] == "ok"
        assert client.get("/vibe").status_code == 200
        assert client.get("/static/vibe.js").status_code == 200
        snap = client.get("/api/vibe").json()
        assert snap["backend"] == "custom" and snap["models"]  # the configured list

        assert client.post("/api/vibe", json={"prompt": "go"}).status_code == 202
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:  # the mounted worker cooks it
            snap = client.get("/api/vibe").json()
            if snap["generations"] and snap["generations"][0]["status"] != "queued":
                if snap["generations"][0]["status"] != "cooking":
                    break
            time.sleep(0.05)
        assert snap["generations"][0]["status"] == "ok", snap["generations"][0]
        assert snap["now"]["pattern"] == "vibe-1"
        assert client.get("/api/queue").json()["now"]["pattern"] == "vibe-1"
        assert (tmp_path / "state" / "vibe" / "vibe-0001.py").is_file()
        # Generations are ordinary patterns to the rest of the server.
        names = {row["name"] for row in client.get("/api/patterns").json()}
        assert "vibe-1" in names


def test_create_app_gates_vibe_like_upload(tmp_path, lights, monkeypatch):  # noqa: F811
    from luminary.server.app import create_app

    lights_path = tmp_path / "tiny.lights.json"
    lights.save(lights_path)
    monkeypatch.delenv("LUMINARY_STAGE_KEY", raising=False)
    fake = Coder(transport=ScriptedModel())

    def health(**kwargs):
        app = create_app(
            state_dir=tmp_path / "state",
            stage_lights=str(lights_path),
            vibe_coder=fake,
            **kwargs,
        )
        with TestClient(app) as client:
            return (
                client.get("/api/health").json()["vibe"],
                client.get("/vibe").status_code,
            )

    assert health(stage=True, allow_pattern_upload=False) == (
        False,
        404,
    )  # locked out...
    assert health(stage=True, allow_pattern_upload=False, stage_key="k") == (
        True,
        200,
    )  # ...unless keyed
    assert health(stage=True, vibe=False) == (False, 404)  # --no-vibe
    assert health(stage=False) == (False, 404)  # no stage, nothing to cut

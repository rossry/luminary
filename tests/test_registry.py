"""Pattern registry: discovery, hot reload, error isolation (spec §9.3)."""

import numpy as np

from luminary.patterns.registry import PatternRegistry, default_registry

GOOD = """
import numpy as np
from luminary.patterns.base import Pattern

class TestPattern(Pattern):
    name = "{name}"
    description = "test pattern"

    def render(self, lights, t):
        out = np.zeros((lights.shape[0], 3))
        out[:, 0] = {level}
        return out
"""

BROKEN = "import nonexistent_module_xyz\n"


def test_repo_patterns_discovered():
    registry = default_registry()
    names = {entry["name"] for entry in registry.list() if entry["ok"]}
    assert {
        "simple",
        "ripple",
        "spiral",
        "wave",
        "breathe",
        "kaleidoscope",
        "tunnel_vision",
        "firelike",
        "plasma_storm",
        # book-one/ — the look-dev set (2026-07): one axis of the medium each.
        "aurora",
        "emberfall",
        "sanctum",
        "prism",
        "tidepool",
        "vespers",
        # conifer/ — conifer egitto's set.
        "life",
        "pacman",
        "serpent",
        # book-two/ — composed from the shared primitives library.
        "starlight",
        "weather",
        "veils",
        "ringfall",
        "nocturne",
    } <= names
    assert not registry.errors, f"pattern load errors: {registry.errors}"


def test_discovery_is_recursive_with_exclusions(tmp_path):
    (tmp_path / "vol").mkdir()
    (tmp_path / "vol" / "deep").mkdir()
    (tmp_path / "vol" / "a.py").write_text(GOOD.format(name="a", level="0.1"))
    (tmp_path / "vol" / "deep" / "b.py").write_text(GOOD.format(name="b", level="0.2"))
    # Excluded: _-prefixed files and directories (helpers), and legacy/.
    (tmp_path / "vol" / "_helper.py").write_text(GOOD.format(name="h", level="0.3"))
    (tmp_path / "_wip").mkdir()
    (tmp_path / "_wip" / "c.py").write_text(GOOD.format(name="c", level="0.4"))
    (tmp_path / "legacy").mkdir()
    (tmp_path / "legacy" / "old.py").write_text(BROKEN)
    registry = PatternRegistry([tmp_path])
    assert set(registry.patterns) == {"a", "b"}
    assert not registry.errors, f"exclusions leaked: {registry.errors}"
    assert registry.get("b").name == "b"  # stem lookup reaches into subdirs


def test_hot_reload_swaps_implementation(tmp_path):
    file = tmp_path / "mypattern.py"
    file.write_text(GOOD.format(name="mine", level="0.25"))
    registry = PatternRegistry([tmp_path])
    lights = np.zeros((4, 24))
    assert registry.get("mine").render(lights, 0.0)[0, 0] == 0.25

    file.write_text(GOOD.format(name="mine", level="0.75"))
    registry.reload()
    assert registry.get("mine").render(lights, 0.0)[0, 0] == 0.75


def test_broken_file_is_isolated(tmp_path):
    (tmp_path / "good.py").write_text(GOOD.format(name="ok", level="0.5"))
    (tmp_path / "bad.py").write_text(BROKEN)
    registry = PatternRegistry([tmp_path])
    assert "ok" in registry.patterns
    assert any("bad.py" in key for key in registry.errors)
    entries = registry.list()
    assert any(not entry["ok"] for entry in entries)


def test_lookup_by_stem_and_helpful_error(tmp_path):
    (tmp_path / "fancy_file.py").write_text(GOOD.format(name="fancy", level="0.1"))
    registry = PatternRegistry([tmp_path])
    assert registry.get("fancy_file").name == "fancy"
    try:
        registry.get("nope")
    except KeyError as exc:
        assert "fancy" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected KeyError")

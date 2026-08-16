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
        # The look-dev set (2026-07): each explores one axis of the medium.
        "aurora",
        "emberfall",
        "sanctum",
        "prism",
        "tidepool",
        "vespers",
    } <= names
    assert not registry.errors, f"pattern load errors: {registry.errors}"


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

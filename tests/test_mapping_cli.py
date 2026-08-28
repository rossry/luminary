"""The map verb: help, hardware-free construction, resume, web guard.

``build_mapping_session`` exists exactly so these tests can build the
session objects without entering the TUI loop or opening a port.
"""

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from luminary.mapping.state import Event

REPO = Path(__file__).resolve().parents[1]


def _args(tmp_path, **overrides):
    base = dict(
        store=str(tmp_path / "mapping"),
        config="4A-33",
        continue_=False,
        trust_boards=False,
        controllers="1,2,3,4,5,6,7",
        fps=30.0,
        tui=False,
        web=False,  # accepted and ignored; the window is the default now
        no_browser=True,
        host="127.0.0.1",
        port=8090,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def test_map_help_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "luminary.cli", "map", "--help"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    # --tui, not --web: the window is the default now, so the flag that used
    # to select it is accepted but hidden.
    for flag in ("--continue", "--trust-boards", "--controllers", "--tui"):
        assert flag in result.stdout
    assert "4A-33" in result.stdout  # the production-default net


def test_build_mapping_session_without_hardware(tmp_path):
    from luminary.cli import build_mapping_session

    core, store = build_mapping_session(_args(tmp_path))
    assert core.state.stage == "ports"
    assert core.state.controllers == (1, 2, 3, 4, 5, 6, 7)
    assert core.fps == 30.0
    assert core.wire_sinks == []  # --controllers skips probing: no ports
    assert store.directory == tmp_path / "mapping"
    assert store.directory.is_dir()
    # Both engines stand ready: the window always, the wire because the
    # ports stage breathes the candidate board.
    assert core.window_engine is not None
    assert core.wire_engine is not None


def test_build_continue_resumes_from_the_store(tmp_path):
    from luminary.cli import build_mapping_session

    core, store = build_mapping_session(_args(tmp_path))
    for _ in range(3):
        core.apply(Event.ENTER)
    store.save_state(core.state, core.plan)

    resumed, _ = build_mapping_session(_args(tmp_path, continue_=True))
    assert resumed.state.stage == "ports"
    assert resumed.state.board_cursor == 3
    assert resumed.state.boards == core.state.boards


def test_store_dir_is_var_with_no_fallback_logic():
    """Runtime state defaults to var/ — which ships in the repo
    (var/.gitkeep), so the resolver carries no existence or legacy
    logic at all; an explicit --store wins verbatim."""
    from luminary.cli import _store_dir

    assert _store_dir(None) == Path("var")
    assert _store_dir(None, "mapping") == Path("var") / "mapping"
    # An explicit path is the directory itself, sub or no sub.
    assert _store_dir("elsewhere", "mapping") == Path("elsewhere")
    assert (REPO / "var" / ".gitkeep").exists()  # the checkout guarantee


def test_parse_keys_alpha_only_confirms():
    """p and space are enter synonyms: the whole flow works on an
    alpha-only keyboard (arrows already have WASD)."""
    from luminary.mapping.tui import parse_keys

    tokens, rest = parse_keys(b"pP \r\n")
    assert tokens == [Event.ENTER] * 5
    assert rest == b""


def test_mapping_opens_the_window_by_default(tmp_path, monkeypatch):
    """Mapping is spatial. A terminal can say "board 1/6"; it cannot show an
    operator standing at the sphere *which* board that is, so the browser
    window — which draws the net with the board under the cursor lit — is
    what you get unless you ask otherwise."""
    from luminary.cli import cmd_map

    served = {}

    def _fake_serve(core, store, host, port):
        served["host"], served["port"] = host, port

    monkeypatch.setattr("luminary.mapping.web.serve_mapping", _fake_serve)
    monkeypatch.setattr(
        "luminary.mapping.tui.run_tui",
        lambda *a, **k: pytest.fail("ran the terminal surface by default"),
    )

    assert cmd_map(_args(tmp_path)) == 0
    assert served == {"host": "127.0.0.1", "port": 8090}


def test_tui_is_still_reachable(tmp_path, monkeypatch):
    from luminary.cli import cmd_map

    ran = {}
    monkeypatch.setattr(
        "luminary.mapping.tui.run_tui", lambda *a, **k: ran.setdefault("yes", True)
    )
    monkeypatch.setattr(
        "luminary.mapping.web.serve_mapping",
        lambda *a, **k: pytest.fail("served the window despite --tui"),
    )

    assert cmd_map(_args(tmp_path, tui=True)) == 0
    assert ran == {"yes": True}

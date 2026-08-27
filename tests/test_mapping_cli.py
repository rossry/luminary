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
        web=False,
        host="127.0.0.1",
        port=8080,
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
    for flag in ("--continue", "--trust-boards", "--controllers", "--web"):
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


def test_parse_keys_alpha_only_confirms():
    """p and space are enter synonyms: the whole flow works on an
    alpha-only keyboard (arrows already have WASD)."""
    from luminary.mapping.tui import parse_keys

    tokens, rest = parse_keys(b"pP \r\n")
    assert tokens == [Event.ENTER] * 5
    assert rest == b""


def test_web_flag_without_the_web_surface_exits_cleanly(tmp_path, capsys):
    if importlib.util.find_spec("luminary.mapping.web") is not None:
        pytest.skip("web surface present; the guard has nothing to catch")
    from luminary.cli import cmd_map

    assert cmd_map(_args(tmp_path, web=True)) == 2
    assert "web surface not present" in capsys.readouterr().err

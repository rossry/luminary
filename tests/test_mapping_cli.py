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
        state_dir=str(tmp_path / "mapping"),
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

    core, saved = build_mapping_session(_args(tmp_path))
    assert core.state.stage == "ports"
    assert core.state.controllers == (1, 2, 3, 4, 5, 6, 7)
    assert core.fps == 30.0
    assert core.wire_sinks == []  # --controllers skips probing: no ports
    assert saved.directory == tmp_path / "mapping"
    assert saved.directory.is_dir()
    # Both engines stand ready: the window always, the wire because the
    # ports stage breathes the candidate board.
    assert core.window_engine is not None
    assert core.wire_engine is not None


def test_build_continue_resumes_from_saved_records(tmp_path):
    from luminary.cli import build_mapping_session

    core, saved = build_mapping_session(_args(tmp_path))
    for _ in range(3):
        core.apply(Event.ENTER)
    saved.save_state(core.state, core.plan)

    resumed, _ = build_mapping_session(_args(tmp_path, continue_=True))
    assert resumed.state.stage == "ports"
    assert resumed.state.board_cursor == 3
    assert resumed.state.boards == core.state.boards


def test_state_dir_is_the_checkout_var_regardless_of_cwd(tmp_path, monkeypatch):
    """Runtime state defaults to the CHECKOUT's var/ — which ships in
    the repo (var/.gitkeep) — anchored by __file__ like the pattern
    registry, so a service run from any working directory (systemd's
    default is /) still finds the operator's files. No existence or
    legacy logic; an explicit --state-dir wins verbatim."""
    from luminary.cli import _state_dir

    assert _state_dir(None) == REPO / "var"
    assert _state_dir(None, "mapping") == REPO / "var" / "mapping"
    monkeypatch.chdir(tmp_path)  # a wrong CWD must change nothing
    assert _state_dir(None) == REPO / "var"
    # An explicit path is the directory itself, sub or no sub.
    assert _state_dir("elsewhere", "mapping") == Path("elsewhere")
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

    def _fake_serve(core, saved, host, port):
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


def test_the_word_store_never_returns():
    """The dead pre-rename tree cost a festival evening: an old CLI
    flag silently pointed the whole runtime at a phantom directory.
    The bare word is banned from python sources — compounds
    (GeometryStore, MappingStore, argparse's own action names) remain
    legal; the standalone token, a module by that name, or the old
    flag do not."""
    import re

    word = "".join("st or e".split())
    bare = re.compile(r"(?<![A-Za-z_])" + word + r"(?![A-Za-z_])")
    offenders = []
    for path in sorted(REPO.glob("luminary/**/*.py")) + sorted(
        REPO.glob("tests/**/*.py")
    ):
        if path.name == word + ".py":
            offenders.append(f"{path}: module named {word}.py")
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if ("--" + word) in line or bare.search(line):
                offenders.append(f"{path.relative_to(REPO)}:{lineno}: {line.strip()}")
    assert not offenders, "the word came back:\n" + "\n".join(offenders[:20])


def test_tui_loop_saves_records_and_restores_the_terminal(tmp_path, monkeypatch):
    """Drive the real ``run_tui`` body over a pty.

    Every other test in this file patches ``run_tui`` away, so nothing ever
    executed its interior. A rename once bound the records parameter and the
    saved termios attributes to the same local name, which sent the resume
    refresh to ``save_state`` on a list of terminal flags: ``luminary map
    --tui`` died before the operator's first key, and only mypy saw it. This
    runs the loop for one keystroke instead.
    """
    import os
    import pty
    import termios
    import threading

    from luminary.cli import build_mapping_session
    from luminary.mapping.tui import run_tui

    core, records = build_mapping_session(_args(tmp_path))

    saves = []
    monkeypatch.setattr(
        type(records), "save_state", lambda self, state, plan: saves.append(state)
    )

    controller_fd, terminal_fd = pty.openpty()
    before = termios.tcgetattr(terminal_fd)
    done = threading.Event()

    def press_quit():
        # Repeatedly, until the loop takes one: tty.setcbreak flushes pending
        # input (TCSAFLUSH), so anything written before run_tui reaches it is
        # discarded and a single pre-loop write would hang here forever.
        while not done.wait(0.02):
            try:
                os.write(controller_fd, b"q")
            except OSError:
                return

    typist = threading.Thread(target=press_quit, daemon=True)
    typist.start()
    try:
        with os.fdopen(terminal_fd, "rb", buffering=0, closefd=False) as terminal:
            monkeypatch.setattr("sys.stdin", terminal)
            run_tui(core, records, fps=30.0)
        # The resume refresh reached the records, not the terminal flags.
        assert saves and saves[0] == core.state
        assert termios.tcgetattr(terminal_fd) == before  # cbreak undone
    finally:
        done.set()
        typist.join(timeout=1.0)
        os.close(controller_fd)
        os.close(terminal_fd)

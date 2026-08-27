"""The key -> event contract, held to one canon across surfaces.

The web page and the TUI necessarily carry their own key tables (one
maps KeyboardEvent names, the other terminal bytes) — exactly the kind
of per-surface duplication that must not drift. This test is the
golden-vector philosophy applied to key handling: one canonical
contract, every surface asserted against it.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from luminary.mapping import tui
from luminary.mapping.state import Event

REPO = Path(__file__).resolve().parents[1]

# THE contract: KeyboardEvent.key (lowercased) -> control event name.
# Arrows and WASD are equivalent; enter, p, and space all confirm.
CANON = {
    "arrowleft": "left",
    "a": "left",
    "arrowright": "right",
    "d": "right",
    "arrowup": "up",
    "w": "up",
    "arrowdown": "down",
    "s": "down",
    "enter": "enter",
    "p": "enter",
    " ": "enter",
}


def test_tui_matches_the_contract():
    plain = {bytes([k[0]]).decode(): ev for k, ev in tui._PLAIN.items()}
    # CR and LF are both the terminal's Enter key.
    assert plain.pop("\r") is Event.ENTER
    assert plain.pop("\n") is Event.ENTER
    expected = {
        key: Event(name)
        for key, name in CANON.items()
        if not key.startswith("arrow") and key != "enter"
    }
    assert plain == expected
    csi = {
        b"A": Event(CANON["arrowup"]),
        b"B": Event(CANON["arrowdown"]),
        b"C": Event(CANON["arrowright"]),
        b"D": Event(CANON["arrowleft"]),
    }
    assert dict(tui._CSI) == csi


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_web_matches_the_contract():
    result = subprocess.run(
        ["node", str(REPO / "tests" / "js" / "print_mapping_keys.mjs")],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == CANON

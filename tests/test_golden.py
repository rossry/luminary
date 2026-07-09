"""Golden vector conformance (spec §11.9).

1. The checked-in vectors regenerate byte-identically (encoder is stable).
2. The JS decoder replays them bit-exactly (when node is available).
3. The C++ decoder replays them bit-exactly (when g++ is available).
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GOLDEN = REPO / "firmware" / "golden" / "case1"


def test_golden_vectors_regenerate_identically(tmp_path, monkeypatch):
    for name in ("stream.bin", "expected.bin", "expected_rgb.bin"):
        assert (GOLDEN / name).exists(), "run scripts/generate_golden.py"
    checked_in = {
        name: (GOLDEN / name).read_bytes()
        for name in ("stream.bin", "expected.bin", "expected_rgb.bin")
    }

    result = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "generate_golden.py")],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert result.returncode == 0, result.stderr
    for name, data in checked_in.items():
        assert (GOLDEN / name).read_bytes() == data, f"{name} is not reproducible"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_js_decoder_conformance():
    result = subprocess.run(
        ["node", str(REPO / "tests" / "js" / "test_decoder.mjs")],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "bit-exact" in result.stdout


@pytest.mark.skipif(shutil.which("g++") is None, reason="g++ not available")
def test_cpp_decoder_conformance(tmp_path):
    host_dir = REPO / "firmware" / "test" / "host"
    build = subprocess.run(
        ["make", "-B", "test_decoder"], capture_output=True, text=True, cwd=host_dir
    )
    assert build.returncode == 0, build.stdout + build.stderr
    result = subprocess.run(
        [str(host_dir / "test_decoder"), str(GOLDEN)],
        capture_output=True,
        text=True,
        cwd=host_dir,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "bit-exact" in result.stdout

"""Presentation timing, and the three implementations that must agree.

The boards, the web viewer and the local preview are fed the identical wire
stream. If they disagree about *when* a frame is shown, the boards drift apart
from each other and the preview stops being evidence of what the installation
is doing — so the clock is held to one canon the same way the three wire
decoders are, by replaying a golden vector through all of them.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from luminary.comms.presentation import PlayoutQueue, PresentationClock

REPO = Path(__file__).resolve().parents[1]
VECTOR = REPO / "firmware" / "golden" / "presentation" / "case1.json"


@pytest.fixture(scope="module")
def vector():
    return json.loads(VECTOR.read_text())


def test_the_reference_reproduces_its_own_vector(vector):
    clock = PresentationClock()
    for (t, arrival), want in zip(vector["observations"], vector["expected"]):
        clock.observe(t, arrival)
        usable = clock.usable_delay(vector["delay_us"], vector["slots"])
        assert [
            clock.skew_us,
            clock.interval_us,
            usable,
            clock.deadline(t, usable),
        ] == want


def test_the_offset_converges_within_a_few_frames():
    """Acquisition speed is the whole startup story.

    A flat 64-observation window put the first correction 2.1 s into a 30 fps
    show, and until then every frame ran on whatever queuing delay the first
    frame happened to carry — about 100 frames shown past their deadline at
    startup, and none at all once settled.
    """
    fps = 30.0
    queuing = [4300, 900, 120, 0, 40, 1500, 70, 2600]
    clock = PresentationClock()
    corrected_at = None
    for i in range(64):
        t = i / fps
        clock.observe(t, 1_000_000 + int(t * 1e6) + 1200 + queuing[i % 8])
        if corrected_at is None and clock.skew_us:
            corrected_at = i

    assert corrected_at is not None, "never corrected"
    assert corrected_at <= 8, f"first correction took {corrected_at} frames"
    assert -4500 < clock.skew_us < -4100, "converged on the wrong offset"


def test_the_offset_is_the_floor_not_the_mean():
    """Arrival delay is the true offset plus non-negative queuing.

    A mean would bake each surface's own average queuing into its estimate,
    and the surfaces would sit at different offsets forever.
    """
    fps = 60.0
    queuing = [4300, 900, 120, 0, 40, 1500, 70, 2600]
    clock = PresentationClock()
    for i in range(200):
        t = i / fps
        clock.observe(t, 1_000_000 + int(t * 1e6) + 1200 + queuing[i % 8])

    # The base was captured from a frame that was itself 4300 us late, so the
    # filter's job is to walk that back.
    assert -4500 < clock.skew_us < -4100
    assert abs(clock.interval_us - 16666) < 200


def test_two_surfaces_differ_only_by_their_link_latency():
    """The property the whole mechanism exists for."""
    fps = 60.0
    a_queue = [4300, 900, 120, 0, 40, 1500, 70, 2600]
    b_queue = [0, 2600, 70, 1500, 40, 4300, 120, 900]
    a, b = PresentationClock(), PresentationClock()
    base_a, base_b, lat_a, lat_b = 500_000, 99_000_000, 1200, 7800
    for i in range(200):
        t = i / fps
        a.observe(t, base_a + int(t * 1e6) + lat_a + a_queue[i % 8])
        b.observe(t, base_b + int(t * 1e6) + lat_b + b_queue[i % 8])

    show_t, delay = 200 / fps, 50_000
    spread = abs(
        (a.deadline(show_t, delay) - base_a) - (b.deadline(show_t, delay) - base_b)
    )
    assert abs(spread - (lat_b - lat_a)) < 200


def test_delay_is_capped_to_what_the_queue_holds():
    """Staging is eager, so a full queue holds slots-1 frames ahead."""
    clock = PresentationClock()
    for i in range(40):
        clock.observe(i / 60.0, 1_000_000 + int(i / 60.0 * 1e6))

    assert clock.usable_delay(1000, 1) == 1000  # inside a frame: untouched
    assert clock.usable_delay(500_000, 1) <= clock.interval_us
    assert clock.usable_delay(500_000, 4) == clock.interval_us * 3


def test_a_fresh_clock_claims_nothing():
    assert not PresentationClock().have


# ------------------------------------------------------------------- queue


def test_the_queue_holds_frames_until_their_deadline():
    queue = PlayoutQueue(depth=3)

    assert queue.push("a", 1000) and queue.push("b", 2000) and queue.push("c", 3000)
    assert not queue.push("d", 4000), "accepted a frame past its depth"
    assert queue.due(999) is None, "released a frame before its deadline"
    assert queue.due(1000) == "a"
    assert queue.due(2500) == "b"
    assert queue.due(2500) is None, "released a frame early"
    assert len(queue) == 1


# ------------------------------------------------------- cross-implementation


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_browser_clock_matches_the_reference():
    result = subprocess.run(
        ["node", str(REPO / "tests" / "js" / "test_presentation.mjs")],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert result.returncode == 0, result.stdout + result.stderr

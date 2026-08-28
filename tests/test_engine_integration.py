"""Engine integration (spec §10, §17.2.3): the full pipeline within
quantization tolerance, statelessness, hot-swap keyframes, and the
performance budget (spec §17.3)."""

import time

import numpy as np
import pytest

from luminary.comms import protocol as p
from luminary.comms.codec import CodecConfig, Decoder
from luminary.engine.engine import Engine
from luminary.geometry.capture import CaptureParams, capture
from luminary.geometry.scaffold import Scaffold
from luminary.patterns.registry import default_registry

SCAFFOLD = {
    "schema": "luminary.scaffold/1",
    "space": {"authoritative": ["xy"]},
    "lines": [
        {"p1": [0, 0], "p2": [200, 0]},
        {"p1": [200, 0], "p2": [200, 200]},
        {"p1": [200, 200], "p2": [0, 200]},
        {"p1": [0, 200], "p2": [0, 0]},
        {"p1": [0, 0], "p2": [200, 200]},
        {"p1": [200, 0], "p2": [0, 200]},
    ],
    "meta": {"name": "engine-test"},
}


@pytest.fixture(scope="module")
def lights():
    return capture(
        Scaffold.load(SCAFFOLD), CaptureParams(count_per_line=32, interpolate_every=4)
    )


@pytest.fixture(scope="module")
def registry():
    return default_registry()


def test_decoded_matches_pattern_within_quantization(lights, registry):
    engine = Engine(lights, registry.get("spiral"), codec_config=CodecConfig())
    decoder = Decoder()
    for frame in engine.session_frames():
        decoder.decode(frame)
    for i in range(45):
        t = i / 30.0
        for frame in engine.frame(t):
            decoder.decode(frame)
        truth = p.quantize(engine.colors_oklch(t)[lights.control_mask])
        got = decoder.active_q(0)
        # Uncapped budget: within one quantization step everywhere, exact
        # almost everywhere (keyframe rounding residue heals in the same
        # tick, spec §11.7.3a; only delta-range saturation can lag).
        assert np.max(np.abs(got[:, 0] - truth[:, 0])) <= 1
        assert np.max(np.abs(got[:, 1] - truth[:, 1])) <= 1
        hue_err = np.abs(((got[:, 2] - truth[:, 2] + 128) % 256) - 128)
        assert np.max(hue_err) <= 1


def test_statelessness_all_patterns(lights, registry):
    """Every shipped pattern: same (lights, t) -> identical output (§9.1.3)."""
    for entry in registry.list():
        if not entry["ok"]:
            continue
        pattern = registry.get(entry["name"])
        a = pattern.render(lights.array, 12.34)
        _ = pattern.render(lights.array, 99.9)  # interleaved call
        b = pattern.render(lights.array, 12.34)
        np.testing.assert_array_equal(a, b, err_msg=f"{entry['name']} is stateful")
        assert a.shape == (lights.n, 3)
        assert np.all(np.isfinite(a)), f"{entry['name']} produced non-finite output"


def test_pattern_hot_swap_forces_keyframe(lights, registry):
    engine = Engine(lights, registry.get("simple"))
    decoder = Decoder()
    for frame in engine.session_frames():
        decoder.decode(frame)
    engine.frame(0.0)
    engine.frame(1 / 30)
    engine.set_pattern(registry.get("wave"))
    frames = engine.frame(2 / 30)
    frame_type, _, _, _ = p.parse_frame(p.cobs_decode(frames[0].rstrip(b"\x00")))
    assert frame_type == p.FRAME_KEYFRAME


def test_engine_rejects_wrong_shape(lights, registry):
    engine = Engine(lights, registry.get("simple"))
    with pytest.raises(ValueError, match="rows"):
        engine.encoder.encode(np.zeros((3, 3)), 0.0)


def test_performance_budget_render_encode(registry):
    """Spec §17.3.1: pattern eval + encode for 8x256 ACTIVE lights well under
    the 33ms frame budget (target <= 5ms on a Pi-class machine; assert a
    generous CI-safe bound and print the measurement)."""
    from luminary.geometry.lights import LightsGeometry, LightSpec, SpaceSpec

    specs = [
        LightSpec(
            controller=0,
            channel=ch,
            index=i,
            kind="active",
            pos=[float(i), float(ch * 40)],
        )
        for ch in range(8)
        for i in range(256)
    ]
    lights = LightsGeometry.from_specs(specs, SpaceSpec())
    engine = Engine(
        lights,
        registry.get("kaleidoscope"),
        codec_config=CodecConfig(budget_bytes=1200),
    )
    engine.frame(0.0)  # warm up (keyframe + numpy caches)
    n = 60
    start = time.perf_counter()
    for i in range(1, n + 1):
        engine.frame(i / 30.0)
    per_frame_ms = (time.perf_counter() - start) / n * 1000
    print(f"\nrender+encode 2048 lights: {per_frame_ms:.2f} ms/frame")
    assert per_frame_ms < 25.0, "render+encode blew the frame budget"

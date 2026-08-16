"""Wire protocol and codec (spec §11): framing, quantization, predictor,
encoder/decoder lockstep, budgets, eventual correctness, corruption."""

import numpy as np
import pytest

from luminary.comms import predictor
from luminary.comms import protocol as p
from luminary.comms.codec import CodecConfig, Decoder, Encoder
from luminary.geometry.lights import LightsGeometry, LightSpec, SpaceSpec


def make_lights(n_active=24, n_interp_every=None, channels=2):
    specs = []
    per_channel = n_active // channels
    for ch in range(channels):
        for i in range(per_channel):
            kind = "active"
            if n_interp_every and i % n_interp_every:
                kind = "interpolated"
            specs.append(
                LightSpec(
                    controller=0,
                    channel=ch,
                    index=i,
                    kind=kind,
                    pos=[float(i * 10), float(ch * 25)],
                )
            )
        if n_interp_every:
            specs[-1].kind = "active"
    return LightsGeometry.from_specs(specs, SpaceSpec())


def smooth_oklch(lights, t):
    idx = np.arange(lights.n)
    return np.stack(
        [
            0.5 + 0.4 * np.sin(t + idx * 0.3),
            0.2 + 0.15 * np.cos(t * 0.7 + idx),
            (idx * 29.0 + t * 80.0) % 360.0,
        ],
        axis=1,
    )


# ------------------------------------------------------------------ framing


def test_cobs_roundtrip():
    cases = [b"", b"\x00", b"\x00\x00", b"abc", b"a\x00b", bytes(range(256)) * 3]
    for data in cases:
        encoded = p.cobs_encode(data)
        assert 0 not in encoded
        assert p.cobs_decode(encoded) == data


def test_frame_roundtrip_and_crc():
    frame = p.build_frame(p.FRAME_DELTA, 3, 1.25, b"payload")
    assert frame.endswith(b"\x00")
    body = p.cobs_decode(frame[:-1])
    frame_type, controller, t, payload = p.parse_frame(body)
    assert (frame_type, controller, t, payload) == (p.FRAME_DELTA, 3, 1.25, b"payload")

    corrupted = bytearray(body)
    corrupted[HEADER_TAMPER] ^= 0xFF
    with pytest.raises(p.ProtocolError):
        p.parse_frame(bytes(corrupted))


HEADER_TAMPER = 5


def test_splitter_reassembles_across_chunks():
    frames = [
        p.build_frame(p.FRAME_DELTA, 0, float(i), bytes([i] * i)) for i in range(1, 6)
    ]
    stream = b"".join(frames)
    splitter = p.FrameSplitter()
    out = []
    for i in range(0, len(stream), 3):
        out.extend(splitter.feed(stream[i : i + 3]))
    assert len(out) == 5
    assert p.parse_frame(out[2])[3] == bytes([3, 3, 3])


# -------------------------------------------------------------- quantization


def test_quantize_ranges_and_roundtrip_error():
    rng = np.random.default_rng(7)
    oklch = np.stack(
        [rng.random(1000), rng.random(1000) * 0.4, rng.random(1000) * 360], axis=1
    )
    q = p.quantize(oklch)
    assert q[:, 0].min() >= 0 and q[:, 0].max() <= 63
    assert q[:, 1].min() >= 0 and q[:, 1].max() <= 31
    assert q[:, 2].min() >= 0 and q[:, 2].max() <= 255
    back = p.dequantize(q)
    assert np.max(np.abs(back[:, 0] - oklch[:, 0])) <= 0.5 / 63 + 1e-9
    assert np.max(np.abs(back[:, 1] - oklch[:, 1])) <= 0.5 / 31 * 0.4 + 1e-9


def test_keyframe_words_top_bits():
    q = np.array([[63, 31, 255], [0, 0, 0], [33, 17, 129]], dtype=np.int32)
    decoded = p.unpack_keyframe_words(p.pack_keyframe_words(q))
    # Within 1 LSB everywhere (bottom bit lost, spec §11.4.2); hue wraps.
    assert np.all(np.abs(decoded[:, 0] - q[:, 0]) <= 1 + (q[:, 0] == 63))
    err_h = np.abs(predictor.hue_wrap_diff(decoded[:, 2], q[:, 2]))
    assert np.all(err_h <= 1)


def test_delta_words_sign_magnitude():
    corr = np.array(
        [[15, -7, 63], [-15, 7, -63], [0, 0, 0], [1, -1, 1]], dtype=np.int32
    )
    back = p.unpack_delta_words(p.pack_delta_words(corr))
    np.testing.assert_array_equal(back, corr)
    with pytest.raises(p.ProtocolError, match="exceeds field range"):
        p.pack_delta_words(np.array([[16, 0, 0]], dtype=np.int32))


def test_delta_payload_skip_encoding():
    positions = np.array([0, 1, 5, 200], dtype=np.int64)
    words = np.array([1, 2, 3, 4], dtype=np.uint16)
    parsed_pos, parsed_words = p.parse_delta_payload(
        p.build_delta_payload(positions, words)
    )
    np.testing.assert_array_equal(parsed_pos, positions)
    np.testing.assert_array_equal(parsed_words, words)


# ---------------------------------------------------------------- predictor


def test_predictor_coasts_velocity():
    q = np.array([[30, 15, 100]], dtype=np.int32)
    v = np.zeros((1, 3), dtype=np.int32)
    # Apply +2 L corrections for a few frames; velocity should build up and
    # then prediction alone should keep moving without corrections.
    for _ in range(6):
        pred, err, corr = predictor.error_to_target(q, v, q + [[2, 0, 0]])
        q, v = predictor.apply_delta(q, v, np.array([0]), corr[[0]])
    q_before = q[0, 0]
    q, v = predictor.apply_delta(q, v, None, None)  # pure dead reckoning
    assert q[0, 0] > q_before  # kept moving on velocity alone


def test_hue_wrap_shortest_path():
    a = np.array([250], dtype=np.int32)
    b = np.array([5], dtype=np.int32)
    assert predictor.hue_wrap_diff(b, a)[0] == 11  # wraps forward, not -245


# ----------------------------------------------------------------- lockstep


def test_encoder_decoder_lockstep_uncapped():
    lights = make_lights()
    encoder = Encoder(lights, CodecConfig(keyframe_interval=15))
    decoder = Decoder()
    for frame in encoder.session_frames():
        decoder.decode(frame)
    for i in range(60):
        for frame in encoder.encode(smooth_oklch(lights, i / 30), i / 30):
            decoder.decode(frame)
        np.testing.assert_array_equal(decoder.active_q(0), encoder.states[0].q)


def test_lockstep_under_tight_budget_random_walk():
    lights = make_lights()
    encoder = Encoder(lights, CodecConfig(keyframe_interval=25, budget_bytes=40))
    decoder = Decoder()
    for frame in encoder.session_frames():
        decoder.decode(frame)
    rng = np.random.default_rng(11)
    oklch = smooth_oklch(lights, 0)
    for i in range(150):
        oklch = oklch + rng.normal(scale=[0.05, 0.02, 8.0], size=oklch.shape)
        oklch[:, 0] = np.clip(oklch[:, 0], 0, 1)
        oklch[:, 1] = np.clip(oklch[:, 1], 0, 0.4)
        frames = encoder.encode(oklch, i / 30)
        for frame in frames:
            body = p.cobs_decode(frame.rstrip(b"\x00"))
            frame_type = body[1]
            if frame_type == p.FRAME_DELTA:
                # The budget caps DELTA frames; keyframes are exempt and
                # amortized by the interval (CodecConfig docstring).
                assert len(frame) <= 40 + 8  # + COBS/delimiter overhead
            decoder.decode(frame)
        np.testing.assert_array_equal(decoder.active_q(0), encoder.states[0].q)


def test_eventual_correctness_static_target():
    """A frozen target converges to exact quantized ground truth (§11.1.2)."""
    lights = make_lights()
    encoder = Encoder(lights, CodecConfig(keyframe_interval=10**9))
    decoder = Decoder()
    for frame in encoder.session_frames():
        decoder.decode(frame)
    target = smooth_oklch(lights, 3.7)
    for i in range(10):
        for frame in encoder.encode(target, i / 30.0):
            decoder.decode(frame)
    expected = p.quantize(target[lights.control_mask])
    np.testing.assert_array_equal(decoder.active_q(0), expected)


def test_keyframe_resets_late_joiner():
    """A decoder joining mid-stream syncs at the first keyframe (§11.7.3)."""
    lights = make_lights()
    encoder = Encoder(lights, CodecConfig(keyframe_interval=10**9))
    early = Decoder()
    for frame in encoder.session_frames():
        early.decode(frame)
    for i in range(20):
        for frame in encoder.encode(smooth_oklch(lights, i / 30), i / 30):
            early.decode(frame)

    late = Decoder()
    for frame in encoder.session_frames():
        late.decode(frame)
    encoder.force_keyframe()
    for i in range(20, 24):
        for frame in encoder.encode(smooth_oklch(lights, i / 30), i / 30):
            early.decode(frame)
            late.decode(frame)
    np.testing.assert_array_equal(late.active_q(0), early.active_q(0))


def test_corrupt_stream_flags_resync_then_recovers():
    lights = make_lights()
    encoder = Encoder(lights, CodecConfig())
    decoder = Decoder()
    for frame in encoder.session_frames():
        decoder.feed(frame)
    frames = encoder.encode(smooth_oklch(lights, 0.0), 0.0)
    corrupted = bytearray(frames[0])
    corrupted[len(corrupted) // 2] ^= 0x55
    if corrupted[len(corrupted) // 2] == 0:
        corrupted[len(corrupted) // 2] = 1
    decoder.feed(bytes(corrupted))
    assert decoder.want_resync
    # Server responds with a keyframe; decoder recovers.
    encoder.force_keyframe()
    for frame in encoder.encode(smooth_oklch(lights, 0.1), 0.1):
        decoder.feed(frame)
    np.testing.assert_array_equal(decoder.active_q(0), encoder.states[0].q)


def test_strip_oklch_interpolation():
    lights = make_lights(n_active=8, n_interp_every=2, channels=1)
    encoder = Encoder(lights, CodecConfig())
    decoder = Decoder()
    for frame in encoder.session_frames():
        decoder.decode(frame)
    oklch = np.tile([0.5, 0.2, 100.0], (lights.n, 1))
    for frame in encoder.encode(oklch, 0.0):
        decoder.decode(frame)
    strip = decoder.strip_oklch(0, 0)
    active_mask = lights.control_mask
    # Uniform color: interpolated positions land on the same color.
    np.testing.assert_allclose(strip[:, 0], strip[0, 0], atol=1e-9)
    assert strip.shape[0] == int(lights.ints(2).max()) + 1
    assert np.sum(~active_mask) > 0  # the case actually exercised interp

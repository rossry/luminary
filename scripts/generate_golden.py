#!/usr/bin/env python3
"""Generate the codec conformance golden vectors (spec §11.9).

Writes, per case directory:
  stream.bin       — SESSION + N wire frames, exactly as on the wire
  expected.bin     — after each non-SESSION frame: u16 n_active, then
                     n_active x (qL u8, qC u8, qH u8): the decoded state
  expected_rgb.bin — final full-strip RGB from the Python float reference:
                     per channel: u8 id, u16 len, len x 3 bytes
  meta.json        — counts for the harnesses

Deterministic: same code -> same bytes. tests/test_golden.py regenerates and
compares; the C++ and JS decoders replay stream.bin and assert expected.*.
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from luminary.color import convert  # noqa: E402
from luminary.comms.codec import CodecConfig, Decoder, Encoder  # noqa: E402
from luminary.geometry.lights import (  # noqa: E402
    LightsGeometry,
    LightSpec,
    SpaceSpec,
)

N_FRAMES = 48
FPS = 30.0


def build_lights() -> LightsGeometry:
    """Two channels, mixed kinds, an index gap — exercises the session map."""
    specs = []
    # Channel 0: 8 lights, every 3rd active (0,3,6 active + last forced).
    for i in range(8):
        kind = "active" if i % 3 == 0 or i == 7 else "interpolated"
        specs.append(
            LightSpec(
                controller=0, channel=0, index=i, kind=kind, pos=[float(i * 10), 0.0]
            )
        )
    # Channel 2 (gap: no channel 1): actives with one inactive hole at 2.
    for i in range(6):
        kind = "inactive" if i == 2 else "active"
        specs.append(
            LightSpec(
                controller=0, channel=2, index=i, kind=kind, pos=[float(i * 10), 40.0]
            )
        )
    return LightsGeometry.from_specs(
        specs, SpaceSpec(authoritative=["xy"]), source={"type": "golden"}, meta={}
    )


def trajectory(lights: LightsGeometry, t: float) -> np.ndarray:
    """Smooth deterministic OKLCH trajectories (stands in for a pattern)."""
    n = lights.n
    idx = np.arange(n)
    oklch = np.empty((n, 3))
    oklch[:, 0] = 0.5 + 0.45 * np.sin(0.9 * t + idx * 0.7)
    oklch[:, 1] = 0.2 + 0.19 * np.cos(0.6 * t + idx * 1.3)
    oklch[:, 2] = (idx * 47.0 + t * 130.0) % 360.0
    return oklch


def main() -> None:
    out_dir = REPO / "firmware" / "golden" / "case1"
    out_dir.mkdir(parents=True, exist_ok=True)

    lights = build_lights()
    # Small budget forces delta selection; interval forces a mid-run keyframe.
    encoder = Encoder(lights, CodecConfig(keyframe_interval=20, budget_bytes=48))
    decoder = Decoder()

    stream = bytearray()
    expected = bytearray()

    for frame in encoder.session_frames(0.0):
        stream.extend(frame)
        decoder.decode(frame)

    n_wire_frames = 0
    for i in range(N_FRAMES):
        t = i / FPS
        # One expected block per wire frame: keyframe ticks emit KEYFRAME +
        # the same-tick healing DELTA (spec §11.7.3a), and the goldens pin
        # the decoded state after each, mid-tick state included.
        for frame in encoder.encode(trajectory(lights, t), t):
            stream.extend(frame)
            decoder.decode(frame)
            q = decoder.active_q(0)
            expected.extend(struct.pack("<H", q.shape[0]))
            expected.extend(q.astype(np.uint8).tobytes())
            n_wire_frames += 1
        assert np.array_equal(
            decoder.active_q(0), encoder.states[0].q
        ), "encoder/decoder diverged"

    rgb = bytearray()
    for channel in sorted(decoder.controllers[0].channels):
        strip_oklch = decoder.strip_oklch(0, channel)
        # Firmware clamps out-of-gamut channels rather than chroma-clipping
        # (spec §13.4), so the reference here uses clip=False.
        oklab = convert.oklch_to_oklab(strip_oklch)
        strip_rgb = convert.linear_to_srgb8(convert.oklab_to_linear_srgb(oklab))
        rgb.append(channel)
        rgb.extend(struct.pack("<H", strip_rgb.shape[0]))
        rgb.extend(strip_rgb.tobytes())

    (out_dir / "stream.bin").write_bytes(bytes(stream))
    (out_dir / "expected.bin").write_bytes(bytes(expected))
    (out_dir / "expected_rgb.bin").write_bytes(bytes(rgb))
    (out_dir / "meta.json").write_text(
        json.dumps(
            {
                "n_frames": n_wire_frames,
                "n_active": int(lights.control_mask.sum()),
                "controller": 0,
                "channels": sorted(int(c) for c in decoder.controllers[0].channels),
            },
            indent=2,
        )
    )
    print(f"Golden vectors written to {out_dir}")
    print(
        f"  stream: {len(stream)} bytes over {N_FRAMES} ticks "
        f"({n_wire_frames} wire frames) + session"
    )


if __name__ == "__main__":
    main()

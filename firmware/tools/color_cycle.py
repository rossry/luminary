"""Solid-color cycle for verifying strip color order by eye.

Loops RED (2s) -> GREEN (2s) -> BLUE (2s) on all 8 outputs, forever. The
colors are named by what the FIRMWARE intends; whatever the strip actually
shows tells you the byte-order permutation:

  see R,G,B  -> order correct
  see G,R,B  -> strip wants RGB, firmware is sending GRB (classic swap)
  see G,B,R  -> strip is BGR
  (any other permutation similarly pins the mapping)

OKLCH cannot express a perfectly pure sRGB primary, so each phase is only
dominantly one channel -- but dominance is all a permutation test needs.

    python firmware/tools/color_cycle.py --port COM8
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import serial

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).parent))

from luminary.comms.codec import CodecConfig, Encoder  # noqa: E402
from bench import synth  # noqa: E402

# OKLCH of the sRGB primaries (L 0..1, C, H degrees).
PHASES = [
    ("RED", (0.628, 0.258, 29.2)),
    ("GREEN", (0.866, 0.295, 142.5)),
    ("BLUE", (0.452, 0.313, 264.1)),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM8")
    ap.add_argument("--phase-seconds", type=float, default=2.0)
    ap.add_argument(
        "--brightness",
        type=float,
        default=0.2,
        help="0..1; ~linear in strip current draw",
    )
    args = ap.parse_args()

    lights = synth(8, 360)
    config = CodecConfig()
    config.brightness = max(1, min(255, round(255 * args.brightness)))
    encoder = Encoder(lights, config)
    conn = serial.Serial(args.port, baudrate=2_000_000, timeout=0, write_timeout=2.0)
    try:
        time.sleep(0.3)
        conn.write(b"\x00" * 4)
        time.sleep(0.2)
        for frame in encoder.session_frames():
            conn.write(frame)
        t = 0.0
        while True:
            for name, (l, c, h) in PHASES:
                oklch = np.tile(np.array([l, c, h]), (lights.n, 1))
                # Force a keyframe per phase so every light snaps at once.
                for state in encoder.states.values():
                    state.need_keyframe = True
                for frame in encoder.encode(oklch, t):
                    conn.write(frame)
                print(f"showing {name}", flush=True)
                t += args.phase_seconds
                deadline = time.monotonic() + args.phase_seconds
                while time.monotonic() < deadline:
                    conn.read(4096)  # drain ACKs
                    time.sleep(0.05)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

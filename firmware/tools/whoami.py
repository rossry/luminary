"""Identify which controller id a connected board was flashed with.

Two boards enumerate identically (same VID:PID), so port -> controller
mapping cannot come from enumeration. The wire protocol answers it instead:
a deliberately corrupt frame provokes a RESYNC, and RESYNC carries the
board's compiled-in controller id in its header. Works in any board state --
unlike HELLO, which stops after the first frame is consumed.

    python firmware/tools/whoami.py            # probe every candidate port
    python firmware/tools/whoami.py --port COM8
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import serial
from serial.tools import list_ports

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from luminary.comms import protocol as p  # noqa: E402

APP_VIDPID = (0x239A, 0x8121)


def probe(port: str, timeout: float = 1.5):
    """Return (controller_id, how) or (None, reason)."""
    try:
        conn = serial.Serial(port, baudrate=2_000_000, timeout=0, write_timeout=1.0)
    except (serial.SerialException, OSError) as exc:
        return None, f"cannot open: {exc}"
    try:
        time.sleep(0.2)
        conn.reset_input_buffer()
        splitter = p.FrameSplitter()
        # A COBS chunk that decodes but fails CRC: one byte of junk. The
        # board answers RESYNC, whose header names its controller.
        conn.write(b"\x01\x00")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data = conn.read(4096)
            for raw in splitter.feed(data):
                try:
                    frame_type, controller, _, _ = p.parse_frame(raw)
                except p.ProtocolError:
                    continue
                if frame_type == p.FRAME_RESYNC:
                    return controller, "RESYNC"
                if frame_type == p.FRAME_HELLO:
                    return controller, "HELLO"
            if not data:
                time.sleep(0.02)
        return None, "no response"
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=None)
    args = ap.parse_args()
    if args.port:
        candidates = [args.port]
    else:
        candidates = [
            i.device for i in list_ports.comports() if (i.vid, i.pid) == APP_VIDPID
        ]
        if not candidates:
            print("no boards enumerated")
            return 1
    for port in candidates:
        controller, how = probe(port)
        if controller is None:
            print(f"{port}: {how}")
        else:
            print(f"{port}: controller {controller}  (via {how})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

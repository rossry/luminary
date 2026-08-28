"""Identify which controller id a connected board was flashed with.

Two boards enumerate identically (same VID:PID), so port -> controller
mapping cannot come from enumeration. The wire protocol answers it instead:
a deliberately corrupt frame provokes a RESYNC, and RESYNC carries the
board's compiled-in controller id in its header. Works in any board state --
unlike HELLO, which stops after the first frame is consumed.

The probe itself lives in ``luminary.boards.discovery`` and is shared with
``luminary boards`` and the mapping tool, so all three agree on what counts
as a board. ``luminary boards`` is the fuller command -- it registers what it
finds and reports BOOTSEL and duplicate ids; this stays as the minimal
one-port check for firmware work.

    python firmware/tools/whoami.py            # probe every candidate port
    python firmware/tools/whoami.py --port /dev/ttyACM0
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from serial.tools import list_ports

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from luminary.boards import discovery  # noqa: E402

APP_VIDPID = discovery.APP_VIDPID


def probe(port: str, timeout: float = 1.5):
    """Return (controller_id, how) or (None, reason)."""
    return discovery.probe_port(port, timeout)


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

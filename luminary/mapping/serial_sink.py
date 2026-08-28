"""Hardware adapter for the mapping tool: which board is on which port,
and frame routing to it.

The identity probe lives in ``luminary.boards.discovery`` and is shared
with ``firmware/tools/whoami.py`` and ``luminary boards``: every board
enumerates with the same VID:PID, so port -> controller cannot come from
enumeration. A deliberately corrupt frame provokes RESYNC, whose header
carries the compiled-in controller id — which is why mappings are keyed
on controller id, never port paths (plan/mapping/DESCRIPTION.md). One
copy of that rule, because a mapping surface that disagreed with
``luminary boards`` about which board is which would be a
production-divergence bug (CLAUDE.md, "one logic path across modes").

Everything degrades to "no hardware": pyserial absent, no matching
ports, or no answers just means the tool runs window-only.

The sink is deliberately smaller than ``drivers/serial_driver.py``:
mapping streams are tiny (one board breathing, one panel under test),
so the ACK window, budget adaptation, and reconnection machinery would
be noise here. A port that faults is dropped for the session — the
operator is standing right there.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Dict, List, Optional

from luminary.boards import discovery
from luminary.comms import protocol as p

if TYPE_CHECKING:
    import serial

# Application-mode USB identity of a flashed Scorpio (whoami.py).
APP_VIDPID = (0x239A, 0x8121)
BAUD = 2_000_000


def probe_controllers(timeout: float = 1.5) -> Dict[int, str]:
    """controller id -> port device, for every board that answers.

    Pyserial absent, no candidate ports, or no answers -> {}. Collisions
    (two boards flashed with the same id) resolve first-wins here; the
    mapping session makes them visible, and ``luminary boards`` reports
    them outright.
    """
    return discovery.probe_controllers(timeout)


def _probe_port(device: str, timeout: float) -> Optional[int]:
    """Provoke a RESYNC on one port; -> its controller id, or None."""
    controller, _ = discovery.probe_port(device, timeout)
    return controller


class SerialSink:
    """Wire-frame sink: routes each framed byte string to its
    controller's port by the header controller byte.

    Registered on ``SessionCore.wire_sinks``; the TUI also feeds it the
    fresh SESSION frames after every rebuild. Frames are already framed
    wire bytes, so routing needs only the O(1) header decode. A port
    that fails to open — or faults later — is dropped and the rest keep
    streaming; frames for unreachable controllers are discarded (the
    ports-stage hypothesis can name any probed board).
    """

    def __init__(self, ports: Dict[int, str], baud: int = BAUD) -> None:
        import serial

        self.connections: Dict[int, "serial.Serial"] = {}
        for controller, device in ports.items():
            try:
                self.connections[controller] = serial.Serial(
                    device, baudrate=baud, timeout=0, write_timeout=1.0
                )
            except (OSError, ValueError):
                continue  # window-only for this board

    def __call__(self, frames: List[bytes]) -> None:
        for frame in frames:
            try:
                controller = p.cobs_decode_header(frame.rstrip(b"\x00"))[2]
            except p.ProtocolError:
                continue
            connection = self.connections.get(controller)
            if connection is None:
                continue
            try:
                connection.write(frame)
            except OSError:  # SerialException included; write timeout too
                try:
                    connection.close()
                except OSError:
                    pass
                del self.connections[controller]

    def close(self) -> None:
        for connection in self.connections.values():
            try:
                connection.close()
            except OSError:
                pass
        self.connections.clear()

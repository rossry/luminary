"""Hardware adapter for the mapping tool: which board is on which port,
and frame routing to it.

The identity probe reimplements ``firmware/tools/whoami.py`` inside the
package (the tools script is not importable): every board enumerates
with the same VID:PID, so port -> controller cannot come from
enumeration. A deliberately corrupt frame provokes RESYNC, whose header
carries the compiled-in controller id — which is why mappings are keyed
on controller id, never port paths (plan/mapping/DESCRIPTION.md).

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

from luminary.comms import protocol as p

if TYPE_CHECKING:
    import serial

# Application-mode USB identity of a flashed Scorpio (whoami.py).
APP_VIDPID = (0x239A, 0x8121)
BAUD = 2_000_000


def probe_controllers(timeout: float = 1.5) -> Dict[int, str]:
    """controller id -> port device, for every board that answers.

    Pyserial absent, no candidate ports, or no answers -> {}. When two
    ports answer with the same id (misflashed boards) the first wins;
    the mapping session will make the collision visible.
    """
    try:
        from serial.tools import list_ports
    except ImportError:
        return {}
    found: Dict[int, str] = {}
    for info in list_ports.comports():
        if (info.vid, info.pid) != APP_VIDPID:
            continue
        controller = _probe_port(info.device, timeout)
        if controller is not None and controller not in found:
            found[controller] = info.device
    return found


def _probe_port(device: str, timeout: float) -> Optional[int]:
    """Provoke a RESYNC on one port; -> its controller id, or None."""
    import serial

    try:
        conn = serial.Serial(device, baudrate=BAUD, timeout=0, write_timeout=1.0)
    except (OSError, ValueError):
        return None
    try:
        time.sleep(0.2)  # let the CDC connection settle mid-frame
        conn.reset_input_buffer()
        splitter = p.FrameSplitter()
        # One COBS chunk decoding to a single junk byte: fails CRC, and
        # the board answers RESYNC naming itself. HELLO (an unhosted
        # board announcing) carries the same header field.
        conn.write(b"\x01\x00")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data = conn.read(4096)
            for raw in splitter.feed(data):
                try:
                    frame_type, controller, _, _ = p.parse_frame(raw)
                except p.ProtocolError:
                    continue
                if frame_type in (p.FRAME_RESYNC, p.FRAME_HELLO):
                    return controller
            if not data:
                time.sleep(0.02)
        return None
    except OSError:
        return None
    finally:
        conn.close()


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

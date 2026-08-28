"""Board discovery: which Scorpios are on USB, and are they really Scorpios.

Two checks, and a board must pass both:

1. **USB identity.** A flashed Scorpio in application mode enumerates as
   ``239A:8121``. This is what separates a board from everything else that
   turns up on a bus — USB-UART bridges, keyboards, radios.
2. **Protocol identity.** Only firmware speaking the Luminary protocol
   answers a deliberately corrupt frame with RESYNC, whose header names the
   board's compiled-in controller id (spec §13.3).

Neither alone is enough. VID:PID is a claim any device can make, and it says
nothing about what firmware is actually on the board — a Scorpio with an
empty flash does not enumerate at all, and one with foreign firmware may
enumerate and never answer. The probe alone would have to open every serial
port on the system, including ones owned by unrelated devices, which is both
rude and slow. Requiring both is what makes "is this a Scorpio?" answerable
rather than guessed.

This module is the single source of that answer: ``firmware/tools/whoami.py``
and ``luminary/mapping/serial_sink.py`` both route through it, so the identity
rule cannot drift between surfaces (CLAUDE.md, "one logic path across modes").
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from luminary.comms import protocol as p

# Application-mode USB identity of a flashed Scorpio.
APP_VIDPID = (0x239A, 0x8121)
# The RP2040 mask-ROM bootloader. Present whenever BOOTSEL is held at plug-in,
# and unbrickable by definition: it lives in ROM, so a board that appears here
# is electrically fine no matter what its flash contains.
BOOTSEL_VIDPID = (0x2E8A, 0x0003)
BOOTSEL_LABEL = "RPI-RP2"

BAUD = 2_000_000
PROBE_TIMEOUT = 1.5

# Status values, most-useful-first when reported.
BOARD = "board"  # answered with a controller id
BLOCKED = "blocked"  # right USB identity, port not openable
UNRESPONSIVE = "unresponsive"  # right USB identity, no protocol answer
BOOTSEL = "bootsel"  # in the ROM bootloader, awaiting a UF2
FOREIGN = "foreign"  # something else entirely


@dataclass
class Candidate:
    """One USB device considered as a possible board."""

    device: str  # port path, or the BOOTSEL mount
    status: str
    controller: Optional[int] = None
    vid: Optional[int] = None
    pid: Optional[int] = None
    usb_serial: Optional[str] = None
    description: str = ""
    detail: str = ""

    @property
    def is_board(self) -> bool:
        return self.status == BOARD

    def vidpid(self) -> str:
        if self.vid is None or self.pid is None:
            return "-"
        return f"{self.vid:04x}:{self.pid:04x}"


def probe_port(
    device: str, timeout: float = PROBE_TIMEOUT
) -> Tuple[Optional[int], str]:
    """Provoke an identifying frame on one port -> (controller id, how).

    A one-byte junk payload is a COBS chunk that decodes and then fails CRC,
    so the board answers RESYNC. That works in *any* board state, unlike
    HELLO, which the firmware stops repeating once its first frame arrives.
    """
    try:
        import serial
    except ImportError:
        return None, "pyserial not installed"
    try:
        conn = serial.Serial(device, baudrate=BAUD, timeout=0, write_timeout=1.0)
    except (OSError, ValueError) as exc:
        return None, f"cannot open: {exc}"
    try:
        time.sleep(0.2)  # let the CDC connection settle mid-frame
        conn.reset_input_buffer()
        splitter = p.FrameSplitter()
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
    except OSError as exc:
        return None, f"read failed: {exc}"
    finally:
        try:
            conn.close()
        except Exception:
            pass


def bootsel_devices() -> List[Candidate]:
    """RP2040s sitting in the ROM bootloader, with their UF2 mount if mounted.

    Read from sysfs rather than pyserial: the bootloader is a mass-storage
    device and never appears as a serial port, so a board waiting to be
    flashed is invisible to every port-based enumeration.
    """
    found: List[Candidate] = []
    root = Path("/sys/bus/usb/devices")
    if not root.is_dir():
        return found
    mount = _bootsel_mount()
    for entry in sorted(root.iterdir()):
        try:
            vid = int((entry / "idVendor").read_text().strip(), 16)
            pid = int((entry / "idProduct").read_text().strip(), 16)
        except (OSError, ValueError):
            continue
        if (vid, pid) != BOOTSEL_VIDPID:
            continue
        found.append(
            Candidate(
                device=str(mount) if mount else f"usb:{entry.name}",
                status=BOOTSEL,
                vid=vid,
                pid=pid,
                description="RP2040 ROM bootloader",
                detail=(
                    f"mounted at {mount}"
                    if mount
                    else "not mounted; mount the RPI-RP2 volume to flash"
                ),
            )
        )
    return found


def _bootsel_mount() -> Optional[Path]:
    """Where the RPI-RP2 volume is mounted, if it is."""
    try:
        mounts = Path("/proc/mounts").read_text().splitlines()
    except OSError:
        return None
    for line in mounts:
        parts = line.split()
        if len(parts) < 2:
            continue
        target = Path(parts[1].replace("\\040", " "))
        if target.name == BOOTSEL_LABEL and (target / "INFO_UF2.TXT").exists():
            return target
    return None


def discover(
    *,
    all_ports: bool = False,
    timeout: float = PROBE_TIMEOUT,
) -> List[Candidate]:
    """Every USB device considered, classified, boards probed for identity.

    ``all_ports`` probes serial ports whose VID:PID is *not* the Scorpio's.
    Off by default because it opens ports belonging to unrelated devices;
    on, it is the escape hatch for a board reached through a bridge or
    reporting an unexpected identity.
    """
    try:
        from serial.tools import list_ports
    except ImportError:
        return bootsel_devices()

    candidates: List[Candidate] = []
    for info in list_ports.comports():
        # Legacy motherboard UARTs (/dev/ttyS*) have no USB identity at all.
        # They cannot be a board on USB, and there are typically 32 of them,
        # so they are dropped rather than listed as rejected candidates.
        if info.vid is None and not all_ports:
            continue
        matches = (info.vid, info.pid) == APP_VIDPID
        base = Candidate(
            device=info.device,
            status=FOREIGN,
            vid=info.vid,
            pid=info.pid,
            usb_serial=info.serial_number,
            description=(info.description or "").strip(),
        )
        if not matches and not all_ports:
            base.detail = "not a Scorpio USB identity; skipped"
            candidates.append(base)
            continue
        controller, how = probe_port(info.device, timeout)
        if controller is None:
            # "cannot open" is a different problem from "did not answer", and
            # conflating them sends people to debug firmware when the real
            # fault is that they are not in the dialout group. A board that
            # was just flashed re-enumerates as a new device node, so this is
            # the common first-run failure, not an exotic one.
            blocked = how.startswith("cannot open")
            if blocked:
                base.status = BLOCKED
                base.detail = (
                    f"{how}\n    fix: add yourself to the dialout group "
                    "(`sudo usermod -aG dialout $USER`, then log out and in)"
                )
            else:
                base.status = UNRESPONSIVE if matches else FOREIGN
                base.detail = (
                    f"{how} — right USB identity, but nothing speaking the "
                    "Luminary protocol"
                    if matches
                    else f"{how}"
                )
        else:
            base.status = BOARD
            base.controller = controller
            base.detail = f"identified via {how}"
            if not matches:
                base.detail += " (non-standard USB identity)"
        candidates.append(base)

    candidates.extend(bootsel_devices())
    return candidates


def boards_by_controller(candidates: List[Candidate]) -> Dict[int, str]:
    """controller id -> port, for confirmed boards only.

    On a duplicate id the first wins, matching the historical behaviour;
    callers that care should report the collision from
    :func:`duplicate_controllers` rather than silently accept one board.
    """
    ports: Dict[int, str] = {}
    for candidate in candidates:
        if candidate.is_board and candidate.controller is not None:
            ports.setdefault(candidate.controller, candidate.device)
    return ports


def duplicate_controllers(candidates: List[Candidate]) -> Dict[int, List[str]]:
    """Controller ids claimed by more than one board.

    Two boards flashed with the same id address the same lights: the codec
    routes by the header controller byte, so one of them renders the other's
    geometry. Silent first-wins made this look like a missing board instead
    of a misflash, so it is surfaced rather than resolved.
    """
    seen: Dict[int, List[str]] = {}
    for candidate in candidates:
        if candidate.is_board and candidate.controller is not None:
            seen.setdefault(candidate.controller, []).append(candidate.device)
    return {c: ports for c, ports in seen.items() if len(ports) > 1}


def probe_controllers(timeout: float = PROBE_TIMEOUT) -> Dict[int, str]:
    """controller id -> port for every board that answers (mapping's view)."""
    return boards_by_controller(discover(timeout=timeout))

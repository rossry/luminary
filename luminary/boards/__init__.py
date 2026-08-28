"""Board discovery, identity, and the registered inventory (spec §12.2.4)."""

from luminary.boards.discovery import (
    APP_VIDPID,
    BLOCKED,
    BOARD,
    BOOTSEL,
    BOOTSEL_VIDPID,
    FOREIGN,
    UNRESPONSIVE,
    Candidate,
    boards_by_controller,
    discover,
    duplicate_controllers,
    probe_controllers,
    probe_port,
)
from luminary.boards.registry import BoardRecord, BoardRegistry

__all__ = [
    "APP_VIDPID",
    "BLOCKED",
    "BOARD",
    "BOOTSEL",
    "BOOTSEL_VIDPID",
    "FOREIGN",
    "UNRESPONSIVE",
    "Candidate",
    "BoardRecord",
    "BoardRegistry",
    "boards_by_controller",
    "discover",
    "duplicate_controllers",
    "probe_controllers",
    "probe_port",
]

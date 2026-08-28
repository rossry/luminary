"""The registered inventory of boards: ``var/boards.yaml``.

Keyed on **controller id, never port path**. Port paths are assigned by the
kernel in enumeration order and move whenever boards are plugged in a
different order or a hub re-enumerates; the controller id is compiled into
the firmware and is the only stable name a board has. This is the same rule
the mapping records follow (plan/mapping/DESCRIPTION.md), and for the same
reason.

The recorded port is therefore a *hint*, useful for reporting and for
skipping a probe when it still holds — never an identity. Every consumer
re-probes at startup and treats a mismatch as "the board moved", not as a
different board.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

import yaml

FILENAME = "boards.yaml"
SCHEMA = "luminary.boards/1"


@dataclass
class BoardRecord:
    controller: int
    port: Optional[str] = None
    usb_serial: Optional[str] = None
    last_seen: Optional[str] = None
    note: str = ""


class BoardRegistry:
    """Load/save the board inventory for one runtime-state directory."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.path = self.directory / FILENAME
        self.records: Dict[int, BoardRecord] = {}

    # ------------------------------------------------------------ persistence

    def load(self) -> "BoardRegistry":
        """Read the inventory; a missing or empty file is simply no boards."""
        self.records = {}
        if not self.path.exists():
            return self
        try:
            doc = yaml.safe_load(self.path.read_text()) or {}
        except (OSError, yaml.YAMLError):
            return self
        for entry in doc.get("boards") or []:
            try:
                controller = int(entry["controller"])
            except (KeyError, TypeError, ValueError):
                continue
            self.records[controller] = BoardRecord(
                controller=controller,
                port=entry.get("port"),
                usb_serial=entry.get("usb_serial"),
                last_seen=entry.get("last_seen"),
                note=entry.get("note", "") or "",
            )
        return self

    def save(self) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        doc = {
            "schema": SCHEMA,
            "boards": [asdict(self.records[c]) for c in sorted(self.records)],
        }
        self.path.write_text(yaml.safe_dump(doc, sort_keys=False))
        return self.path

    # ---------------------------------------------------------------- updates

    def register(
        self, controller: int, port: str, usb_serial: Optional[str], when: str
    ) -> BoardRecord:
        """Record a board seen at ``port``, preserving any operator note."""
        existing = self.records.get(controller)
        record = BoardRecord(
            controller=controller,
            port=port,
            usb_serial=usb_serial,
            last_seen=when,
            note=existing.note if existing else "",
        )
        self.records[controller] = record
        return record

    def ports(self) -> Dict[int, str]:
        """controller -> last known port, for boards that have one."""
        return {
            c: r.port for c, r in sorted(self.records.items()) if r.port is not None
        }

    def controllers(self) -> List[int]:
        return sorted(self.records)

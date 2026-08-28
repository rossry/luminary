"""Mapping persistence: one YAML per board, keyed by controller id.

Schema and discipline per plan/mapping/DESCRIPTION.md "Saved state":
`mapping-<controller_id>.yaml` with the `luminary.mapping/1` tag; every
write goes to the final path, is fsync'd, read back and byte-compared,
then copied to `<name>.bak` (fsync'd again) — a torn write is caught the
moment it happens, and the `.bak` twin survives the next one. The
`progress` block is the `--continue` marker: carried while its board is
incomplete, dropped from the file once every planned panel of that board
is recorded — so when the whole mapping reaches "done", no file carries
one.

Board-side copies ride the :class:`BoardStore` protocol. The serial
transport is a handoff ("Board-side mapping storage" in the DESCRIPTION),
so :class:`SerialBoards` raises until the firmware grows FILE_* frames;
:class:`LocalOnlyBoards` is the working default. Parsing is deliberately
conservative (`safe_load`, schema tag, plan cross-checks): these files
drive physical addressing, so anything unrecognized is an error, never a
guess.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Tuple, runtime_checkable

import yaml

from luminary.mapping.plan import Face, Plan
from luminary.mapping.state import BoardRecord, ChannelRecord, MappingState

SCHEMA = "luminary.mapping/1"
ABSENT_SCHEMA = "luminary.mapping-absent/1"

_WINDINGS = ("cw", "ccw")
_DENSITIES = (180, 360)


class StoreError(RuntimeError):
    """A mapping file failed verification or does not match the plan."""


def _fsync_write(path: Path, data: bytes) -> None:
    """Write to the final path and force it to disk. No tempfile/rename
    dance: the `.bak` twin, not atomicity, is the recovery path here."""
    with open(path, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def dated_backup(path: Path) -> Path:
    """Copy ``path`` to ``<name>.<UTC timestamp>.bak`` and return the copy.

    The prior-local safety net of ``--trust-boards``
    (``mapping-3.yaml.2026-08-27T0412Z.bak``). Never overwrites an earlier
    backup: same-minute repeats gain a counter.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    backup = path.with_name(f"{path.name}.{stamp}.bak")
    n = 2
    while backup.exists():
        backup = path.with_name(f"{path.name}.{stamp}.{n}.bak")
        n += 1
    _fsync_write(backup, path.read_bytes())
    return backup


class MappingStore:
    """One YAML per assigned board under ``directory``."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        # Informational only, reprobed at startup (DESCRIPTION schema
        # comment); the CLI fills this from the identity probe.
        self.port_hints: Dict[int, str] = {}

    def path_for(self, controller_id: int) -> Path:
        return self.directory / f"mapping-{controller_id}.yaml"

    # Boards recorded absent have no controller id, so they cannot be keyed
    # the way every other record is. They get one small file listing the data
    # units that are not on the sphere. Without it an absent board is
    # indistinguishable from an unmapped one on reload, and `geometry` refuses
    # the deployment over a board the operator already said was missing.
    @property
    def absent_path(self) -> Path:
        return self.directory / "absent.yaml"

    def clear_records(self) -> List[Path]:
        """Delete every board YAML and its ``.bak`` twin (the demo's
        start-over); dated backups are kept. Returns what was removed."""
        removed: List[Path] = []
        for path in sorted(self.directory.glob("mapping-*.yaml")):
            twin = path.with_name(path.name + ".bak")
            for victim in (path, twin):
                if victim.exists():
                    victim.unlink()
                    removed.append(victim)
        return removed

    # -------------------------------------------------------------- save

    def save_state(self, state: MappingState, plan: Plan) -> Dict[int, Path]:
        """Write every assigned board's YAML; -> controller id -> path.

        Unassigned boards have no controller id to key a file on, so they
        are simply absent — exactly what ``load_records`` tolerates.
        """
        written: Dict[int, Path] = {}
        absent = [unit for unit in plan.units if state.boards[unit].absent]
        if absent:
            self._write_verified(
                self.absent_path,
                yaml.safe_dump(
                    {"schema": ABSENT_SCHEMA, "units": absent}, sort_keys=False
                ).encode(),
            )
        elif self.absent_path.exists():
            self.absent_path.unlink()  # nothing absent any more
        for unit in plan.units:
            board = state.boards[unit]
            if board.controller_id is None:
                continue
            data = yaml.safe_dump(
                self._board_doc(board, plan, state), sort_keys=False
            ).encode()
            path = self.path_for(board.controller_id)
            self._write_verified(path, data)
            written[board.controller_id] = path
        return written

    def _board_doc(self, board: BoardRecord, plan: Plan, state: MappingState) -> dict:
        assert board.controller_id is not None
        block: dict = {
            "controller_id": board.controller_id,
            "data_unit_vertex": board.unit_vertex,
        }
        hint = self.port_hints.get(board.controller_id)
        if hint is not None:
            block["port_hint"] = hint
        doc: dict = {
            "schema": SCHEMA,
            "board": block,
            "absent": board.absent,
            "absent_faces": [list(face) for face in board.absent_faces],
            "channels": {
                ch: {
                    "face": list(rec.face),
                    "winding": rec.winding,
                    "density": rec.density,
                }
                for ch, rec in sorted(board.channels.items())
            },
        }
        if len(board.channels) < len(plan.panels[board.unit_vertex]):
            # Cursor: the next board to map while assigning ports, the
            # next panel ordinal on this board while mapping panels.
            cursor = (
                state.board_cursor if state.stage == "ports" else len(board.channels)
            )
            doc["progress"] = {"stage": state.stage, "cursor": cursor}
        return doc

    def _write_verified(self, path: Path, data: bytes) -> None:
        """The write discipline: final path, fsync, readback compare,
        `.bak` copy, fsync that."""
        _fsync_write(path, data)
        readback = path.read_bytes()
        if readback != data:
            raise StoreError(f"readback mismatch after writing {path}")
        _fsync_write(path.with_name(path.name + ".bak"), readback)

    # -------------------------------------------------------------- load

    def load_records(self, plan: Plan) -> Dict[int, BoardRecord]:
        """Read the board YAMLs back into state-machine records, keyed by
        unit vertex (what ``resume_state`` takes). Absent files are boards
        not yet assigned."""
        records: Dict[int, BoardRecord] = {}
        for path in sorted(self.directory.glob("mapping-*.yaml")):
            controller_id, record = _parse_board_yaml(path.read_bytes(), plan)
            if path.name != self.path_for(controller_id).name:
                raise StoreError(
                    f"{path.name} declares controller {controller_id}; "
                    "the filename must agree"
                )
            if record.unit_vertex in records:
                raise StoreError(
                    f"data unit {record.unit_vertex} is claimed by two mapping files"
                )
            records[record.unit_vertex] = record
        for unit in self._load_absent(plan):
            if unit in records:
                raise StoreError(
                    f"data unit {unit} is recorded absent and also has a "
                    "mapping file"
                )
            records[unit] = BoardRecord(unit_vertex=unit, absent=True)
        return records

    def _load_absent(self, plan: Plan) -> List[int]:
        """Data units recorded as not on the sphere."""
        if not self.absent_path.exists():
            return []
        try:
            doc = yaml.safe_load(self.absent_path.read_bytes()) or {}
        except yaml.YAMLError as exc:
            raise StoreError(f"{self.absent_path.name}: {exc}")
        if doc.get("schema") != ABSENT_SCHEMA:
            raise StoreError(f"{self.absent_path.name}: schema {doc.get('schema')!r}")
        units = doc.get("units") or []
        for unit in units:
            if unit not in plan.units:
                raise StoreError(
                    f"{self.absent_path.name}: {unit} is not a data unit of "
                    f"{plan.net_name}"
                )
        return [int(u) for u in units]


def _parse_board_yaml(data: bytes, plan: Plan) -> Tuple[int, BoardRecord]:
    """``safe_load`` + schema-tag and plan validation -> (controller id,
    record)."""
    doc = yaml.safe_load(data)
    if not isinstance(doc, dict):
        raise StoreError("mapping file is not a YAML mapping")
    if doc.get("schema") != SCHEMA:
        raise StoreError(
            f"unrecognized schema tag {doc.get('schema')!r} (want {SCHEMA})"
        )
    board = doc.get("board")
    if not isinstance(board, dict) or not {"controller_id", "data_unit_vertex"} <= (
        board.keys()
    ):
        raise StoreError("malformed board block")
    controller_id = int(board["controller_id"])
    unit = int(board["data_unit_vertex"])
    if unit not in plan.panels:
        raise StoreError(f"data unit {unit} is not in the {plan.net_name} plan")
    channels: Dict[int, ChannelRecord] = {}
    for key, rec in (doc.get("channels") or {}).items():
        channel = int(key)
        if not 0 <= channel <= 7:
            raise StoreError(f"channel {channel} out of range")
        if (
            not isinstance(rec, dict)
            or not {"face", "winding", "density"} <= rec.keys()
        ):
            raise StoreError(f"channel {channel}: malformed record")
        verts = [int(v) for v in rec["face"]]
        if len(verts) != 3:
            raise StoreError(f"channel {channel}: face must be three vertex ids")
        face: Face = (verts[0], verts[1], verts[2])
        panel = plan.by_face.get(face)
        if panel is None:
            raise StoreError(f"channel {channel}: face {face} is not a planned panel")
        if panel.unit_vertex != unit:
            raise StoreError(
                f"channel {channel}: face {face} belongs to unit "
                f"{panel.unit_vertex}, not {unit}"
            )
        winding = rec["winding"]
        if winding not in _WINDINGS:
            raise StoreError(f"channel {channel}: winding {winding!r}")
        density = int(rec["density"])
        if density not in _DENSITIES:
            raise StoreError(f"channel {channel}: density {density}")
        channels[channel] = ChannelRecord(face=face, winding=winding, density=density)
    record = BoardRecord(
        unit_vertex=unit,
        controller_id=controller_id,
        channels=channels,
        # Density is a property of the strip in the channel, so it is seeded
        # per channel on load and survives a panel being moved elsewhere.
        densities={ch: rec.density for ch, rec in channels.items()},
        # Recorded absent is not the same as unmapped: the sequence must not
        # come back to it and the geometry must not refuse to build over it.
        absent=bool(doc.get("absent", False)),
        absent_faces=tuple(
            sorted(tuple(sorted(f)) for f in (doc.get("absent_faces") or []))
        ),
    )
    return controller_id, record


# ------------------------------------------------------------ board side


@runtime_checkable
class BoardStore(Protocol):
    """Board-side mapping storage: the sphere carries its own copy of
    each YAML (DESCRIPTION "Board-side mapping storage")."""

    def controllers(self) -> List[int]:
        """Controller ids reachable for board-side reads/writes."""
        ...

    def read_mapping(self, controller_id: int) -> Optional[bytes]:
        """The board's stored YAML, or None if it holds none."""
        ...

    def write_mapping(self, controller_id: int, data: bytes) -> None:
        """Replace the board's stored YAML."""
        ...


class LocalOnlyBoards:
    """No board-side storage: sync is a no-op — the default until the
    firmware transport lands."""

    def controllers(self) -> List[int]:
        return []

    def read_mapping(self, controller_id: int) -> Optional[bytes]:
        return None

    def write_mapping(self, controller_id: int, data: bytes) -> None:
        return None


_HANDOFF = (
    "board-side mapping storage is not implemented: the FILE_* serial frames "
    'are a firmware handoff — see "Board-side mapping storage" in '
    "plan/mapping/DESCRIPTION.md"
)


class SerialBoards:
    """The real transport, once the firmware grows FILE_READ/FILE_WRITE."""

    def __init__(self, ports: Dict[int, str]) -> None:
        self.ports = dict(ports)

    def controllers(self) -> List[int]:
        return sorted(self.ports)

    def read_mapping(self, controller_id: int) -> Optional[bytes]:
        raise NotImplementedError(_HANDOFF)

    def write_mapping(self, controller_id: int, data: bytes) -> None:
        raise NotImplementedError(_HANDOFF)


def trust_boards(
    store: MappingStore, board_store: BoardStore, plan: Plan
) -> Dict[int, Optional[Path]]:
    """``--trust-boards``: the sphere's copies replace the local files.

    For each reachable board: validate its stored YAML against the plan,
    save the prior local file as a dated backup, write the board copy
    over local with the usual verify discipline. Returns controller id ->
    dated-backup path (None where no local file existed). A board without
    a stored mapping is skipped — absence is not evidence.
    """
    replaced: Dict[int, Optional[Path]] = {}
    for controller_id in board_store.controllers():
        data = board_store.read_mapping(controller_id)
        if data is None:
            continue
        declared, _ = _parse_board_yaml(data, plan)
        if declared != controller_id:
            raise StoreError(
                f"board {controller_id} serves a mapping declaring "
                f"controller {declared}"
            )
        local = store.path_for(controller_id)
        backup = dated_backup(local) if local.exists() else None
        store._write_verified(local, data)
        replaced[controller_id] = backup
    return replaced

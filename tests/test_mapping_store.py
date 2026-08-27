"""Mapping persistence: round-trip, write discipline, markers, trust.

States are produced by walking the real state machine — the store must
round-trip exactly what the sequence produces, not hand-built fixtures.
"""

import re

import pytest
import yaml

from luminary.mapping import store as store_mod
from luminary.mapping.plan import Plan
from luminary.mapping.state import Event, initial_state, resume_state, step
from luminary.mapping.store import (
    SCHEMA,
    BoardStore,
    LocalOnlyBoards,
    MappingStore,
    SerialBoards,
    StoreError,
    dated_backup,
    trust_boards,
)

CONTROLLERS = [3, 1, 4, 0, 6, 2, 5]

_BAK_RE = re.compile(r"^mapping-\d+\.yaml\.\d{4}-\d{2}-\d{2}T\d{4}Z(\.\d+)?\.bak$")


@pytest.fixture(scope="module")
def plan():
    return Plan.load()


@pytest.fixture(scope="module")
def mid_state(plan):
    """All ports assigned, three panels mapped (one 360, one cw)."""
    state = initial_state(plan, CONTROLLERS)
    while state.stage == "ports":
        state = step(state, plan, Event.ENTER)
    state = step(state, plan, Event.UP)  # density 360
    state = step(state, plan, Event.ENTER)
    state = step(state, plan, Event.DOWN)  # winding cw
    state = step(state, plan, Event.ENTER)
    state = step(state, plan, Event.ENTER)
    return state


@pytest.fixture(scope="module")
def done_state(plan, mid_state):
    state = mid_state
    while state.stage != "done":
        state = step(state, plan, Event.ENTER)
    return state


class FakeBoards:
    """In-memory BoardStore: what SerialBoards will be once the firmware
    grows FILE_* frames."""

    def __init__(self, files):
        self.files = dict(files)

    def controllers(self):
        return sorted(self.files)

    def read_mapping(self, controller_id):
        return self.files.get(controller_id)

    def write_mapping(self, controller_id, data):
        self.files[controller_id] = data


# ------------------------------------------------------------ save/load


def test_round_trip_through_the_state_machine(tmp_path, plan, mid_state):
    store = MappingStore(tmp_path)
    store.port_hints = {3: "/dev/ttyACM2"}
    written = store.save_state(mid_state, plan)
    assert set(written) == {b.controller_id for b in mid_state.boards.values()}
    for path in written.values():
        assert path.parent == tmp_path
        doc = yaml.safe_load(path.read_text())
        assert doc["schema"] == SCHEMA
    hinted = yaml.safe_load(store.path_for(3).read_text())
    assert hinted["board"]["port_hint"] == "/dev/ttyACM2"

    loaded = store.load_records(plan)
    assert loaded == dict(mid_state.boards)
    # Resuming from disk is indistinguishable from resuming in memory.
    assert resume_state(plan, CONTROLLERS, loaded) == resume_state(
        plan, CONTROLLERS, dict(mid_state.boards)
    )


def test_every_write_leaves_a_matching_bak_twin(tmp_path, plan, mid_state):
    store = MappingStore(tmp_path)
    for path in store.save_state(mid_state, plan).values():
        twin = path.with_name(path.name + ".bak")
        assert twin.read_bytes() == path.read_bytes()


def test_load_records_tolerates_an_empty_store(tmp_path, plan):
    assert MappingStore(tmp_path).load_records(plan) == {}


def test_clear_records_removes_yamls_and_twins_keeps_dated(tmp_path, plan, mid_state):
    """The demo's start-over: board YAMLs and their .bak twins go, dated
    backups (the trust flow's history) stay."""
    store = MappingStore(tmp_path)
    store.save_state(mid_state, plan)
    dated = tmp_path / "mapping-3.yaml.2026-08-27T0412Z.bak"
    dated.write_bytes(b"history")
    assert list(tmp_path.glob("mapping-*.yaml"))
    removed = store.clear_records()
    assert removed and all(not p.exists() for p in removed)
    assert list(tmp_path.glob("mapping-*.yaml")) == []
    assert not any(p.name.endswith(".yaml.bak") for p in tmp_path.iterdir())
    assert dated.exists()
    assert store.load_records(plan) == {}


# ------------------------------------------------------- progress marker


def test_progress_markers_mid_way_and_absent_at_done(
    tmp_path, plan, mid_state, done_state
):
    ports_dir = tmp_path / "ports"
    state = step(initial_state(plan, CONTROLLERS), plan, Event.ENTER)
    written = MappingStore(ports_dir).save_state(state, plan)
    assert len(written) == 1  # only the one assigned board has a file
    (path,) = written.values()
    assert yaml.safe_load(path.read_text())["progress"]["stage"] == "ports"

    store = MappingStore(tmp_path / "walk")
    marked = 0
    for cid, path in store.save_state(mid_state, plan).items():
        board = next(b for b in mid_state.boards.values() if b.controller_id == cid)
        complete = len(board.channels) == len(plan.panels[board.unit_vertex])
        doc = yaml.safe_load(path.read_text())
        assert ("progress" in doc) == (not complete)
        if not complete:
            marked += 1
            assert doc["progress"] == {
                "stage": "panels",
                "cursor": len(board.channels),
            }
    assert marked > 0

    for path in store.save_state(done_state, plan).values():
        assert "progress" not in yaml.safe_load(path.read_text())


# ------------------------------------------------------ write discipline


def test_readback_verification_catches_a_corrupted_write(
    tmp_path, plan, mid_state, monkeypatch
):
    store = MappingStore(tmp_path)
    real = store_mod._fsync_write

    def torn(path, data):
        real(path, data[:-1])  # the disk did not take the last byte

    monkeypatch.setattr(store_mod, "_fsync_write", torn)
    with pytest.raises(StoreError, match="readback mismatch"):
        store.save_state(mid_state, plan)


def test_dated_backup_naming_and_content(tmp_path):
    path = tmp_path / "mapping-9.yaml"
    path.write_bytes(b"one")
    first = dated_backup(path)
    assert _BAK_RE.match(first.name)
    assert first.read_bytes() == b"one"
    path.write_bytes(b"two")
    second = dated_backup(path)  # same minute: gains a counter, no clobber
    assert second != first and _BAK_RE.match(second.name)
    assert first.read_bytes() == b"one" and second.read_bytes() == b"two"


# ------------------------------------------------------------ validation


def _doc(plan, controller_id=3, **overrides):
    unit = plan.units[0]
    panel = plan.panels[unit][0]
    doc = {
        "schema": SCHEMA,
        "board": {"controller_id": controller_id, "data_unit_vertex": unit},
        "channels": {0: {"face": list(panel.face), "winding": "ccw", "density": 180}},
    }
    doc.update(overrides)
    return doc


def _write(store, name, doc):
    (store.directory / name).write_text(yaml.safe_dump(doc, sort_keys=False))


def test_conservative_parsing_rejects_bad_files(tmp_path, plan):
    store = MappingStore(tmp_path)
    _write(store, "mapping-3.yaml", _doc(plan, schema="luminary.mapping/2"))
    with pytest.raises(StoreError, match="schema tag"):
        store.load_records(plan)

    bad_face = _doc(plan)
    bad_face["channels"][0]["face"] = [1, 2, 3]
    _write(store, "mapping-3.yaml", bad_face)
    with pytest.raises(StoreError, match="not a planned panel"):
        store.load_records(plan)

    bad_winding = _doc(plan)
    bad_winding["channels"][0]["winding"] = "clockwise"
    _write(store, "mapping-3.yaml", bad_winding)
    with pytest.raises(StoreError, match="winding"):
        store.load_records(plan)

    bad_density = _doc(plan)
    bad_density["channels"][0]["density"] = 200
    _write(store, "mapping-3.yaml", bad_density)
    with pytest.raises(StoreError, match="density"):
        store.load_records(plan)

    (store.directory / "mapping-3.yaml").unlink()
    _write(store, "mapping-4.yaml", _doc(plan, controller_id=3))
    with pytest.raises(StoreError, match="filename"):
        store.load_records(plan)

    (store.directory / "mapping-4.yaml").unlink()
    _write(store, "mapping-3.yaml", _doc(plan, controller_id=3))
    _write(store, "mapping-5.yaml", _doc(plan, controller_id=5))
    with pytest.raises(StoreError, match="two mapping files"):
        store.load_records(plan)


# ---------------------------------------------------------- board stores


def test_trust_boards_replaces_local_and_keeps_dated_backups(
    tmp_path, plan, mid_state, done_state
):
    local = MappingStore(tmp_path / "local")
    local.save_state(mid_state, plan)
    donor = MappingStore(tmp_path / "donor")
    board_files = {
        cid: path.read_bytes()
        for cid, path in donor.save_state(done_state, plan).items()
    }
    absent = min(board_files)  # one board holds no mapping: skipped
    del board_files[absent]
    fake = FakeBoards(board_files)
    assert isinstance(fake, BoardStore)

    assigned = {b.controller_id for b in mid_state.boards.values()}
    before = {cid: local.path_for(cid).read_bytes() for cid in assigned}
    replaced = trust_boards(local, fake, plan)

    assert set(replaced) == set(board_files)
    for cid, backup in replaced.items():
        assert local.path_for(cid).read_bytes() == board_files[cid]
        assert backup is not None and _BAK_RE.match(backup.name)
        assert backup.read_bytes() == before[cid]
    assert local.path_for(absent).read_bytes() == before[absent]

    loaded = local.load_records(plan)
    trusted = {
        b.unit_vertex: b
        for b in done_state.boards.values()
        if b.controller_id in board_files
    }
    for unit, record in trusted.items():
        assert loaded[unit] == record


def test_trust_boards_validates_before_clobbering(tmp_path, plan, mid_state):
    local = MappingStore(tmp_path)
    local.save_state(mid_state, plan)
    before = local.path_for(3).read_bytes()
    fake = FakeBoards({3: yaml.safe_dump(_doc(plan, controller_id=4)).encode()})
    with pytest.raises(StoreError, match="declaring"):
        trust_boards(local, fake, plan)
    assert local.path_for(3).read_bytes() == before


def test_local_only_boards_is_a_no_op(tmp_path, plan, mid_state):
    local = MappingStore(tmp_path)
    written = local.save_state(mid_state, plan)
    before = {cid: path.read_bytes() for cid, path in written.items()}
    boards = LocalOnlyBoards()
    assert isinstance(boards, BoardStore)
    assert boards.controllers() == []
    assert boards.read_mapping(3) is None
    assert boards.write_mapping(3, b"ignored") is None
    assert trust_boards(local, boards, plan) == {}
    assert {cid: path.read_bytes() for cid, path in written.items()} == before


def test_serial_boards_raise_toward_the_handoff(plan):
    boards = SerialBoards({4: "/dev/ttyACM1", 2: "/dev/ttyACM0"})
    assert isinstance(boards, BoardStore)
    assert boards.controllers() == [2, 4]
    with pytest.raises(NotImplementedError, match="Board-side mapping storage"):
        boards.read_mapping(4)
    with pytest.raises(NotImplementedError, match="plan/mapping/DESCRIPTION.md"):
        boards.write_mapping(4, b"")

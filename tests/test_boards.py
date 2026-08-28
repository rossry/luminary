"""Board discovery, the registry, and flash target selection.

The question these cover is "is this thing on USB actually a Scorpio?", which
has bitten for real: a bus with two CH340 bridges and a keyboard on it looks
plausible to a VID:PID check alone, and a freshly flashed board is a brand-new
device node whose permissions are the usual reason it cannot be verified.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from luminary.boards import discovery
from luminary.boards.flash import targets_from
from luminary.boards.registry import BoardRegistry

SCORPIO_VID, SCORPIO_PID = discovery.APP_VIDPID


def _port(device, vid=None, pid=None, serial_number=None, description="dev"):
    return SimpleNamespace(
        device=device,
        vid=vid,
        pid=pid,
        serial_number=serial_number,
        description=description,
    )


@pytest.fixture
def bus(monkeypatch):
    """Install a fake USB bus and probe; -> a mutable (ports, answers) pair."""
    state = {"ports": [], "answers": {}, "bootsel": []}

    class _FakeListPorts:
        @staticmethod
        def comports():
            return state["ports"]

    import serial.tools

    monkeypatch.setattr(serial.tools, "list_ports", _FakeListPorts, raising=False)
    monkeypatch.setattr(
        discovery,
        "probe_port",
        lambda device, timeout=1.5: state["answers"].get(device, (None, "no response")),
    )
    monkeypatch.setattr(discovery, "bootsel_devices", lambda: list(state["bootsel"]))
    return state


def test_a_real_board_is_identified_by_both_checks(bus):
    bus["ports"] = [_port("/dev/ttyACM0", SCORPIO_VID, SCORPIO_PID, "AB12")]
    bus["answers"] = {"/dev/ttyACM0": (3, "RESYNC")}

    found = discovery.discover()

    assert [c.status for c in found] == [discovery.BOARD]
    assert found[0].controller == 3
    assert discovery.boards_by_controller(found) == {3: "/dev/ttyACM0"}


def test_other_usb_devices_are_not_mistaken_for_boards(bus):
    """A CH340 bridge and a keyboard are never probed, let alone accepted."""
    bus["ports"] = [
        _port("/dev/ttyUSB0", 0x1A86, 0x7523, description="USB Serial"),
        _port("/dev/ttyUSB1", 0x1A86, 0x7523, description="USB Serial"),
    ]
    # Even if something on those ports would answer, they must not be opened.
    bus["answers"] = {"/dev/ttyUSB0": (0, "RESYNC"), "/dev/ttyUSB1": (1, "RESYNC")}

    found = discovery.discover()

    assert {c.status for c in found} == {discovery.FOREIGN}
    assert discovery.boards_by_controller(found) == {}


def test_all_ports_probes_past_the_usb_identity_filter(bus):
    bus["ports"] = [_port("/dev/ttyUSB0", 0x1A86, 0x7523)]
    bus["answers"] = {"/dev/ttyUSB0": (2, "RESYNC")}

    found = discovery.discover(all_ports=True)

    assert found[0].status == discovery.BOARD
    assert found[0].controller == 2
    assert "non-standard USB identity" in found[0].detail


def test_non_usb_serial_ports_are_dropped(bus):
    """The 32 legacy /dev/ttyS* UARTs are not candidates and are not listed."""
    bus["ports"] = [_port(f"/dev/ttyS{i}") for i in range(32)]

    assert discovery.discover() == []


def test_right_identity_but_silent_is_unresponsive_not_foreign(bus):
    bus["ports"] = [_port("/dev/ttyACM0", SCORPIO_VID, SCORPIO_PID)]
    bus["answers"] = {"/dev/ttyACM0": (None, "no response")}

    found = discovery.discover()

    assert found[0].status == discovery.UNRESPONSIVE
    assert "nothing speaking the" in found[0].detail


def test_an_unopenable_port_is_blocked_not_unresponsive(bus):
    """Permission errors must not read as a firmware problem."""
    bus["ports"] = [_port("/dev/ttyACM0", SCORPIO_VID, SCORPIO_PID)]
    bus["answers"] = {
        "/dev/ttyACM0": (None, "cannot open: [Errno 13] Permission denied")
    }

    found = discovery.discover()

    assert found[0].status == discovery.BLOCKED
    assert "dialout" in found[0].detail


def test_duplicate_controller_ids_are_surfaced(bus):
    """Two boards flashed with one id address the same lights."""
    bus["ports"] = [
        _port("/dev/ttyACM0", SCORPIO_VID, SCORPIO_PID),
        _port("/dev/ttyACM1", SCORPIO_VID, SCORPIO_PID),
    ]
    bus["answers"] = {
        "/dev/ttyACM0": (1, "RESYNC"),
        "/dev/ttyACM1": (1, "RESYNC"),
    }

    found = discovery.discover()

    assert discovery.duplicate_controllers(found) == {
        1: ["/dev/ttyACM0", "/dev/ttyACM1"]
    }


def test_bootsel_boards_are_reported_alongside_ports(bus):
    """A board waiting to be flashed has no serial port at all."""
    bus["bootsel"] = [
        discovery.Candidate(
            device="/media/u/RPI-RP2", status=discovery.BOOTSEL, vid=0x2E8A, pid=3
        )
    ]

    found = discovery.discover()

    assert [c.status for c in found] == [discovery.BOOTSEL]
    assert discovery.boards_by_controller(found) == {}


# ------------------------------------------------------------------- registry


def test_registry_round_trips_and_keys_on_controller(tmp_path):
    registry = BoardRegistry(tmp_path).load()
    registry.register(2, "/dev/ttyACM1", "AB12", "2026-01-01T00:00:00+00:00")
    registry.register(0, "/dev/ttyACM0", None, "2026-01-01T00:00:00+00:00")
    registry.save()

    reloaded = BoardRegistry(tmp_path).load()

    assert reloaded.controllers() == [0, 2]
    assert reloaded.ports() == {0: "/dev/ttyACM0", 2: "/dev/ttyACM1"}
    assert reloaded.records[2].usb_serial == "AB12"


def test_registry_re_registration_follows_a_moved_port(tmp_path):
    """Ports move between boots; the controller id is the identity."""
    registry = BoardRegistry(tmp_path).load()
    registry.register(1, "/dev/ttyACM0", "AB12", "t0")
    registry.register(1, "/dev/ttyACM3", "AB12", "t1")

    assert registry.ports() == {1: "/dev/ttyACM3"}
    assert registry.controllers() == [1]


def test_missing_registry_is_simply_no_boards(tmp_path):
    assert BoardRegistry(tmp_path / "nope").load().controllers() == []


# ---------------------------------------------------------------- flash targets


def test_flash_targets_union_registered_and_live():
    registered = {0: "/dev/ttyACM0"}
    live = [
        discovery.Candidate(device="/dev/ttyACM1", status=discovery.BOARD, controller=1)
    ]

    assert targets_from(registered, live) == [0, 1]


def test_flash_targets_default_to_controller_zero_for_a_lone_bootsel_board():
    """First-ever flash: nothing is registered and nothing answers yet."""
    live = [discovery.Candidate(device="/media/u/RPI-RP2", status=discovery.BOOTSEL)]

    assert targets_from({}, live) == [0]


def test_flash_targets_are_empty_when_nothing_is_present():
    assert targets_from({}, []) == []

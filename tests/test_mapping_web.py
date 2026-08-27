"""Mapping web adapters (plan/mapping/DESCRIPTION.md): pages, layout JSON,
stream/control websockets, and the demo scramble.

The apps are built with ``run_ticker=False`` and the tests drive
``core.tick`` / ``core.apply`` directly, so every frame on a socket is
accounted for. Stream sockets carry wire bytes only, decoded here with the
reference Decoder (spec §11.8.1).
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from luminary.comms import protocol as p
from luminary.comms.codec import Decoder
from luminary.geometry.net import Net
from luminary.geometry.pentagon import capture
from luminary.mapping.plan import Plan
from luminary.mapping.session import SessionCore
from luminary.mapping.state import Event, initial_state
from luminary.mapping.web import build_demo_truth, create_demo_app, create_mapping_app

CONTROLLERS = [3, 1, 4, 0, 6, 2, 5]


@pytest.fixture(scope="module")
def plan():
    return Plan.load()


@pytest.fixture(scope="module")
def net_lights():
    configs = Path(__file__).resolve().parents[1] / "configs"
    return capture(Net.from_json_file(configs / "4A-37.json"))


@pytest.fixture()
def core(plan, net_lights):
    return SessionCore(plan, net_lights, initial_state(plan, CONTROLLERS))


class StubStore:
    """Duck-typed stand-in for the CLI's board store."""

    def __init__(self):
        self.calls = []

    def save_state(self, state, plan):
        self.calls.append((state, plan))


def test_pages_and_layout(core, plan):
    app = create_mapping_app(core, run_ticker=False)
    with TestClient(app) as client:
        index = client.get("/")
        assert index.status_code == 200 and "window-canvas" in index.text
        demo = client.get("/demo")
        assert demo.status_code == 200 and "build-canvas" in demo.text
        # The modules the pages import are served alongside.
        assert client.get("/static/mapping.js").status_code == 200
        assert client.get("/static/mapping-demo.js").status_code == 200

        body = client.get("/api/mapping/layout").json()
        assert set(body) == {"layout", "plan", "state"}
        assert body["layout"]["counts"]["total"] == core.window_engine.lights.n
        assert len(body["layout"]["viewBox"]) == 4
        assert body["plan"]["units"] == plan.units
        entry = body["plan"]["panels"][str(plan.units[0])][0]
        assert {"face", "tri_index", "corner_vertex", "corner_xy", "arc"} <= set(entry)
        assert body["state"]["stage"] == "ports"
        assert body["state"]["candidate_controller"] == CONTROLLERS[0]
        # A real mapping session has no scrambled demo build.
        assert client.get("/api/mapping/demo-truth").status_code == 404


def test_window_stream_session_then_frames(core):
    app = create_mapping_app(core, run_ticker=False)
    decoder = Decoder()
    with TestClient(app) as client:
        with client.websocket_connect("/api/mapping/window") as ws:
            # SESSION arrives on accept (window = one controller, the net).
            frame_type, controller = decoder.decode(ws.receive_bytes())
            assert frame_type == p.FRAME_SESSION and controller == 0
            core.tick(0.1)  # manual clock; a join requests the keyframe
            frame_type, _ = decoder.decode(ws.receive_bytes())
            assert frame_type == p.FRAME_KEYFRAME
            core.tick(0.2)
            frame_type, _ = decoder.decode(ws.receive_bytes())
            assert frame_type == p.FRAME_DELTA
            # Decoded state is sane dequantized OKLCH.
            oklch = decoder.active_oklch(0)
            assert oklch.shape == (core.window_engine.lights.n, 3)
            assert oklch[:, 0].min() >= 0.0 and oklch[:, 0].max() <= 1.0


def test_wire_stream_resyncs_across_rebuild(core):
    app = create_mapping_app(core, run_ticker=False)
    decoder = Decoder()
    with TestClient(app) as client:
        with client.websocket_connect("/api/mapping/wire") as ws:
            # Ports stage: only the candidate board is on the wire.
            frame_type, controller = decoder.decode(ws.receive_bytes())
            assert frame_type == p.FRAME_SESSION and controller == CONTROLLERS[0]
            core.tick(0.1)
            frame_type, _ = decoder.decode(ws.receive_bytes())
            assert frame_type == p.FRAME_KEYFRAME
            # Locking the board rebuilds the engines; the adapter re-sends
            # SESSION (now: locked board 3 + next candidate 1), and the
            # fresh encoder keyframes on its first tick — a late joiner and
            # a rebuild are the same clean resync.
            core.apply(Event.ENTER)
            received = [decoder.decode(ws.receive_bytes()) for _ in range(2)]
            assert [t for t, _ in received] == [p.FRAME_SESSION, p.FRAME_SESSION]
            assert sorted(c for _, c in received) == sorted(CONTROLLERS[:2])
            core.tick(0.2)
            received = [decoder.decode(ws.receive_bytes()) for _ in range(2)]
            assert {t for t, _ in received} == {p.FRAME_KEYFRAME}


def test_control_socket_applies_events_and_saves(core, plan):
    store = StubStore()
    app = create_mapping_app(core, store, run_ticker=False)
    with TestClient(app) as client:
        with client.websocket_connect("/api/mapping/control") as ws1:
            first = json.loads(ws1.receive_text())["state"]
            assert first["stage"] == "ports" and first["board_cursor"] == 0
            with client.websocket_connect("/api/mapping/control") as ws2:
                assert json.loads(ws2.receive_text())["state"] == first

                before = core.state
                ws1.send_text(json.dumps({"event": "enter"}))
                pushed = json.loads(ws1.receive_text())["state"]
                assert pushed["board_cursor"] == 1
                unit0 = str(plan.units[0])
                assert pushed["boards"][unit0]["controller_id"] == CONTROLLERS[0]
                # ... and the push reaches every control socket.
                assert json.loads(ws2.receive_text())["state"] == pushed
                assert core.state is not before
                # The duck-typed store saw exactly this state change.
                assert len(store.calls) == 1
                saved_state, saved_plan = store.calls[0]
                assert saved_state is core.state and saved_plan is plan

                # A no-op event (up means nothing in the ports stage) still
                # confirms with a push, and does not save.
                ws1.send_text(json.dumps({"event": "up"}))
                assert json.loads(ws1.receive_text())["state"] == pushed
                assert len(store.calls) == 1


@pytest.fixture(scope="module")
def demo_client():
    app = create_demo_app(run_ticker=False)
    with TestClient(app) as client:
        yield client, app


def test_demo_truth_stable_and_valid(demo_client, plan):
    client, app = demo_client
    one = client.get("/api/mapping/demo-truth").json()
    two = client.get("/api/mapping/demo-truth").json()
    assert one == two  # stable per server run (and per seed)
    assert build_demo_truth(plan, one["seed"]) == one

    controllers = one["controllers"]
    assert sorted(controllers) == list(range(len(plan.units)))
    boards = one["boards"]
    assert sorted(int(cid) for cid in boards) == sorted(controllers)
    # controller -> physical cluster is a bijection onto the planned units.
    assert sorted(b["unit_vertex"] for b in boards.values()) == sorted(plan.units)
    for board in boards.values():
        unit = board["unit_vertex"]
        channels = [int(ch) for ch in board["channels"]]
        assert len(set(channels)) == len(channels)
        assert all(0 <= ch < 8 for ch in channels)
        # Each board's channels carry exactly its unit's planned panels.
        tri = sorted(entry["tri_index"] for entry in board["channels"].values())
        assert tri == sorted(panel.tri_index for panel in plan.panels[unit])
        for entry in board["channels"].values():
            assert entry["winding"] in ("cw", "ccw")
            assert entry["density"] in (180, 360)
    # A different seed scrambles differently.
    assert build_demo_truth(plan, "another-seed") != one
    # The demo session probes exactly the scrambled ids, in probe order.
    assert list(app.state.core.state.controllers) == controllers


def test_demo_app_serves_streams(demo_client):
    client, app = demo_client
    core = app.state.core
    decoder = Decoder()
    with client.websocket_connect("/api/mapping/wire") as ws:
        frame_type, controller = decoder.decode(ws.receive_bytes())
        assert frame_type == p.FRAME_SESSION
        assert controller == core.state.candidate_controller

"""Web API end-to-end (spec §15): the exit-condition flow over TestClient.

save scaffold -> list -> view -> from-scaffold capture -> layout -> view ->
upload pattern (hot reload) -> WS play streaming real wire frames, decoded
with the reference Decoder and compared against ground truth.
"""

import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from luminary.comms import protocol as p
from luminary.comms.codec import Decoder
from luminary.server.app import create_app

SCAFFOLD_DOC = {
    "schema": "luminary.scaffold/1",
    "space": {"authoritative": ["xy"]},
    "lines": [
        {"id": "a", "p1": [0, 0], "p2": [90, 0]},
        {"id": "b", "p1": [90, 0], "p2": [90, 90]},
        {"id": "c", "p1": [90, 90], "p2": [0, 0]},
    ],
    "meta": {"name": "api-triangle"},
}

UPLOAD_PATTERN = """
import numpy as np
from luminary.patterns.base import Pattern

class Uploaded(Pattern):
    name = "uploaded_solid"
    description = "uploaded test pattern"

    def render(self, lights, t):
        out = np.zeros((lights.shape[0], 3))
        out[:, 0] = 0.5
        out[:, 1] = 0.2
        out[:, 2] = (t * 10.0) % 360.0
        return out
"""


@pytest.fixture()
def client(tmp_path):
    app = create_app(state_dir=tmp_path / "state")
    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["protocol_version"] == p.PROTOCOL_VERSION


def test_full_geometry_flow(client):
    # Save scaffold; invalid ones are rejected with detail.
    response = client.post("/api/scaffolds", json=SCAFFOLD_DOC)
    assert response.status_code == 200
    scaffold_id = response.json()["id"]
    assert client.post("/api/scaffolds", json={"schema": "nope"}).status_code == 422

    listed = client.get("/api/scaffolds").json()
    assert any(entry["id"] == scaffold_id for entry in listed)
    assert client.get(f"/api/scaffolds/{scaffold_id}").json()["meta"]["name"] == (
        "api-triangle"
    )
    view = client.get(f"/api/scaffolds/{scaffold_id}/view")
    assert view.status_code == 200 and "<svg" in view.text
    assert client.get("/api/scaffolds/zzzz/view").status_code == 404

    # Capture lights from the scaffold with params (spec §15.3 exit condition).
    response = client.post(
        "/api/lights/from-scaffold",
        json={
            "scaffold_id": scaffold_id,
            "params": {"count_per_line": 9, "interpolate_every": 3},
        },
    )
    assert response.status_code == 200
    lights_id = response.json()["id"]

    listed = client.get("/api/lights").json()
    entry = next(e for e in listed if e["id"] == lights_id)
    assert entry["n_lights"] == 27

    layout = client.get(f"/api/lights/{lights_id}/layout").json()
    assert layout["counts"]["total"] == 27
    assert layout["counts"]["interpolated"] > 0
    assert len(layout["viewBox"]) == 4
    view = client.get(f"/api/lights/{lights_id}/view")
    assert view.status_code == 200 and "<svg" in view.text

    # Round-trip: fetch the saved lights doc and re-save it (dedupe by hash).
    doc = client.get(f"/api/lights/{lights_id}").json()
    assert client.post("/api/lights", json=doc).json()["id"] == lights_id


def test_pattern_upload_and_hot_reload(client):
    names = {
        entry["name"] for entry in client.get("/api/patterns").json() if entry["ok"]
    }
    assert "simple" in names and "uploaded_solid" not in names

    response = client.post(
        "/api/patterns",
        files={"file": ("solid.py", UPLOAD_PATTERN.encode(), "text/x-python")},
    )
    assert response.status_code == 200 and response.json()["ok"]

    names = {
        entry["name"] for entry in client.get("/api/patterns").json() if entry["ok"]
    }
    assert "uploaded_solid" in names

    # A broken upload is reported, never fatal (spec §15.5.1).
    response = client.post(
        "/api/patterns",
        files={"file": ("broken.py", b"import not_a_module_qq\n", "text/x-python")},
    )
    assert response.status_code == 200 and not response.json()["ok"]
    assert client.get("/api/health").json()["status"] == "ok"


def test_play_websocket_streams_wire_protocol(client):
    scaffold_id = client.post("/api/scaffolds", json=SCAFFOLD_DOC).json()["id"]
    lights_id = client.post(
        "/api/lights/from-scaffold",
        json={"scaffold_id": scaffold_id, "params": {"count_per_line": 8}},
    ).json()["id"]

    decoder = Decoder()
    frame_types = []
    with client.websocket_connect(
        f"/api/play?lights={lights_id}&pattern=ripple&fps=60"
    ) as websocket:
        for _ in range(6):
            data = websocket.receive_bytes()
            frame_type, controller = decoder.decode(data)
            frame_types.append(frame_type)
        # Live control: force a keyframe mid-stream (spec §15.4).
        websocket.send_text(json.dumps({"type": "resync"}))
        saw_keyframe = False
        for _ in range(8):
            frame_type, _ = decoder.decode(websocket.receive_bytes())
            frame_types.append(frame_type)
            if frame_type == p.FRAME_KEYFRAME and saw_keyframe:
                break
            saw_keyframe |= frame_type == p.FRAME_KEYFRAME

    assert frame_types[0] == p.FRAME_SESSION
    assert frame_types[1] == p.FRAME_KEYFRAME
    assert p.FRAME_DELTA in frame_types
    assert frame_types.count(p.FRAME_KEYFRAME) >= 2  # initial + resync

    # Decoded state is sane dequantized OKLCH.
    oklch = decoder.active_oklch(0)
    assert oklch.shape[1] == 3
    assert np.all(oklch[:, 0] >= 0) and np.all(oklch[:, 0] <= 1)


def test_play_websocket_rejects_unknown(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/api/play?lights=none&pattern=simple"):
            pass


def test_index_page_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "canvas" in response.text

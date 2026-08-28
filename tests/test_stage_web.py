"""Stage web adapter (luminary/stage/web.py): queue API, wire stream,
viewer page, and the serve-time mount.

The bare-app tests register the routes with no lifespan — no ticker —
and drive ``core.tick()`` against a fake clock, so every frame on the
socket is accounted for (the mapping web tests' approach). The stream
socket carries wire bytes only, decoded with the reference Decoder.
The ``create_app`` tests cover the real mount: composed lifespan, live
ticker, static assets, and the --stage-lights file path.
"""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from luminary.comms import protocol as p
from luminary.comms.codec import Decoder
from luminary.stage.web import register_stage
from tests.test_stage_core import (  # noqa: F401 — imported fixtures
    AUDIO_FILES,
    FakeClock,
    lights,
    make_stage,
    registry,
)

TICK = 1.0 / 30.0


@pytest.fixture()
def stage(tmp_path, registry, lights):  # noqa: F811 — fixture params
    core, spawn, clock = make_stage(tmp_path, registry, lights)
    app = FastAPI()
    register_stage(app, core)
    return app, core, spawn, clock


def test_page_layout_and_audio_endpoints(stage, lights):  # noqa: F811
    app, core, _spawn, _clock = stage
    with TestClient(app) as client:
        page = client.get("/stage")
        assert page.status_code == 200
        assert "stage-canvas" in page.text
        assert './static/stage.js"' in page.text  # page-relative import

        layout = client.get("/api/stage/layout").json()
        assert layout["counts"]["total"] == lights.n == core.engine.lights.n
        assert len(layout["viewBox"]) == 4

        assert client.get("/api/audio").json() == AUDIO_FILES  # sorted


def test_queue_http_flow(stage):
    app, core, spawn, _clock = stage
    with TestClient(app) as client:
        snap = client.get("/api/queue").json()
        assert snap["entries"] == []
        assert snap["now"]["holding"] is True
        assert snap["now"]["pattern"] == "spiral"
        assert snap["audio_player"] == "fakeplay"

        # Append: starts immediately from the hold.
        snap = client.post(
            "/api/queue", json={"pattern": "plain", "duration": 5}
        ).json()
        assert snap["now"]["index"] == 0
        assert snap["now"]["pattern"] == "plain"
        assert snap["now"]["holding"] is False
        # Bad entries are refused whole, with a reason.
        assert client.post("/api/queue", json={"pattern": "nope"}).status_code == 422
        assert (
            client.post(
                "/api/queue", json={"pattern": "plain", "duration": -1}
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/queue", json={"pattern": "plain", "audio": "missing.mp3"}
            ).status_code
            == 422
        )

        # Audio through the API: the (stubbed) player spawns and skip kills it.
        snap = client.post(
            "/api/queue", json={"pattern": "timed", "audio": "track1.mp3"}
        ).json()
        assert [e["pattern"] for e in snap["entries"]] == ["plain", "timed"]
        assert spawn.procs == []  # queued behind "plain": not playing yet
        snap = client.post("/api/queue/skip").json()
        assert snap["now"]["pattern"] == "timed" and snap["audio_playing"] is True
        assert len(spawn.procs) == 1
        snap = client.post("/api/queue/skip").json()  # skip kills the player
        assert spawn.procs[0].terminated is True
        assert snap["now"]["holding"] is True and snap["audio_playing"] is False

        # Move validation and index bounds.
        assert (
            client.post("/api/queue/move", json={"from": 0, "to": 9}).status_code == 422
        )
        assert client.post("/api/queue/move", json={"from": 0}).status_code == 422
        assert (
            client.post("/api/queue/move", json={"from": 1, "to": 0}).status_code == 200
        )
        assert client.delete("/api/queue/9").status_code == 404
        snap = client.delete("/api/queue/0").json()
        assert len(snap["entries"]) == 1

        snap = client.post("/api/queue/clear").json()
        assert snap["entries"] == [] and snap["now"]["holding"] is True


def test_ws_stream_session_then_frames(stage):
    """WS join: SESSION immediately, keyframe at the next tick, deltas
    after; a queued entry re-keyframes but never re-sends SESSION; a
    {"type":"resync"} from the client forces a keyframe."""
    app, core, _spawn, clock = stage
    decoder = Decoder()
    with TestClient(app) as client:
        with client.websocket_connect("/api/stage") as ws:
            frame_type, controller = decoder.decode(ws.receive_bytes())
            assert frame_type == p.FRAME_SESSION and controller == 0

            core.tick()  # the join requested a keyframe
            assert decoder.decode(ws.receive_bytes())[0] == p.FRAME_KEYFRAME
            clock.advance(TICK)
            core.tick()
            assert decoder.decode(ws.receive_bytes())[0] == p.FRAME_DELTA
            # Decoded state is sane dequantized OKLCH.
            oklch = decoder.active_oklch(0)
            assert oklch.shape == (core.engine.lights.n, 3)

            # Entry start from the hold: gapless — keyframe, no SESSION.
            client.post("/api/queue", json={"pattern": "plain"})
            clock.advance(TICK)
            core.tick()
            assert decoder.decode(ws.receive_bytes())[0] == p.FRAME_KEYFRAME

            # Client resync request forces a keyframe (well before the
            # 2 s cadence could: the clock only advances ~1 s here).
            ws.send_text(json.dumps({"type": "resync"}))
            forced = False
            for _ in range(30):
                clock.advance(TICK)
                core.tick()
                if decoder.decode(ws.receive_bytes())[0] == p.FRAME_KEYFRAME:
                    forced = True
                    break
            assert forced


def test_create_app_mounts_stage(tmp_path, lights):  # noqa: F811
    """The serve path: create_app(stage=True) with --stage-lights as a
    file path serves the page + static module, runs the ticker under the
    composed lifespan (SESSION then a live keyframe with no manual
    tick), takes queue commands, and persists under <store>/stage/."""
    from luminary.server.app import create_app

    lights_path = tmp_path / "tiny.lights.json"
    lights.save(lights_path)
    app = create_app(
        store_dir=tmp_path / "store", stage=True, stage_lights=str(lights_path)
    )
    with TestClient(app) as client:
        page = client.get("/stage")
        assert page.status_code == 200 and "stage-canvas" in page.text
        assert client.get("/static/stage.js").status_code == 200
        assert client.get("/static/mapping.js").status_code == 200  # imported

        snap = client.get("/api/queue").json()
        assert snap["now"]["holding"] is True
        assert snap["now"]["pattern"] == "spiral"  # the repo default
        assert client.get("/api/audio").json() == []

        decoder = Decoder()
        with client.websocket_connect("/api/stage") as ws:
            frame_type, controller = decoder.decode(ws.receive_bytes())
            assert frame_type == p.FRAME_SESSION and controller == 0
            # No manual tick: the next frame proves the mounted ticker is
            # alive (it idles until this socket joined).
            assert decoder.decode(ws.receive_bytes())[0] == p.FRAME_KEYFRAME

        snap = client.post(
            "/api/queue", json={"pattern": "spiral", "duration": 60}
        ).json()
        assert snap["now"]["holding"] is False
        assert (tmp_path / "store" / "stage" / "queue.json").is_file()

        # The rest of the server is untouched.
        assert client.get("/api/health").json()["status"] == "ok"


def test_create_app_stage_off_by_default(tmp_path):
    from luminary.server.app import create_app

    app = create_app(store_dir=tmp_path / "store")
    with TestClient(app) as client:
        assert client.get("/stage").status_code == 404
        assert client.get("/api/queue").status_code == 404
        assert client.get("/api/health").status_code == 200

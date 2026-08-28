"""Demo geometry seeding (docs/deploy.md): idempotent, and visible to the API."""

from fastapi.testclient import TestClient

from luminary.server.app import create_app
from luminary.server.demo import seed_geometries


def test_seed_idempotent_and_served(tmp_path):
    state_dir = tmp_path / "state"
    first = seed_geometries(state_dir)
    second = seed_geometries(state_dir)
    assert first == second  # content-hash ids: reseeding changes nothing
    assert {entry["kind"] for entry in first} == {"scaffold", "lights"}

    app = create_app(state_dir=state_dir)
    with TestClient(app) as client:
        names = {entry["name"] for entry in client.get("/api/lights").json()}
        assert {
            "hex-demo",
            "pentagon-4A-35",
            "pentagon-4A-33",
            "pentagon-4A-37",
        } <= names
        scaffolds = client.get("/api/scaffolds").json()
        assert any(entry["name"] == "hex-demo" for entry in scaffolds)

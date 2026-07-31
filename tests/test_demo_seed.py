"""Demo store seeding (docs/deploy.md): idempotent, and visible to the API."""

from fastapi.testclient import TestClient

from luminary.server.app import create_app
from luminary.server.demo import seed_store


def test_seed_idempotent_and_served(tmp_path):
    store_dir = tmp_path / "store"
    first = seed_store(store_dir)
    second = seed_store(store_dir)
    assert first == second  # content-hash ids: reseeding changes nothing
    assert {entry["kind"] for entry in first} == {"scaffold", "lights"}

    app = create_app(store_dir=store_dir)
    with TestClient(app) as client:
        names = {entry["name"] for entry in client.get("/api/lights").json()}
        assert {"hex-demo", "pentagon-4A-35", "pentagon-4A-33"} <= names
        scaffolds = client.get("/api/scaffolds").json()
        assert any(entry["name"] == "hex-demo" for entry in scaffolds)

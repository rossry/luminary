"""serve --disable-pattern-upload: uploads 403, everything else works."""

from fastapi.testclient import TestClient

from luminary.server.app import create_app


def test_upload_disabled_403s_but_server_functions(tmp_path):
    app = create_app(store_dir=tmp_path / "store", allow_pattern_upload=False)
    with TestClient(app) as client:
        health = client.get("/api/health").json()
        assert health["pattern_upload"] is False

        response = client.post(
            "/api/patterns",
            files={"file": ("x.py", b"print('nope')", "text/x-python")},
        )
        assert response.status_code == 403
        assert "disabled" in response.json()["detail"]

        # Repo patterns still listed; geometry endpoints unaffected.
        names = {e["name"] for e in client.get("/api/patterns").json() if e["ok"]}
        assert "simple" in names
        doc = {
            "schema": "luminary.scaffold/1",
            "space": {"authoritative": ["xy"]},
            "lines": [{"p1": [0, 0], "p2": [10, 0]}],
            "meta": {"name": "t"},
        }
        assert client.post("/api/scaffolds", json=doc).status_code == 200


def test_upload_enabled_by_default(tmp_path):
    app = create_app(store_dir=tmp_path / "store")
    with TestClient(app) as client:
        assert client.get("/api/health").json()["pattern_upload"] is True

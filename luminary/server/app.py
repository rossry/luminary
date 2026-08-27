"""FastAPI app: the exit-condition REST + WebSocket API (spec §15).

A thin adapter: every endpoint translates HTTP/WS to store/registry/engine
calls and holds no rendering or codec logic (spec §15.1.1). The engine never
imports this module.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import FastAPI, HTTPException, Query, UploadFile, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from luminary.comms.codec import CodecConfig
from luminary.drivers.websocket_driver import WebSocketSession
from luminary.engine.engine import Engine
from luminary.geometry.capture.from_scaffold import CaptureParams, capture
from luminary.geometry.lights import LightsGeometry, LightsGeometryError
from luminary.geometry.scaffold import Scaffold, ScaffoldError
from luminary.patterns.registry import PatternRegistry, default_registry
from luminary.render import projection, svg
from luminary.server.store import Store

_STATIC_DIR = Path(__file__).parent / "static"


def create_app(
    store_dir: Optional[Path] = None,
    registry: Optional[PatternRegistry] = None,
    uploads_dir: Optional[Path] = None,
    allow_pattern_upload: bool = True,
    mapping_demo: bool = False,
) -> FastAPI:
    """Build the app. ``allow_pattern_upload=False`` hard-disables
    POST /api/patterns (403) — uploads execute in-process (spec §15.5.2), so
    shared deployments run without them and take patterns from the repo
    instead (docs/deploy.md). ``mapping_demo=True`` mounts the hardware-free
    mapping tutorial (``luminary.mapping.web``) at ``/demo/mapping``; its
    mapping records persist under ``<store_dir>/mapping-demo/``."""
    store_dir = Path(store_dir or "var")
    uploads_dir = Path(uploads_dir or store_dir / "patterns-uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    store = Store(store_dir)
    registry = registry or default_registry(
        [uploads_dir] if allow_pattern_upload else []
    )

    if mapping_demo:
        from luminary.mapping.web import create_demo_app

        demo_app = create_demo_app(
            root_page="demo", store_dir=store_dir / "mapping-demo"
        )

        @asynccontextmanager
        async def _demo_lifespan(_app: FastAPI) -> AsyncIterator[None]:
            # Starlette does not run mounted apps' lifespans; enter the
            # demo's explicitly so its frame ticker starts and stops with
            # this server.
            async with demo_app.router.lifespan_context(demo_app):
                yield

        app = FastAPI(title="Luminary", version="2.1", lifespan=_demo_lifespan)
        app.mount("/demo/mapping", demo_app, name="mapping-demo")
    else:
        app = FastAPI(title="Luminary", version="2.1")
    app.state.store = store
    app.state.registry = registry
    app.state.uploads_dir = uploads_dir
    app.state.allow_pattern_upload = allow_pattern_upload

    # ------------------------------------------------------------------ health

    @app.get("/api/health")
    def health() -> Dict[str, Any]:
        from luminary.comms.protocol import PROTOCOL_VERSION

        return {
            "status": "ok",
            "protocol_version": PROTOCOL_VERSION,
            "patterns": len(registry.patterns),
            "pattern_upload": allow_pattern_upload,
        }

    # --------------------------------------------------------------- scaffolds

    @app.post("/api/scaffolds")
    def save_scaffold(doc: Dict[str, Any]) -> Dict[str, str]:
        try:
            Scaffold.load(doc)  # validate before persisting
        except (ScaffoldError, ValueError) as exc:
            raise HTTPException(422, detail=str(exc))
        return {"id": store.save("scaffolds", doc)}

    @app.get("/api/scaffolds")
    def list_scaffolds() -> list:
        return store.list("scaffolds")

    @app.get("/api/scaffolds/{doc_id}")
    def get_scaffold(doc_id: str) -> JSONResponse:
        return JSONResponse(_get_or_404(store, "scaffolds", doc_id))

    @app.get("/api/scaffolds/{doc_id}/view", response_class=HTMLResponse)
    def view_scaffold(doc_id: str) -> str:
        scaffold = Scaffold.load(_get_or_404(store, "scaffolds", doc_id))
        return _view_page(f"Scaffold {doc_id}", svg.scaffold_svg(scaffold))

    # ------------------------------------------------------------------ lights

    @app.post("/api/lights")
    def save_lights(doc: Dict[str, Any]) -> Dict[str, str]:
        try:
            LightsGeometry.load(doc)
        except (LightsGeometryError, ValueError) as exc:
            raise HTTPException(422, detail=str(exc))
        return {"id": store.save("lights", doc)}

    @app.get("/api/lights")
    def list_lights() -> list:
        return store.list("lights")

    @app.get("/api/lights/{doc_id}")
    def get_lights(doc_id: str) -> JSONResponse:
        return JSONResponse(_get_or_404(store, "lights", doc_id))

    @app.get("/api/lights/{doc_id}/layout")
    def get_lights_layout(doc_id: str) -> JSONResponse:
        lights = LightsGeometry.load(_get_or_404(store, "lights", doc_id))
        return JSONResponse(projection.lights_layout(lights))

    @app.get("/api/lights/{doc_id}/view", response_class=HTMLResponse)
    def view_lights(doc_id: str) -> str:
        lights = LightsGeometry.load(_get_or_404(store, "lights", doc_id))
        return _view_page(f"Lights {doc_id}", svg.lights_svg(lights))

    @app.post("/api/lights/from-scaffold")
    def lights_from_scaffold(body: Dict[str, Any]) -> Dict[str, str]:
        scaffold_id = body.get("scaffold_id")
        if not isinstance(scaffold_id, str):
            raise HTTPException(422, detail="scaffold_id (string) is required")
        scaffold = Scaffold.load(_get_or_404(store, "scaffolds", scaffold_id))
        try:
            params = CaptureParams.model_validate(body.get("params") or {})
            lights = capture(scaffold, params)
        except (LightsGeometryError, ValueError) as exc:
            raise HTTPException(422, detail=str(exc))
        doc = lights.to_file_dict()
        doc["source"]["scaffold"] = scaffold_id
        return {"id": store.save("lights", doc)}

    # ---------------------------------------------------------------- patterns

    @app.get("/api/patterns")
    def list_patterns() -> list:
        return registry.list()

    @app.post("/api/patterns")
    async def upload_pattern(file: UploadFile) -> Dict[str, Any]:
        if not allow_pattern_upload:
            raise HTTPException(
                403,
                detail="Pattern upload is disabled on this server; add patterns "
                "to the repository and redeploy (docs/deploy.md)",
            )
        name = Path(file.filename or "pattern.py").name
        if not name.endswith(".py"):
            raise HTTPException(422, detail="Pattern uploads must be .py files")
        target = uploads_dir / name
        target.write_bytes(await file.read())
        registry.reload()
        error = registry.errors.get(str(target))
        if error is not None:
            return {"ok": False, "file": name, "error": error}
        loaded = [
            entry["name"]
            for entry in registry.list()
            if entry["ok"] and registry._by_stem.get(target.stem) == entry["name"]
        ]
        return {"ok": True, "file": name, "patterns": loaded}

    # -------------------------------------------------------------------- play

    @app.websocket("/api/play")
    async def play(
        websocket: WebSocket,
        lights: str = Query(...),
        pattern: str = Query(...),
        fps: float = Query(30.0, gt=0, le=120),
        budget: Optional[int] = Query(None, ge=64),
    ) -> None:
        try:
            geometry = LightsGeometry.load(store.get("lights", lights))
            selected = registry.get(pattern)
        except (KeyError, LightsGeometryError, ValueError):
            await websocket.close(code=4404)
            return
        await websocket.accept()
        engine = Engine(
            geometry,
            selected,
            fps=fps,
            codec_config=CodecConfig(budget_bytes=budget),
        )
        session = WebSocketSession(engine, websocket, resolve_pattern=registry.get)
        await session.run()

    # ------------------------------------------------------------------- pages

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (_STATIC_DIR / "index.html").read_text()

    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
    return app


def _get_or_404(store: Store, kind: str, doc_id: str) -> Dict[str, Any]:
    try:
        return store.get(kind, doc_id)
    except KeyError as exc:
        raise HTTPException(404, detail=str(exc))


def _view_page(title: str, svg_markup: str) -> str:
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>{title}</title>"
        "<style>body{margin:0;background:#101014;color:#dde;"
        "font-family:system-ui}h1{font-size:1rem;padding:.6rem 1rem;margin:0}"
        "div{padding:0 1rem 1rem}</style></head>"
        f"<body><h1>{title}</h1><div>{svg_markup}</div></body></html>"
    )
